import pytest
from r01s2orm import Column, ConstraintError, Schema, Table


def make_users_table() -> Table:
    schema = Schema([
        Column("id", int, primary_key=True),
        Column("email", str, unique=True, normalizer=lambda s: s.strip().lower()),
        Column("score", int, default=0),
    ])
    return Table("users", schema)


def test_insert_and_basic_lookup():
    users = make_users_table()
    saved = users.upsert({"id": 1, "email": "Alice@Example.com", "score": 10})
    assert saved["email"] == "alice@example.com"
    assert users.get(1) == {"id": 1, "email": "alice@example.com", "score": 10}
    assert users.find_by_unique("email", "alice@example.com")["id"] == 1


def test_snapshot_and_rollback():
    users = make_users_table()
    users.upsert({"id": 1, "email": "a@example.com", "score": 5})
    users.snapshot("s1")
    users.upsert({"id": 2, "email": "b@example.com", "score": 20})
    assert len(users.all_rows()) == 2
    users.rollback("s1")
    assert len(users.all_rows()) == 1
    assert users.find_by_unique("email", "b@example.com") is None


def test_basic_query_filtering():
    users = make_users_table()
    users.upsert({"id": 1, "email": "a@example.com", "score": 15})
    users.upsert({"id": 2, "email": "b@example.com", "score": 5})
    high = users.query().where(lambda r: r["score"] >= 10).all()
    assert [r["id"] for r in high] == [1]
