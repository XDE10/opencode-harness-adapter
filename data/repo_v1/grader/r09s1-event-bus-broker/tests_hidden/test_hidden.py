import pytest
from r09s1bus import Event, EventBroker, TopicPattern, validate_topic


def test_validate_topic_rejects_malformed_topics():
    with pytest.raises(ValueError):
        validate_topic("")
    with pytest.raises(ValueError):
        validate_topic("orders..created")
    with pytest.raises(ValueError):
        validate_topic(".orders.created")
    with pytest.raises(ValueError):
        validate_topic("orders.*.created", allow_wildcards=False)


def test_wildcard_multi_segment_matching_one_or_more():
    pattern = TopicPattern("orders.**.created")
    assert pattern.matches("orders.eu.created") is True
    assert pattern.matches("orders.eu.de.berlin.created") is True
    assert pattern.matches("orders.eu.cancelled") is False


def test_wildcard_multi_segment_matching_zero_segments():
    middle = TopicPattern("orders.**.created")
    assert middle.matches("orders.created") is True

    trailing = TopicPattern("orders.**")
    assert trailing.matches("orders") is True
    assert trailing.matches("orders.eu.created") is True

    leading = TopicPattern("**.created")
    assert leading.matches("created") is True
    assert leading.matches("orders.eu.created") is True


def test_broker_routes_zero_segment_double_wildcard_events():
    broker = EventBroker(max_retries=2, retry_backoff=5)
    seen = []
    broker.subscribe("audit", "audit.**.logged", lambda e: seen.append(e.event_id))

    broker.publish(Event("e1", "audit.logged", {}, published_at=10))
    broker.publish(Event("e2", "audit.auth.user.logged", {}, published_at=11))

    r1 = broker.poll("audit", now=20)
    r2 = broker.poll("audit", now=21)
    assert (r1.processed, r2.processed) == (1, 1)
    assert seen == ["e1", "e2"]


def test_retry_backoff_and_eventual_recovery():
    broker = EventBroker(max_retries=3, retry_backoff=10)
    calls = []

    def flaky_handler(event: Event) -> None:
        calls.append(event.event_id)
        if len(calls) < 3:
            raise RuntimeError(f"temporary failure #{len(calls)}")

    broker.subscribe("workers", "jobs.*", flaky_handler)
    broker.publish(Event("job-1", "jobs.email", {}, published_at=100))

    # 1st attempt at t=100 fails -> next_retry_at = 110
    r1 = broker.poll("workers", now=100)
    assert (r1.processed, r1.dead_lettered, r1.next_offset) == (0, 0, 0)

    # Too early at t=109 -> handler not called
    r_early = broker.poll("workers", now=109)
    assert (r_early.processed, r_early.dead_lettered, r_early.next_offset) == (0, 0, 0)
    assert len(calls) == 1

    # 2nd attempt at t=110 fails -> next_retry_at = 110 + 10*2 = 130
    r2 = broker.poll("workers", now=110)
    assert (r2.processed, r2.dead_lettered, r2.next_offset) == (0, 0, 0)
    assert len(calls) == 2

    # 3rd attempt at t=130 succeeds -> offset advances to 1
    r3 = broker.poll("workers", now=130)
    assert (r3.processed, r3.dead_lettered, r3.next_offset) == (1, 0, 1)
    assert len(calls) == 3
    assert broker.dead_letters == []


def test_dead_letter_record_accuracy_and_offset_advancement():
    broker = EventBroker(max_retries=3, retry_backoff=5)
    processed = []

    def failing_on_bad(event: Event) -> None:
        if event.event_id == "bad-1":
            raise ValueError("corrupt payload")
        processed.append(event.event_id)

    broker.subscribe("ingest", "data.*", failing_on_bad)
    broker.publish(Event("bad-1", "data.csv", {}, published_at=10))
    broker.publish(Event("good-2", "data.json", {}, published_at=11))

    # Attempt 1 fails at t=10 (next retry at 15)
    res1 = broker.poll("ingest", now=10)
    assert (res1.processed, res1.dead_lettered, res1.next_offset) == (0, 0, 0)

    # Attempt 2 fails at t=15 (next retry at 25)
    res2 = broker.poll("ingest", now=15)
    assert (res2.processed, res2.dead_lettered, res2.next_offset) == (0, 0, 0)

    # Attempt 3 fails at t=25 -> moves to DLQ and advances offset to 1
    res3 = broker.poll("ingest", now=25)
    assert (res3.processed, res3.dead_lettered, res3.next_offset) == (0, 1, 1)
    assert len(broker.dead_letters) == 1
    dlq_entry = broker.dead_letters[0]
    assert dlq_entry.group_id == "ingest"
    assert dlq_entry.event.event_id == "bad-1"
    assert dlq_entry.attempts == 3
    assert dlq_entry.last_error == "corrupt payload"
    assert dlq_entry.failed_at == 25

    # Next poll processes good-2 at offset 1 instead of stalling on bad-1
    res4 = broker.poll("ingest", now=26)
    assert (res4.processed, res4.dead_lettered, res4.next_offset) == (1, 0, 2)
    assert processed == ["good-2"]


def test_max_retries_one_dead_letters_on_first_failure():
    broker = EventBroker(max_retries=1, retry_backoff=5)

    def always_fail(event: Event) -> None:
        raise RuntimeError("boom")

    broker.subscribe("fast-fail", "tasks.*", always_fail)
    broker.publish(Event("t1", "tasks.run", {}, published_at=50))

    res = broker.poll("fast-fail", now=50)
    assert (res.processed, res.dead_lettered, res.next_offset) == (0, 1, 1)
    assert len(broker.dead_letters) == 1
    assert broker.dead_letters[0].attempts == 1


def test_independent_consumer_group_offsets():
    broker = EventBroker(max_retries=2, retry_backoff=5)
    g1_events = []
    g2_events = []

    broker.subscribe("g1", "metrics.*", lambda e: g1_events.append(e.event_id))
    broker.subscribe("g2", "metrics.cpu", lambda e: g2_events.append(e.event_id))

    broker.publish(Event("m1", "metrics.mem", {}, published_at=1))
    broker.publish(Event("m2", "metrics.cpu", {}, published_at=2))

    assert broker.poll("g2", now=10).next_offset == 2
    assert g2_events == ["m2"]
    assert broker.get_offset("g1") == 0

    assert broker.poll("g1", now=10).next_offset == 1
    assert broker.poll("g1", now=11).next_offset == 2
    assert g1_events == ["m1", "m2"]
