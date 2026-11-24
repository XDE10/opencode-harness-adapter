from r09s2bus import EventBroker, filter_matching_patterns, topic_matches


def test_single_level_and_invalid_patterns():
    assert topic_matches("billing.+.invoice", "billing.eu.invoice") is True
    assert topic_matches("billing.+.invoice", "billing.eu.west.invoice") is False
    assert topic_matches("", "billing.eu") is False
    assert topic_matches("billing..eu", "billing.eu") is False


def test_independent_consumer_groups_happy_path():
    broker = EventBroker()
    g1_events = []
    g2_events = []
    broker.register_group("g1", ["payments.+.settled"], lambda e: g1_events.append(e.offset) or True)
    broker.register_group("g2", ["shipments.#"], lambda e: g2_events.append(e.offset) or True)

    broker.publish("payments.us.settled", {"amount": 50}, timestamp=10)
    broker.publish("shipments.us.dispatched", {"box": 1}, timestamp=20)
    broker.publish("payments.eu.settled", {"amount": 70}, timestamp=30)

    assert [e.offset for e in broker.poll_group("g1", now=100)] == [1, 3]
    assert [e.offset for e in broker.poll_group("g2", now=100)] == [2]
    assert broker.get_group("g1").committed_offset == 3
    assert broker.get_group("g2").committed_offset == 3


def test_dlq_backoff_and_max_retries_exhaustion():
    broker = EventBroker(max_retries=3, backoff_seconds=10)
    broker.register_group("g1", ["jobs.run"], lambda e: False)
    broker.publish("jobs.run", {"job": 1}, timestamp=50)

    assert broker.poll_group("g1", now=100) == []
    dlq = broker.get_dead_letters("g1")
    assert len(dlq) == 1
    assert dlq[0].attempts == 1
    assert dlq[0].next_retry_at == 110
    assert dlq[0].permanently_failed is False

    # Not due yet at now=105
    assert broker.retry_dead_letters("g1", now=105) == []
    assert broker.get_dead_letters("g1")[0].attempts == 1

    # Attempt 2 at now=110 -> next_retry_at = 110 + 10*2 = 130
    assert broker.retry_dead_letters("g1", now=110) == []
    entry2 = broker.get_dead_letters("g1")[0]
    assert entry2.attempts == 2
    assert entry2.next_retry_at == 130
    assert entry2.permanently_failed is False

    # Attempt 3 at now=130 -> reaches max_retries=3 -> permanently_failed
    assert broker.retry_dead_letters("g1", now=130) == []
    entry3 = broker.get_dead_letters("g1")[0]
    assert entry3.attempts == 3
    assert entry3.permanently_failed is True


def test_multilevel_wildcard_zero_and_mid_segments():
    assert topic_matches("orders.#", "orders") is True
    assert topic_matches("orders.#", "orders.eu") is True
    assert topic_matches("orders.#.failed", "orders.failed") is True
    assert topic_matches("orders.#.failed", "orders.eu.west.failed") is True
    assert topic_matches("#.alert.+", "alert.critical") is True
    assert topic_matches("#.alert.+", "prod.eu.alert.critical") is True
    assert topic_matches("#.alert.+", "prod.eu.alert") is False


def test_filter_matching_patterns_with_complex_wildcards():
    patterns = [
        "metrics.#.latency",
        "metrics.+.latency",
        "metrics.#",
        "logs.#.error",
    ]
    matched_zero = filter_matching_patterns(patterns, "metrics.latency")
    assert matched_zero == ["metrics.#.latency", "metrics.#"]

    matched_multi = filter_matching_patterns(patterns, "metrics.api.edge.latency")
    assert matched_multi == ["metrics.#.latency", "metrics.#"]


def test_broker_routing_with_mid_pattern_hash_wildcard():
    broker = EventBroker()
    received = []
    broker.register_group("alerts", ["system.#.critical"], lambda e: received.append(e.offset) or True)

    broker.publish("system.critical", {"node": "root"}, timestamp=1)
    broker.publish("system.db.primary.critical", {"node": "db1"}, timestamp=2)
    broker.publish("system.db.primary.warning", {"node": "db1"}, timestamp=3)

    delivered = broker.poll_group("alerts", now=10)
    assert [e.offset for e in delivered] == [1, 2]


def test_poll_stops_on_first_failure_and_holds_committed_offset():
    broker = EventBroker(max_retries=3, backoff_seconds=10)
    attempted = []

    def handler(event):
        attempted.append(event.offset)
        return event.offset != 2

    broker.register_group("g_order", ["orders.+"], handler)
    broker.publish("orders.created", {"n": 1}, timestamp=10)
    broker.publish("orders.validated", {"n": 2}, timestamp=11)
    broker.publish("orders.shipped", {"n": 3}, timestamp=12)

    delivered = broker.poll_group("g_order", now=100)
    assert [e.offset for e in delivered] == [1]
    assert attempted == [1, 2]
    assert broker.get_group("g_order").committed_offset == 1
    assert [d.event.offset for d in broker.get_dead_letters("g_order")] == [2]

    # Polling again while offset 2 is still in DLQ must not skip offset 2 or deliver offset 3
    assert broker.poll_group("g_order", now=105) == []
    assert broker.get_group("g_order").committed_offset == 1


def test_dlq_retry_recovery_advances_offset_and_unblocks_subsequent_poll():
    broker = EventBroker(max_retries=3, backoff_seconds=10)
    should_fail_offset_2 = True

    def handler(event):
        if event.offset == 2 and should_fail_offset_2:
            raise RuntimeError("transient_db_timeout")
        return True

    broker.register_group("g_recover", ["orders.+"], handler)
    broker.publish("orders.created", {"n": 1}, timestamp=10)
    broker.publish("orders.validated", {"n": 2}, timestamp=11)
    broker.publish("orders.shipped", {"n": 3}, timestamp=12)

    assert [e.offset for e in broker.poll_group("g_recover", now=100)] == [1]
    assert broker.get_group("g_recover").committed_offset == 1

    should_fail_offset_2 = False
    recovered = broker.retry_dead_letters("g_recover", now=110)
    assert [e.offset for e in recovered] == [2]
    assert broker.get_dead_letters("g_recover") == []
    assert broker.get_group("g_recover").committed_offset == 2

    # Next poll now delivers offset 3 and commits offset 3
    subsequent = broker.poll_group("g_recover", now=115)
    assert [e.offset for e in subsequent] == [3]
    assert broker.get_group("g_recover").committed_offset == 3


def test_rollback_to_purges_dlq_and_replays_events():
    broker = EventBroker(max_retries=3, backoff_seconds=10)
    fail_second = True
    seen = []

    def handler(event):
        seen.append(event.offset)
        if event.offset == 2 and fail_second:
            return False
        return True

    broker.register_group("g_rb", ["orders.+"], handler)
    broker.publish("orders.a", {}, timestamp=1)
    broker.publish("orders.b", {}, timestamp=2)
    broker.publish("orders.c", {}, timestamp=3)

    broker.poll_group("g_rb", now=50)
    assert len(broker.get_dead_letters("g_rb")) == 1

    # Rollback to offset 0 purges DLQ entry for offset 2 and replays 1, 2, 3 cleanly
    fail_second = False
    seen.clear()
    broker.rollback_to("g_rb", target_offset=0)
    assert broker.get_dead_letters("g_rb") == []
    assert broker.get_group("g_rb").committed_offset == 0

    replayed = broker.poll_group("g_rb", now=60)
    assert [e.offset for e in replayed] == [1, 2, 3]
    assert broker.get_group("g_rb").committed_offset == 3
