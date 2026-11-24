from r09s2bus import EventBroker, topic_matches


def test_exact_and_single_wildcard_match():
    assert topic_matches("orders.eu.created", "orders.eu.created") is True
    assert topic_matches("orders.+.created", "orders.eu.created") is True
    assert topic_matches("orders.+.created", "orders.eu.updated") is False


def test_basic_publish_and_poll():
    broker = EventBroker()
    seen = []
    broker.register_group("g1", ["orders.#"], lambda ev: seen.append(ev.offset) or True)

    broker.publish("orders.eu.created", {"id": 1}, timestamp=100)
    broker.publish("inventory.eu.updated", {"id": 2}, timestamp=101)
    broker.publish("orders.us.paid", {"id": 3}, timestamp=102)

    delivered = broker.poll_group("g1", now=200)
    assert [e.offset for e in delivered] == [1, 3]
    assert broker.get_group("g1").committed_offset == 3
