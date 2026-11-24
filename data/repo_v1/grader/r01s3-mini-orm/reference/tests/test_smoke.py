from r01s3pkg import Field, Schema, Table


def test_insert_and_basic_query():
    schema = Schema([
        Field("id", int),
        Field("name", str),
        Field("active", bool, default=True),
    ])
    users = Table("users", schema)
    users.insert({"id": "1", "name": "Alice"})
    users.insert({"id": 2, "name": "Bob", "active": False})

    res = users.query().where("active", "=", True).execute()
    assert len(res) == 1
    assert res[0]["id"] == 1
    assert res[0]["name"] == "Alice"


def test_ordering_and_limit():
    schema = Schema([
        Field("id", int),
        Field("score", float),
    ])
    scores = Table("scores", schema)
    scores.insert_many([
        {"id": 1, "score": 10.5},
        {"id": 2, "score": 25.0},
        {"id": 3, "score": 15.0},
    ])
    top = scores.query().order_by("score", descending=True).limit(2).execute()
    assert [r["id"] for r in top] == [2, 3]
