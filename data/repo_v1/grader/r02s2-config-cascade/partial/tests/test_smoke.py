from r02s2pkg import ConfigStore


def test_basic_layers_and_interpolation():
    store = ConfigStore(env={"REGION": "us-east-1"})
    store.apply_layer(
        "base",
        """
        [app]
        name = billing
        region = ${ENV:REGION:-us-west-2}
        endpoint = https://${app.name}.${app.region}.internal
        """,
    )
    snap = store.snapshot()
    assert snap["app"]["name"] == "billing"
    assert snap["app"]["region"] == "us-east-1"
    assert snap["app"]["endpoint"] == "https://billing.us-east-1.internal"


def test_basic_inheritance_and_query():
    store = ConfigStore()
    store.apply_layer(
        "defaults",
        """
        [service.base]
        timeout = 30
        retries = 3

        [service.api : service.base]
        timeout = 10
        port = 8080
        """,
    )
    res = store.query("service.*", key_prefix="time")
    assert res == {
        "service.api": {"timeout": "10"},
        "service.base": {"timeout": "30"},
    }
