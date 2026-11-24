import pytest
from miniorm import Column, Schema, Table


def make_table() -> Table:
    schema = Schema(
        [
            Column("id", int, unique=True),
            Column("email", str, unique=True),
            Column("name", str),
            Column("score", float, nullable=True),
            Column("active", bool, default=True),
            Column("tags", list, default=[]),
        ]
    )
    return Table("accounts", schema)


def test_predicates_and_pagination():
    tbl = make_table()
    tbl.insert({"id": 1, "email": "a@x.com", "name": "A", "score": 10.0})
    tbl.insert({"id": 2, "email": "b@x.com", "name": "B", "score": 25.0})
    tbl.insert({"id": 3, "email": "c@x.com", "name": "C", "score": 40.0})
    tbl.insert({"id": 4, "email": "d@x.com", "name": "D", "score": None})

    rows = (
        tbl.query()
        .where(score__gte=10.0, score__lt=40.0)
        .order_by("score", descending=False)
        .offset(1)
        .limit(1)
        .all()
    )
    assert [r["id"] for r in rows] == [2]


def test_inner_join_tables():
    users = make_table()
    users.insert({"id": 1, "email": "a@x.com", "name": "Alice", "score": 50.0})
    users.insert({"id": 2, "email": "b@x.com", "name": "Bob", "score": 70.0})

    orders = Table(
        "orders",
        Schema(
            [
                Column("id", int, unique=True),
                Column("user_id", int),
                Column("item", str),
            ]
        ),
    )
    orders.insert({"id": 100, "user_id": 1, "item": "Book"})
    orders.insert({"id": 101, "user_id": 1, "item": "Pen"})

    joined = users.inner_join(orders, left_on="id", right_on="user_id", prefix="order_")
    assert len(joined) == 2
    assert {r["order_id"] for r in joined} == {100, 101}
    assert {r["item"] for r in joined} == {"Book", "Pen"}


def test_ascending_order_places_nulls_last():
    tbl = make_table()
    tbl.insert({"id": 1, "email": "a@x.com", "name": "A", "score": None})
    tbl.insert({"id": 2, "email": "b@x.com", "name": "B", "score": 15.0})
    tbl.insert({"id": 3, "email": "c@x.com", "name": "C", "score": 5.0})

    asc = tbl.query().order_by("score", descending=False).all()
    assert [r["id"] for r in asc] == [3, 2, 1]


def test_boolean_string_coercion_and_invalid_rejection():
    tbl = make_table()
    r1 = tbl.insert({"id": 1, "email": "a@x.com", "name": "A", "active": "false"})
    r2 = tbl.insert({"id": 2, "email": "b@x.com", "name": "B", "active": " 0 "})
    r3 = tbl.insert({"id": 3, "email": "c@x.com", "name": "C", "active": "YES"})
    r4 = tbl.insert({"id": 4, "email": "d@x.com", "name": "D", "active": "No"})

    assert r1["active"] is False
    assert r2["active"] is False
    assert r3["active"] is True
    assert r4["active"] is False

    inactive_ids = [r["id"] for r in tbl.query().where(active=False).all()]
    assert inactive_ids == [1, 2, 4]

    with pytest.raises(ValueError):
        tbl.insert({"id": 5, "email": "e@x.com", "name": "E", "active": "maybe"})


def test_mutable_default_isolation_across_inserts():
    tbl = make_table()
    first = tbl.insert({"id": 1, "email": "a@x.com", "name": "A"})
    first["tags"].append("admin")

    second = tbl.insert({"id": 2, "email": "b@x.com", "name": "B"})
    assert second["tags"] == []


def test_update_where_non_unique_field_does_not_self_conflict():
    tbl = make_table()
    tbl.insert({"id": 1, "email": "a@x.com", "name": "Alice", "score": 10.0})
    tbl.insert({"id": 2, "email": "b@x.com", "name": "Bob", "score": 20.0})

    count = tbl.update_where({"score": 99.5, "active": "false"}, id=1)
    assert count == 1

    updated = tbl.query().where(id=1).all()[0]
    assert updated["score"] == 99.5
    assert updated["active"] is False


def test_update_where_unique_field_reindexes_and_checks_conflicts():
    tbl = make_table()
    tbl.insert({"id": 1, "email": "a@x.com", "name": "Alice"})
    tbl.insert({"id": 2, "email": "b@x.com", "name": "Bob"})

    # Updating row 1's unique email to a conflicting email must fail
    with pytest.raises(ValueError):
        tbl.update_where({"email": "b@x.com"}, id=1)

    # Updating row 1's unique email to a fresh email must release old "a@x.com"
    count = tbl.update_where({"email": "new_a@x.com"}, id=1)
    assert count == 1

    # Now a new row can reuse "a@x.com", while "new_a@x.com" is protected
    tbl.insert({"id": 3, "email": "a@x.com", "name": "Charlie"})
    with pytest.raises(ValueError):
        tbl.insert({"id": 4, "email": "new_a@x.com", "name": "DuplicateNew"})


def test_descending_order_places_nulls_last():
    tbl = make_table()
    tbl.insert({"id": 1, "email": "a@x.com", "name": "A", "score": None})
    tbl.insert({"id": 2, "email": "b@x.com", "name": "B", "score": 15.0})
    tbl.insert({"id": 3, "email": "c@x.com", "name": "C", "score": 35.0})
    tbl.insert({"id": 4, "email": "d@x.com", "name": "D", "score": None})

    desc = tbl.query().order_by("score", descending=True).all()
    assert [r["id"] for r in desc] == [3, 2, 1, 4]
