from r05s3pkg import HierarchicalEnforcer, parse_policy_spec


def test_parse_per_second_policy():
    policy = parse_policy_spec(
        {
            "name": "global-sec",
            "scope": "global",
            "algorithm": "token_bucket",
            "rate": "10/s",
            "burst": 15,
        }
    )
    assert policy.limit == 10
    assert policy.window_seconds == 1.0
    assert policy.burst == 15
    assert policy.refill_rate == 10.0


def test_single_scope_enforcement():
    enforcer = HierarchicalEnforcer()
    enforcer.register_policy(
        {
            "name": "tenant- window",
            "scope": "tenant:acme",
            "algorithm": "sliding_window",
            "rate": "3/10s",
        }
    )
    r1 = enforcer.check_and_consume(["tenant:acme"], cost=2, now=100.0)
    assert r1.allowed is True
    assert r1.remaining_by_policy["tenant- window"] == 1

    r2 = enforcer.check_and_consume(["tenant:acme"], cost=2, now=101.0)
    assert r2.allowed is False
    assert r2.denied_by == "tenant- window"
