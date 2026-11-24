from quotaguard import QuotaEnforcer, parse_policy


def test_single_tenant_per_second_policy():
    policy = parse_policy("api_sec", "10/s burst=15")
    enforcer = QuotaEnforcer()
    enforcer.register_tenant("tenant-1", policy)

    decision = enforcer.check_and_consume("tenant-1", cost=5.0, now=100.0)
    assert decision.allowed is True
    assert decision.blocked_by is None
    assert decision.remaining_min == 10.0


def test_single_tenant_rejection_when_exhausted():
    policy = parse_policy("strict_sec", "5/s")
    enforcer = QuotaEnforcer()
    enforcer.register_tenant("tenant-1", policy)

    first = enforcer.check_and_consume("tenant-1", cost=4.0, now=0.0)
    assert first.allowed is True
    assert first.remaining_min == 1.0

    second = enforcer.check_and_consume("tenant-1", cost=2.0, now=0.0)
    assert second.allowed is False
    assert second.blocked_by == "tenant-1"
