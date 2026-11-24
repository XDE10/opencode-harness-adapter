import pytest
from r02s3pkg import ConfigCascade, ConfigError, ConfigSchema, FieldSpec


def test_multi_layer_scalar_types_and_lists():
    cascade = ConfigCascade()
    cascade.add_layer(
        """
        [app]
        name = "billing"
        workers = 4
        ratio = 0.75
        active = true
        ports = 8001, 8002, 8003
        """
    )
    resolved = cascade.resolve()
    assert resolved["app"] == {
        "name": "billing",
        "workers": 4,
        "ratio": 0.75,
        "active": True,
        "ports": [8001, 8002, 8003],
    }


def test_missing_env_var_without_default_raises():
    cascade = ConfigCascade()
    cascade.add_layer(
        """
        [auth]
        secret = ${API_SECRET}
        """
    )
    with pytest.raises(ConfigError, match="API_SECRET"):
        cascade.resolve(env={})


def test_circular_inheritance_raises():
    cascade = ConfigCascade()
    cascade.add_layer(
        """
        [a]
        extends = b
        x = 1

        [b]
        extends = a
        y = 2
        """
    )
    with pytest.raises(ConfigError, match="Circular"):
        cascade.resolve()


def test_hash_inside_double_quotes_and_inline_comment():
    cascade = ConfigCascade()
    cascade.add_layer(
        """
        [ui]
        color = "#ff00aa" # primary brand hex
        channel = "ops#alerts"
        """
    )
    resolved = cascade.resolve()
    assert resolved["ui"]["color"] == "#ff00aa"
    assert resolved["ui"]["channel"] == "ops#alerts"


def test_env_interpolation_coerces_unquoted_and_preserves_quoted():
    cascade = ConfigCascade()
    cascade.add_layer(
        """
        [service]
        port = ${PORT:-8080}
        debug = ${DEBUG_MODE:-false}
        badge = "${BADGE_CODE:-007}"
        """
    )
    resolved = cascade.resolve(env={"PORT": "9090", "DEBUG_MODE": "true"})
    assert resolved["service"]["port"] == 9090
    assert isinstance(resolved["service"]["port"], int)
    assert resolved["service"]["debug"] is True
    assert resolved["service"]["badge"] == "007"


def test_env_interpolation_empty_string_uses_fallback():
    cascade = ConfigCascade()
    cascade.add_layer(
        """
        [db]
        timeout = ${DB_TIMEOUT:-30}
        host = "${DB_HOST:-localhost}"
        """
    )
    resolved = cascade.resolve(env={"DB_TIMEOUT": "", "DB_HOST": ""})
    assert resolved["db"]["timeout"] == 30
    assert resolved["db"]["host"] == "localhost"


def test_inheritance_does_not_mutate_parent_or_keep_extends_key():
    cascade = ConfigCascade()
    cascade.add_layer(
        """
        [base]
        timeout = 10
        retries = 3

        [staging]
        extends = base
        timeout = 25

        [prod]
        extends = staging
        region = "us-east"
        """
    )
    resolved = cascade.resolve()
    assert resolved["base"] == {"timeout": 10, "retries": 3}
    assert resolved["staging"] == {"timeout": 25, "retries": 3}
    assert resolved["prod"] == {"timeout": 25, "retries": 3, "region": "us-east"}
    assert "extends" not in resolved["staging"]
    assert "extends" not in resolved["prod"]


def test_schema_accepts_falsy_values_and_populates_missing_section_defaults():
    schema = ConfigSchema()
    schema.add_field("flags", "enabled", FieldSpec(bool, required=True))
    schema.add_field("flags", "retries", FieldSpec(int, required=True))
    schema.add_field("flags", "prefix", FieldSpec(str, required=True))
    schema.add_field("telemetry", "endpoint", FieldSpec(str, required=False, default="http://localhost:4317"))
    schema.add_field("telemetry", "tags", FieldSpec(list, required=False, default=["core"]))

    cascade = ConfigCascade(schema=schema)
    cascade.add_layer(
        """
        [flags]
        enabled = false
        retries = 0
        prefix = ""
        """
    )
    first = cascade.resolve()
    assert first["flags"] == {"enabled": False, "retries": 0, "prefix": ""}
    assert first["telemetry"] == {"endpoint": "http://localhost:4317", "tags": ["core"]}

    first["telemetry"]["tags"].append("mutated")
    second = cascade.resolve()
    assert second["telemetry"]["tags"] == ["core"]


def test_schema_missing_required_in_absent_section_raises():
    schema = ConfigSchema()
    schema.add_field("database", "dsn", FieldSpec(str, required=True))

    cascade = ConfigCascade(schema=schema)
    cascade.add_layer(
        """
        [other]
        key = "val"
        """
    )
    with pytest.raises(ConfigError, match="database.dsn"):
        cascade.resolve()
