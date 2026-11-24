import pytest

from r05s3pkg import HierarchicalEnforcer, parse_policy_spec


def test_policy_validation_errors():
    with pytest.raises(ValueError):
        parse_policy_spec(
            {"name": "p1", "scope": "global", "algorithm": "unknown", "rate": "10/s"}
        )
    with pytest.raises(ValueError):
        parse_policy_spec(
            {"name": "p1", "scope": "global", "algorithm": "token_bucket", "rate": "0/5s"}
        )
    with pytest.raises(ValueError):
        parse_policy_spec(
            {
                "name": "p1",
                "scope": "global",
                "algorithm": "token_bucket",
                "rate": "10/s",
                "burst": 0,
            }
        )


def test_token_bucket_refill_and_retry_after():
    enforcer = HierarchicalEnforcer()
    enforcer.register_policy(
        {
            "name": "tb-sec",
            "scope": "tenant:t1",
            "algorithm": "token_bucket",
            "rate": "10/10s",
            "burst": 5,
        }
    )
    res1 = enforcer.check_and_consume(["tenant:t1"], cost=5, now=0.0)
    assert res1.allowed is True
    assert res1.remaining_by_policy["tb-sec"] == 0

    res2 = enforcer.check_and_consume(["tenant:t1"], cost=3, now=1.0)
    assert res2.allowed is False
    assert res2.denied_by == "tb-sec"
    assert pytest.approx(res2.retry_after, rel=1e-4) == 2.0

    res3 = enforcer.check_and_consume(["tenant:t1"], cost=3, now=3.0)
    assert res3.allowed is True
    assert res3.remaining_by_policy["tb-sec"] == 0


def test_sliding_window_expiration():
    enforcer = HierarchicalEnforcer()
    enforcer.register_policy(
        {
            "name": "sw-sec",
            "scope": "tenant:t1",
            "algorithm": "sliding_window",
            "rate": "4/10s",
        }
    )
    assert enforcer.check_and_consume(["tenant:t1"], cost=2, now=0.0).allowed is True
    assert enforcer.check_and_consume(["tenant:t1"], cost=2, now=4.0).allowed is True

    denied = enforcer.check_and_consume(["tenant:t1"], cost=1, now=5.0)
    assert denied.allowed is False
    assert pytest.approx(denied.retry_after, rel=1e-4) == 5.0

    allowed_after = enforcer.check_and_consume(["tenant:t1"], cost=2, now=10.0)
    assert allowed_after.allowed is True
    assert allowed_after.remaining_by_policy["sw-sec"] == 0


def test_parse_rate_with_explicit_multi_unit_counts():
    p_min = parse_policy_spec(
        {
            "name": "min-policy",
            "scope": "tenant:acme",
            "algorithm": "token_bucket",
            "rate": "120/2m",
        }
    )
    assert p_min.limit == 120
    assert p_min.window_seconds == 120.0
    assert pytest.approx(p_min.refill_rate) == 1.0

    p_hour = parse_policy_spec(
        {
            "name": "hour-policy",
            "scope": "tenant:acme",
            "algorithm": "sliding_window",
            "rate": "3600/1h",
        }
    )
    assert p_hour.limit == 3600
    assert p_hour.window_seconds == 3600.0
    assert pytest.approx(p_hour.refill_rate) == 1.0


def test_sliding_window_with_explicit_minute_count_enforces_full_minute():
    enforcer = HierarchicalEnforcer()
    enforcer.register_policy(
        {
            "name": "api-1m",
            "scope": "tenant:acme",
            "algorithm": "sliding_window",
            "rate": "2/1m",
        }
    )
    assert enforcer.check_and_consume(["tenant:acme"], cost=2, now=10.0).allowed is True

    # At t=25.0 (only 15 seconds later, well inside the 1-minute window), quota must still be exhausted
    attempt = enforcer.check_and_consume(["tenant:acme"], cost=1, now=25.0)
    assert attempt.allowed is False
    assert attempt.denied_by == "api-1m"
    assert pytest.approx(attempt.retry_after) == 45.0


def test_token_bucket_with_explicit_hour_count_refill_rate():
    enforcer = HierarchicalEnforcer()
    enforcer.register_policy(
        {
            "name": "hourly-jobs",
            "scope": "tenant:acme",
            "algorithm": "token_bucket",
            "rate": "60/1h",
            "burst": 2,
        }
    )
    # Drain burst of 2 at t=0
    assert enforcer.check_and_consume(["tenant:acme"], cost=2, now=0.0).allowed is True
    # At 60/1h = 1 token per 60 seconds, after 10 seconds 0 tokens have refilled
    early = enforcer.check_and_consume(["tenant:acme"], cost=1, now=10.0)
    assert early.allowed is False
    assert pytest.approx(early.retry_after) == 50.0


def test_hierarchical_denial_does_not_drain_parent_token_bucket():
    enforcer = HierarchicalEnforcer()
    enforcer.register_policy(
        {
            "name": "global-tb",
            "scope": "global",
            "algorithm": "token_bucket",
            "rate": "10/100s",
            "burst": 10,
        }
    )
    enforcer.register_policy(
        {
            "name": "tenant-tb",
            "scope": "tenant:acme",
            "algorithm": "token_bucket",
            "rate": "5/100s",
            "burst": 5,
        }
    )
    enforcer.register_policy(
        {
            "name": "user-tb",
            "scope": "user:alice",
            "algorithm": "token_bucket",
            "rate": "2/100s",
            "burst": 2,
        }
    )

    # Alice uses her 2 tokens
    r1 = enforcer.check_and_consume(["global", "tenant:acme", "user:alice"], cost=2, now=0.0)
    assert r1.allowed is True
    assert r1.remaining_by_policy == {"global-tb": 8, "tenant-tb": 3, "user-tb": 0}

    # Alice makes 3 rejected attempts; global and tenant:acme must NOT lose tokens
    for _ in range(3):
        denied = enforcer.check_and_consume(["global", "tenant:acme", "user:alice"], cost=1, now=0.0)
        assert denied.allowed is False
        assert denied.denied_by == "user-tb"

    rem = enforcer.get_remaining(["global", "tenant:acme", "user:alice"], now=0.0)
    assert rem == {"global-tb": 8, "tenant-tb": 3, "user-tb": 0}

    # Another user in tenant:acme can still consume the remaining 3 tenant tokens
    r_bob = enforcer.check_and_consume(["global", "tenant:acme", "user:bob"], cost=3, now=0.0)
    assert r_bob.allowed is True
    assert r_bob.remaining_by_policy["tenant-tb"] == 0
    assert r_bob.remaining_by_policy["global-tb"] == 5


def test_hierarchical_denial_does_not_pollute_parent_sliding_window():
    enforcer = HierarchicalEnforcer()
    enforcer.register_policy(
        {
            "name": "tenant-sw",
            "scope": "tenant:acme",
            "algorithm": "sliding_window",
            "rate": "4/60s",
        }
    )
    enforcer.register_policy(
        {
            "name": "user-sw",
            "scope": "user:alice",
            "algorithm": "sliding_window",
            "rate": "1/60s",
        }
    )

    assert enforcer.check_and_consume(["tenant:acme", "user:alice"], cost=1, now=1.0).allowed is True

    # Denied on user:alice
    denied = enforcer.check_and_consume(["tenant:acme", "user:alice"], cost=1, now=2.0)
    assert denied.allowed is False
    assert denied.denied_by == "user-sw"

    # Tenant still has 3 units left out of 4
    rem = enforcer.get_remaining(["tenant:acme", "user:alice"], now=2.0)
    assert rem["tenant-sw"] == 3
    assert rem["user-sw"] == 0


def test_same_scope_multi_policy_atomicity():
    enforcer = HierarchicalEnforcer()
    enforcer.register_policy(
        {
            "name": "short-burst",
            "scope": "tenant:acme",
            "algorithm": "token_bucket",
            "rate": "10/10s",
            "burst": 10,
        }
    )
    enforcer.register_policy(
        {
            "name": "strict-window",
            "scope": "tenant:acme",
            "algorithm": "sliding_window",
            "rate": "2/60s",
        }
    )

    # Request of cost=3 passes short-burst (10 >= 3) but fails strict-window (2 < 3)
    res = enforcer.check_and_consume(["tenant:acme"], cost=3, now=0.0)
    assert res.allowed is False
    assert res.denied_by == "strict-window"

    # short-burst must still have all 10 tokens untouched
    rem = enforcer.get_remaining(["tenant:acme"], now=0.0)
    assert rem["short-burst"] == 10
    assert rem["strict-window"] == 2
