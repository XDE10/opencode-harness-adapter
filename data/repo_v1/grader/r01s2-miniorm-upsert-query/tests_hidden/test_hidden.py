import pytest
from r01s2orm import Column, ConstraintError, Schema, Table


def build_tables() -> tuple[Table, Table]:
    user_schema = Schema([
        Column("id", int, primary_key=True),
        Column("username", str, unique=True, normalizer=lambda s: s.strip().lower()),
        Column("badge", str, unique=True, nullable=True),
        Column("team_id", int, nullable=True),
        Column("points", int, default=0),
    ])
    team_schema = Schema([
        Column("id", int, primary_key=True),
        Column("title", str, unique=True),
    ])
    return Table("users", user_schema), Table("teams", team_schema)


def test_schema_validation_and_defaults():
    users, _ = build_tables()
    row = users.upsert({"id": 10, "username": "  DevUser "})
    assert row == {
        "id": 10,
        "username": "devuser",
        "badge": None,
        "team_id": None,
        "points": 0,
    }
    with pytest.raises(ConstraintError):
        users.upsert({"id": "not-an-int", "username": "u2"})
    with pytest.raises(ConstraintError):
        users.upsert({"id": 11, "username": "u2", "extra": 123})


def test_upsert_conflict_modes_raise_and_ignore():
    users, _ = build_tables()
    users.upsert({"id": 1, "username": "alpha", "points": 10})

    with pytest.raises(ConstraintError):
        users.upsert({"id": 1, "username": "alpha_new", "points": 99}, on_conflict="raise")

    ignored = users.upsert({"id": 1, "username": "alpha_new", "points": 99}, on_conflict="ignore")
    assert ignored["username"] == "alpha"
    assert ignored["points"] == 10
    assert users.find_by_unique("username", "alpha")["id"] == 1
    assert users.find_by_unique("username", "alpha_new") is None


def test_delete_cleans_up_unique_indexes():
    users, _ = build_tables()
    users.upsert({"id": 1, "username": "alpha", "badge": "gold"})
    assert users.delete(1) is True
    assert users.delete(1) is False
    assert users.find_by_unique("username", "alpha") is None
    assert users.find_by_unique("badge", "gold") is None
    reused = users.upsert({"id": 2, "username": "alpha", "badge": "gold"})
    assert reused["id"] == 2


def test_failed_upsert_update_preserves_existing_unique_index():
    users, _ = build_tables()
    users.upsert({"id": 1, "username": "alice", "badge": "b-100", "points": 10})
    users.upsert({"id": 2, "username": "bob", "badge": "b-200", "points": 20})

    with pytest.raises(ConstraintError):
        users.upsert(
            {"id": 1, "username": "alice_renamed", "badge": "b-200", "points": 50},
            on_conflict="update",
        )

    assert users.get(1) == {
        "id": 1,
        "username": "alice",
        "badge": "b-100",
        "team_id": None,
        "points": 10,
    }
    assert users.find_by_unique("username", "alice") is not None
    assert users.find_by_unique("username", "alice")["id"] == 1
    assert users.find_by_unique("badge", "b-100") is not None
    assert users.find_by_unique("badge", "b-100")["id"] == 1


def test_failed_upsert_update_prevents_hijacking_old_unique_key():
    users, _ = build_tables()
    users.upsert({"id": 1, "username": "alice", "badge": "b-100", "points": 10})
    users.upsert({"id": 2, "username": "bob", "badge": "b-200", "points": 20})

    with pytest.raises(ConstraintError):
        users.upsert(
            {"id": 1, "username": "bob", "badge": "b-100", "points": 99},
            on_conflict="update",
        )

    with pytest.raises(ConstraintError):
        users.upsert({"id": 3, "username": "alice", "badge": "b-300", "points": 5})


def test_successful_upsert_update_replaces_unique_index_and_allows_self_values():
    users, _ = build_tables()
    users.upsert({"id": 1, "username": "alice", "badge": "b-100", "points": 10})
    updated = users.upsert(
        {"id": 1, "username": "alice", "badge": "b-101", "points": 25},
        on_conflict="update",
    )
    assert updated["points"] == 25
    assert users.find_by_unique("username", "alice")["id"] == 1
    assert users.find_by_unique("badge", "b-100") is None
    assert users.find_by_unique("badge", "b-101")["id"] == 1


def test_query_immutability_across_branched_compositions():
    users, _ = build_tables()
    users.upsert({"id": 1, "username": "u1", "team_id": 10, "points": 30})
    users.upsert({"id": 2, "username": "u2", "team_id": 10, "points": 10})
    users.upsert({"id": 3, "username": "u3", "team_id": 20, "points": 50})

    base_q = users.query().where(lambda r: r["team_id"] == 10)
    high_q = base_q.where(lambda r: r["points"] >= 20)
    low_q = base_q.where(lambda r: r["points"] < 20)

    ordered_asc = base_q.order_by("points", descending=False)
    ordered_desc = base_q.order_by("points", descending=True)

    assert [r["id"] for r in high_q.all()] == [1]
    assert [r["id"] for r in low_q.all()] == [2]
    assert [r["id"] for r in ordered_asc.all()] == [2, 1]
    assert [r["id"] for r in ordered_desc.all()] == [1, 2]
    assert len(base_q.all()) == 2


def test_query_offset_and_limit_windowing_and_total_count():
    users, _ = build_tables()
    for i in range(1, 7):
        users.upsert({"id": i, "username": f"user{i}", "points": i * 10})

    paged = (
        users.query()
        .where(lambda r: r["points"] >= 20)
        .order_by("points", descending=False)
        .offset(2)
        .limit(2)
    )
    rows = paged.all()
    assert [r["id"] for r in rows] == [4, 5]
    assert paged.count() == 5


def test_query_join_with_immutability_and_pagination():
    users, teams = build_tables()
    teams.upsert({"id": 100, "title": "Core"})
    teams.upsert({"id": 200, "title": "Infra"})

    users.upsert({"id": 1, "username": "a", "team_id": 100, "points": 40})
    users.upsert({"id": 2, "username": "b", "team_id": 100, "points": 15})
    users.upsert({"id": 3, "username": "c", "team_id": 200, "points": 30})
    users.upsert({"id": 4, "username": "d", "team_id": 100, "points": 25})

    base_users = users.query()
    joined_q = (
        base_users.join(teams, "team_id", "id", prefix="team_")
        .where(lambda r: r["team_title"] == "Core")
        .order_by("points", descending=True)
    )
    page_q = joined_q.offset(1).limit(1)

    assert [r["id"] for r in page_q.all()] == [4]
    assert page_q.count() == 3
    assert "team_title" not in base_users.all()[0]
