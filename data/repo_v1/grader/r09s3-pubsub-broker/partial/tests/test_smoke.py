from r09s3pkg import EventBroker, compile_pattern


def test_single_wildcard_matching():
    pat = compile_pattern("orders.*.created")
    assert pat.matches("orders.eu.created") is True
    assert pat.matches("orders.us.created") is True
    assert pat.matches("orders.eu.updated") is False


def test_basic_publish_and_poll():
    broker = EventBroker(max_retries=2)
    broker.register_group("billing", "orders.*.created")
    e0 = broker.publish("orders.eu.created", {"id": 101}, timestamp=100)
    broker.publish("orders.eu.cancelled", {"id": 102}, timestamp=101)

    acked = broker.poll_and_process("billing", lambda ev: True, now=105)
    assert [e.offset for e in acked] == [e0.offset]
    assert broker.committed_offset("billing") == 2
