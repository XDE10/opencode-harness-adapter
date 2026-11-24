from r02s1pkg import ConfigLoader, ConfigSchema


def test_smoke_single_file_load():
    files = {
        "app.cfg": """
        [server]
        host = ${HOST:-127.0.0.1}
        port = 8080
        debug = true
        """
    }
    schema = ConfigSchema()
    schema.add_field("server", "host", type="str")
    schema.add_field("server", "port", type="int")
    schema.add_field("server", "debug", type="bool")

    loader = ConfigLoader(files=files, env={})
    cfg = loader.load("app.cfg", schema=schema)
    assert cfg["server"]["host"] == "127.0.0.1"
    assert cfg["server"]["port"] == 8080
    assert cfg["server"]["debug"] is True


def test_smoke_env_override():
    files = {
        "app.cfg": """
        [db]
        url = postgres://${DB_HOST}/mydb
        """
    }
    loader = ConfigLoader(files=files, env={"DB_HOST": "db.internal"})
    cfg = loader.load("app.cfg")
    assert cfg["db"]["url"] == "postgres://db.internal/mydb"
