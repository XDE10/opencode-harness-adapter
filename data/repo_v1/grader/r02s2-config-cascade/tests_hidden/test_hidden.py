import pytest
from r02s2pkg import ConfigStore, ConfigValidationError


def test_env_default_and_chained_interpolation():
    store = ConfigStore(env={"HOST": "db.internal"})
    store.apply_layer(
        "base",
        """
        [net]
        host = ${ENV:HOST:-localhost}
        port = ${ENV:PORT:-5432}
        dsn = postgres://${net.host}:${net.port}/app
        """,
    )
    snap = store.snapshot()
    assert snap["net"]["host"] == "db.internal"
    assert snap["net"]["port"] == "5432"
    assert snap["net"]["dsn"] == "postgres://db.internal:5432/app"


def test_multi_step_query_composition_with_where_predicate():
    store = ConfigStore()
    store.apply_layer(
        "clusters",
        """
        [cluster.alpha]
        role = primary
        node_count = 5
        node_zone = us-east

        [cluster.beta]
        role = replica
        node_count = 2
        node_zone = us-west

        [cluster.gamma]
        role = primary
        node_count = 3
        node_zone = eu-central
        """,
    )
    primaries = store.query(
        "cluster.*",
        key_prefix="node_",
        where=lambda sec: sec.get("role") == "primary" and int(sec.get("node_count", "0")) >= 3,
    )
    assert list(primaries.keys()) == ["cluster.alpha", "cluster.gamma"]
    assert primaries["cluster.alpha"] == {"node_count": "5", "node_zone": "us-east"}
    assert primaries["cluster.gamma"] == {"node_count": "3", "node_zone": "eu-central"}


def test_circular_inheritance_detection():
    store = ConfigStore()
    with pytest.raises(ValueError, match="Circular inheritance"):
        store.apply_layer(
            "bad",
            """
            [a : b]
            x = 1
            [b : a]
            y = 2
            """,
        )


def test_child_section_list_ops_do_not_mutate_parent():
    store = ConfigStore()
    store.apply_layer(
        "base",
        """
        [base.sec]
        tags = [core, v1]

        [child.sec : base.sec]
        tags += canary, v1
        tags -= core
        """,
    )
    snap = store.snapshot()
    assert snap["base.sec"]["tags"] == ["core", "v1"]
    assert snap["child.sec"]["tags"] == ["v1", "canary"]


def test_scalar_to_list_promotion_and_duplicate_removal():
    store = ConfigStore()
    store.apply_layer(
        "l1",
        """
        [auth]
        providers = oauth
        blocked = [legacy, test, legacy, guest]
        """,
    )
    store.apply_layer(
        "l2",
        """
        [auth]
        providers += saml, oauth, ldap
        blocked -= legacy
        """,
    )
    snap = store.snapshot()
    assert snap["auth"]["providers"] == ["oauth", "saml", "ldap"]
    assert snap["auth"]["blocked"] == ["test", "guest"]


def test_cross_section_list_interpolation_with_inheritance():
    store = ConfigStore()
    store.apply_layer(
        "l1",
        """
        [base.fw]
        ports = [80, 443]

        [edge.fw : base.fw]
        ports += 8443

        [summary]
        base_open = ${base.fw.ports}
        edge_open = ${edge.fw.ports}
        """,
    )
    snap = store.snapshot()
    assert snap["summary"]["base_open"] == "80,443"
    assert snap["summary"]["edge_open"] == "80,443,8443"


def test_failed_validation_rolls_back_new_layer_and_cache():
    store = ConfigStore()
    store.apply_layer(
        "base",
        """
        [server]
        port = 8080
        """,
    )
    schema = {
        "server": {
            "required": True,
            "keys": {
                "port": {
                    "required": True,
                    "validator": lambda v: v.isdigit() and int(v) < 65536,
                }
            },
        }
    }
    with pytest.raises(ConfigValidationError):
        store.apply_layer(
            "bad_override",
            """
            [server]
            port = 99999
            """,
            schema=schema,
        )

    assert store.snapshot()["server"]["port"] == "8080"
    assert store.query("server")["server"]["port"] == "8080"


def test_failed_in_place_layer_update_restores_previous_layer_version():
    store = ConfigStore()
    store.apply_layer(
        "base",
        """
        [db]
        pool = 10
        """,
    )
    store.apply_layer(
        "tuning",
        """
        [db]
        pool = 25
        """,
    )
    schema = {
        "db": {
            "required": True,
            "keys": {
                "pool": {
                    "required": True,
                    "validator": lambda v: v.isdigit() and int(v) > 0,
                }
            },
        }
    }
    with pytest.raises(ConfigValidationError):
        store.apply_layer(
            "tuning",
            """
            [db]
            pool = -5
            """,
            schema=schema,
        )

    assert store.query("db")["db"]["pool"] == "25"


def test_rollback_layer_invalidates_compiled_cache_for_queries():
    store = ConfigStore()
    store.apply_layer(
        "base",
        """
        [feature]
        flag = off
        """,
    )
    store.apply_layer(
        "experiment",
        """
        [feature]
        flag = on
        extra = enabled
        """,
    )
    assert store.query("feature")["feature"]["flag"] == "on"

    removed = store.rollback_layer("experiment")
    assert removed is True
    assert store.rollback_layer("nonexistent") is False

    res = store.query("feature")
    assert res == {"feature": {"flag": "off"}}
