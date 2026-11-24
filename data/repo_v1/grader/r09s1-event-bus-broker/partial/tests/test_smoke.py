from r09s1bus import Event, EventBroker, TopicPattern


def test_single_wildcard_match():
    pattern = TopicPattern("orders.*.created")
    assert pattern.matches("orders.eu.created") is True
    assert pattern.matches("orders.us.created") is True
    assert pattern.matches("orders.eu.cancelled") is False


def test_publish_and_poll_happy_path():
    broker = EventBroker(max_retries=3, retry_backoff=5)
    received = []
    broker.subscribe("billing", "payments.*.settled", lambda e: received.append(e.event_id))

    broker.publish(Event("e1", "orders.eu.created", {"amount": 10}, published_at=100))
    broker.publish(Event("e2", "payments.eu.settled", {"amount": 25}, published_at=101))

    res = broker.poll("billing", now=105)
    assert res.processed == 1
    assert res.dead_lettered == 0
    assert res.next_offset == 2
    assert received == ["e2"]
