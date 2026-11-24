import pytest
from miniorm import Column, Schema, Table


def make_users_table() -> Table:
    schema = Schema(
        [
            Column("id", int, unique=True),
            Column("name", str),
            Column("score", float, nullable=True),
            Column("active", bool, default=True),
        ]
    )
    return Table("users", schema)


def test_insert_and_basic_query():
    users = make_users_table()
    users.insert({"id": "1", "name": "Alice", "score": 91.5, "active": True})
    users.insert({"id": "2", "name": "Bob", "score": 80.0, "active": False})

    active = users.query().where(active=True).all()
    assert len(active) == 1
    assert active[0]["name"] == "Alice"
    assert active[0]["id"] == 1


def test_unique_constraint_on_insert():
    users = make_users_table()
    users.insert({"id": 1, "name": "Alice"})
    with pytest.raises(ValueError):
        users.insert({"id": 1, "name": "Duplicate"})
