import pytest
from r02s1pkg import ConfigError, ConfigLoader, ConfigSchema


def test_basic_parsing_and_quotes():
    files = {
        "base.cfg": """
        # comment line
        ; semicolon comment
        global_key = "quoted value"

        [service]
        name = 'my-service'
        workers = 4
        enabled = yes
        tags = api, v2, internal
        """
    }
    schema = ConfigSchema()
    schema.add_field("default", "global_key", type="str")
    schema.add_field("service", "name", type="str")
    schema.add_field("service", "workers", type="int")
    schema.add_field("service", "enabled", type="bool")
    schema.add_field("service", "tags", type="list")

    loader = ConfigLoader(files=files)
    result = loader.load("base.cfg", schema=schema)
    assert result["default"]["global_key"] == "quoted value"
    assert result["service"]["name"] == "my-service"
    assert result["service"]["workers"] == 4
    assert result["service"]["enabled"] is True
    assert result["service"]["tags"] == ["api", "v2", "internal"]


def test_missing_required_env_raises():
    files = {
        "app.cfg": """
        [auth]
        secret = ${SECRET_TOKEN}
        """
    }
    loader = ConfigLoader(files=files, env={})
    with pytest.raises(ConfigError, match="Missing required environment variable: SECRET_TOKEN"):
        loader.load("app.cfg")


def test_circular_inheritance_detected():
    files = {
        "a.cfg": "[meta]\nextends = b.cfg\n[app]\nx = 1",
        "b.cfg": "[meta]\nextends = a.cfg\n[app]\ny = 2",
    }
    loader = ConfigLoader(files=files)
    with pytest.raises(ConfigError, match="Circular config inheritance detected"):
        loader.load("a.cfg")


def test_schema_validation_errors_and_defaults():
    files = {
        "app.cfg": """
        [server]
        port = not_an_int
        """
    }
    schema = ConfigSchema()
    schema.add_field("server", "port", type="int")
    loader = ConfigLoader(files=files)
    with pytest.raises(ConfigError, match="Invalid int for server.port"):
        loader.load("app.cfg", schema=schema)


def test_empty_default_env_interpolation():
    files = {
        "app.cfg": """
        [routing]
        endpoint = http://${HOST:-localhost}:${PORT:-8080}${PREFIX:-}
        empty_list = ${EXTRA_ITEMS:-}
        """
    }
    schema = ConfigSchema()
    schema.add_field("routing", "endpoint", type="str")
    schema.add_field("routing", "empty_list", type="list")

    loader = ConfigLoader(files=files, env={})
    cfg = loader.load("app.cfg", schema=schema)
    assert cfg["routing"]["endpoint"] == "http://localhost:8080"
    assert cfg["routing"]["empty_list"] == []


def test_explicit_empty_env_var_not_overridden_by_default():
    files = {
        "app.cfg": """
        [routing]
        prefix = "${APP_PREFIX:-/v1}"
        """
    }
    loader = ConfigLoader(files=files, env={"APP_PREFIX": ""})
    cfg = loader.load("app.cfg")
    assert cfg["routing"]["prefix"] == ""


def test_child_overrides_parent_in_three_level_inheritance():
    files = {
        "base.cfg": """
        [server]
        host = 0.0.0.0
        port = 8000
        timeout = 30

        [logging]
        level = INFO
        """,
        "staging.cfg": """
        [meta]
        extends = base.cfg

        [server]
        port = 8080

        [logging]
        level = DEBUG
        """,
        "prod.cfg": """
        [meta]
        extends = staging.cfg

        [server]
        host = 10.0.0.1
        port = 9000

        [logging]
        level = WARN
        """,
    }
    schema = ConfigSchema()
    schema.add_field("server", "host", type="str")
    schema.add_field("server", "port", type="int")
    schema.add_field("server", "timeout", type="int")
    schema.add_field("logging", "level", type="str")

    loader = ConfigLoader(files=files)
    prod_cfg = loader.load("prod.cfg", schema=schema)
    assert prod_cfg["server"]["host"] == "10.0.0.1"
    assert prod_cfg["server"]["port"] == 9000
    assert prod_cfg["server"]["timeout"] == 30
    assert prod_cfg["logging"]["level"] == "WARN"


def test_multiple_parents_inheritance_order_and_child_precedence():
    files = {
        "defaults.cfg": """
        [db]
        host = localhost
        port = 5432
        pool = 5
        """,
        "mixin.cfg": """
        [db]
        port = 6432
        ssl = true
        """,
        "service.cfg": """
        [meta]
        extends = defaults.cfg, mixin.cfg

        [db]
        pool = 20
        """,
    }
    schema = ConfigSchema()
    schema.add_field("db", "host", type="str")
    schema.add_field("db", "port", type="int")
    schema.add_field("db", "pool", type="int")
    schema.add_field("db", "ssl", type="bool")

    loader = ConfigLoader(files=files)
    cfg = loader.load("service.cfg", schema=schema)
    assert cfg["db"]["host"] == "localhost"
    assert cfg["db"]["port"] == 6432
    assert cfg["db"]["pool"] == 20
    assert cfg["db"]["ssl"] is True


def test_combined_inheritance_and_empty_default_interpolation():
    files = {
        "base.cfg": """
        [http]
        url = https://${DOMAIN:-example.com}${SUBPATH:-/api}
        """,
        "child.cfg": """
        [meta]
        extends = base.cfg

        [http]
        url = https://${DOMAIN:-example.com}${SUBPATH:-}
        """,
    }
    loader = ConfigLoader(files=files, env={})
    child_cfg = loader.load("child.cfg")
    base_cfg = loader.load("base.cfg")
    assert child_cfg["http"]["url"] == "https://example.com"
    assert base_cfg["http"]["url"] == "https://example.com/api"
