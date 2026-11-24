import pytest
from r01s3pkg import Field, Schema, Table


def test_schema_rejects_unknown_and_missing_required():
    schema = Schema([Field("id", int), Field("title", str)])
    table = Table("posts", schema)

    with pytest.raises(ValueError):
        table.insert({"id": 1})

    with pytest.raises(ValueError):
        table.insert({"id": 1, "title": "Hello", "extra": 123})


def test_schema_rejects_bool_for_int_and_float():
    schema = Schema([Field("id", int), Field("rating", float)])
    table = Table("items", schema)

    with pytest.raises(ValueError):
        table.insert({"id": True, "rating": 4.5})

    with pytest.raises(ValueError):
        table.insert({"id": 1, "rating": False})


def test_predicate_filtering_and_nullable_comparisons():
    schema = Schema([
        Field("id", int),
        Field("tag", str, nullable=True),
        Field("views", int, nullable=True),
    ])
    table = Table("articles", schema)
    table.insert_many([
        {"id": 1, "tag": "python", "views": 100},
        {"id": 2, "tag": None, "views": None},
        {"id": 3, "tag": "rust", "views": 50},
    ])

    assert [r["id"] for r in table.query().where("views", ">", 60).execute()] == [1]
    assert [r["id"] for r in table.query().where("tag", "=", None).execute()] == [2]
    assert [r["id"] for r in table.query().where("tag", "in", ["python", "go"]).execute()] == [1]


def test_callable_default_and_offset_pagination():
    counter = {"n": 0}

    def next_id() -> int:
        counter["n"] += 1
        return counter["n"]

    schema = Schema([Field("id", int, default=next_id), Field("name", str)])
    table = Table("tags", schema)
    table.insert_many([{"name": "a"}, {"name": "b"}, {"name": "c"}, {"name": "d"}])

    page = table.query().order_by("id").offset(1).limit(2).execute()
    assert [r["id"] for r in page] == [2, 3]


def test_bool_string_and_int_coercion_in_table_queries():
    schema = Schema([
        Field("id", int),
        Field("enabled", bool),
    ])
    table = Table("flags", schema)
    table.insert_many([
        {"id": 1, "enabled": "false"},
        {"id": 2, "enabled": "TRUE"},
        {"id": 3, "enabled": "0"},
        {"id": 4, "enabled": "yes"},
        {"id": 5, "enabled": 0},
    ])

    disabled = table.query().where("enabled", "=", False).order_by("id").execute()
    assert [r["id"] for r in disabled] == [1, 3, 5]

    enabled = table.query().where("enabled", "=", True).order_by("id").execute()
    assert [r["id"] for r in enabled] == [2, 4]


def test_bool_invalid_string_or_int_raises_value_error():
    schema = Schema([Field("id", int), Field("enabled", bool)])
    table = Table("flags", schema)

    with pytest.raises(ValueError):
        table.insert({"id": 1, "enabled": "maybe"})

    with pytest.raises(ValueError):
        table.insert({"id": 2, "enabled": 2})


def test_order_by_places_none_last_in_both_directions():
    schema = Schema([
        Field("id", int),
        Field("score", int, nullable=True),
    ])
    table = Table("leaderboard", schema)
    table.insert_many([
        {"id": 1, "score": 20},
        {"id": 2, "score": None},
        {"id": 3, "score": 50},
        {"id": 4, "score": 10},
    ])

    asc_ids = [r["id"] for r in table.query().order_by("score", descending=False).execute()]
    assert asc_ids == [4, 1, 3, 2]

    desc_ids = [r["id"] for r in table.query().order_by("score", descending=True).execute()]
    assert desc_ids == [3, 1, 4, 2]


def test_join_does_not_mutate_table_rows_across_queries():
    user_schema = Schema([Field("id", int), Field("name", str)])
    order_schema = Schema([Field("id", int), Field("user_id", int), Field("total", int)])

    users = Table("users", user_schema)
    orders = Table("orders", order_schema)

    users.insert({"id": 1, "name": "Alice"})
    orders.insert_many([
        {"id": 100, "user_id": 1, "total": 50},
        {"id": 101, "user_id": 1, "total": 75},
    ])

    joined = (
        users.query()
        .join(orders.query().execute(), left_key="id", right_key="user_id", prefix="order_")
        .order_by("order_id")
        .execute()
    )
    assert len(joined) == 2
    assert joined[0]["order_total"] == 50
    assert joined[1]["order_total"] == 75

    plain_users = users.query().execute()
    assert plain_users == [{"id": 1, "name": "Alice"}]
