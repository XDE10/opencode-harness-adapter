import pytest

from r09s3pkg import EventBroker, compile_pattern


def test_validation_rejects_invalid_topics_and_patterns():
    with pytest.raises(ValueError):
        compile_pattern("")
    with pytest.raises(ValueError):
        compile_pattern("orders..eu")
    with pytest.raises(ValueError):
        compile_pattern(".orders.eu")

    broker = EventBroker()
    with pytest.raises(ValueError):
        broker.publish("orders.*.created", {"id": 1}, timestamp=1)
    with pytest.raises(ValueError):
        broker.publish("orders.#", {"id": 1}, timestamp=1)
    with pytest.raises(ValueError):
        broker.publish("orders.eu.", {"id": 1}, timestamp=1)


def test_exact_and_single_level_wildcard_matching():
    pat = compile_pattern("payments.*.settled")
    assert pat.matches("payments.card.settled") is True
    assert pat.matches("payments.ach.settled") is True
    assert pat.matches("payments.settled") is False
    assert pat.matches("payments.card.eu.settled") is False


def test_independent_consumer_groups_happy_path():
    broker = EventBroker(max_retries=2)
    broker.register_group("g_eu", "orders.eu.*")
    broker.register_group("g_us", "orders.us.*")

    broker.publish("orders.eu.created", {"n": 1}, timestamp=10)
    broker.publish("orders.us.created", {"n": 2}, timestamp=20)
    broker.publish("orders.eu.shipped", {"n": 3}, timestamp=30)

    eu_events = broker.poll_and_process("g_eu", lambda e: True, now=50)
    us_events = broker.poll_and_process("g_us", lambda e: True, now=50)

    assert [e.offset for e in eu_events] == [0, 2]
    assert [e.offset for e in us_events] == [1]
    assert broker.committed_offset("g_eu") == 3
    assert broker.committed_offset("g_us") == 3


def test_multilevel_hash_wildcard_zero_and_trailing_segments():
    pat = compile_pattern("orders.#")
    assert pat.matches("orders") is True
    assert pat.matches("orders.eu") is True
    assert pat.matches("orders.eu.west.created") is True
    assert pat.matches("invoices.eu") is False


def test_multilevel_hash_wildcard_middle_and_repeated_tokens():
    pat = compile_pattern("orders.#.created")
    assert pat.matches("orders.created") is True
    assert pat.matches("orders.eu.created") is True
    assert pat.matches("orders.eu.west.created") is True
    assert pat.matches("orders.created.created") is True
    assert pat.matches("orders.eu.created.v2") is False

    pat_combined = compile_pattern("*.#.audit.*")
    assert pat_combined.matches("svc.audit.ok") is True
    assert pat_combined.matches("svc.a.b.audit.ok") is True
    assert pat_combined.matches("svc.a.b.audit") is False


def test_failed_event_does_not_replay_later_acked_events_and_holds_committed_offset():
    broker = EventBroker(max_retries=3)
    broker.register_group("workers", "jobs.*")

    broker.publish("jobs.a", {"id": "a"}, timestamp=100)
    broker.publish("jobs.b", {"id": "b"}, timestamp=101)
    broker.publish("jobs.c", {"id": "c"}, timestamp=102)

    seen_calls: list[int] = []

    def first_poll_handler(ev):
        seen_calls.append(ev.offset)
        return ev.offset != 0

    acked_1 = broker.poll_and_process("workers", first_poll_handler, now=200)
    assert [e.offset for e in acked_1] == [1, 2]
    assert seen_calls == [0, 1, 2]
    assert broker.committed_offset("workers") == 0
    assert len(broker.pending_retries("workers")) == 1
    assert broker.pending_retries("workers")[0].next_retry_at == 210

    seen_calls_before_due: list[int] = []
    acked_2 = broker.poll_and_process(
        "workers",
        lambda ev: seen_calls_before_due.append(ev.offset) or True,
        now=205,
    )
    assert acked_2 == []
    assert seen_calls_before_due == []
    assert broker.committed_offset("workers") == 0

    seen_calls_on_retry: list[int] = []
    acked_3 = broker.poll_and_process(
        "workers",
        lambda ev: seen_calls_on_retry.append(ev.offset) or True,
        now=210,
    )
    assert [e.offset for e in acked_3] == [0]
    assert seen_calls_on_retry == [0]
    assert broker.pending_retries("workers") == []
    assert broker.committed_offset("workers") == 3


def test_retry_backoff_and_dlq_advances_committed_offset():
    broker = EventBroker(max_retries=2)
    broker.register_group("Fulfillment", "orders.*")

    broker.publish("orders.bad", {"id": 1}, timestamp=10)
    broker.publish("orders.good", {"id": 2}, timestamp=11)

    # Attempt 1 fails at now=100 -> retry scheduled for 110 (attempts=1)
    acked = broker.poll_and_process("Fulfillment", lambda ev: ev.offset == 1, now=100)
    assert [e.offset for e in acked] == [1]
    assert broker.committed_offset("Fulfillment") == 0
    assert broker.pending_retries("Fulfillment")[0].attempts == 1
    assert broker.pending_retries("Fulfillment")[0].next_retry_at == 110

    # Attempt 2 fails at now=110 -> retry scheduled for 130 (attempts=2)
    acked = broker.poll_and_process("Fulfillment", lambda ev: False, now=110)
    assert acked == []
    assert broker.committed_offset("Fulfillment") == 0
    assert broker.pending_retries("Fulfillment")[0].attempts == 2
    assert broker.pending_retries("Fulfillment")[0].next_retry_at == 130
    assert broker.dead_letters("Fulfillment") == []

    # Attempt 3 fails at now=130 -> exceeds max_retries=2 -> moved to DLQ
    acked = broker.poll_and_process("Fulfillment", lambda ev: False, now=130)
    assert acked == []
    assert broker.pending_retries("Fulfillment") == []
    dlq = broker.dead_letters("Fulfillment")
    assert len(dlq) == 1
    assert dlq[0].event.offset == 0
    assert dlq[0].attempts == 3
    assert dlq[0].failed_at == 130
    assert broker.committed_offset("Fulfillment") == 2


def test_cross_module_wildcard_subscription_with_out_of_order_retries():
    broker = EventBroker(max_retries=2)
    broker.register_group("analytics", "metrics.#.latency")

    broker.publish("metrics.latency", {"v": 10}, timestamp=1)
    broker.publish("metrics.api.eu.latency", {"v": 20}, timestamp=2)
    broker.publish("metrics.api.eu.throughput", {"v": 99}, timestamp=3)
    broker.publish("metrics.db.latency", {"v": 30}, timestamp=4)

    # Fail offset 1 only; ack offsets 0 and 3
    acked = broker.poll_and_process(
        "analytics",
        lambda ev: ev.offset != 1,
        now=50,
    )
    assert [e.offset for e in acked] == [0, 3]
    assert broker.committed_offset("analytics") == 1

    # Now succeed on retry at now=60
    acked_retry = broker.poll_and_process(
        "analytics",
        lambda ev: True,
        now=60,
    )
    assert [e.offset for e in acked_retry] == [1]
    assert broker.committed_offset("analytics") == 4
