import pytest
from quotaguard import QuotaEnforcer, TokenBucketStore, parse_policy


def test_parse_policy_validation_and_defaults():
    p = parse_policy("default_burst", "25/s")
    assert p.limit == 25
    assert p.window_seconds == 1
    assert p.burst_capacity == 25.0

    with pytest.raises(ValueError):
        parse_policy("bad_burst", "25/s burst=10")

    with pytest.raises(ValueError):
        parse_policy("bad_unit", "25/d")


def test_lineage_resolution_and_registration_errors():
    enforcer = QuotaEnforcer()
    p_org = parse_policy("org", "100/s")
    p_team = parse_policy("team", "50/s")

    with pytest.raises(KeyError):
        enforcer.register_tenant("team-a", p_team, parent_id="missing-org")

    enforcer.register_tenant("org-1", p_org)
    enforcer.register_tenant("team-a", p_team, parent_id="org-1")
    assert enforcer.get_lineage("team-a") == ["org-1", "team-a"]


def test_per_second_refill_and_cap():
    enforcer = QuotaEnforcer()
    p = parse_policy("sec", "10/s burst=12")
    enforcer.register_tenant("t1", p)

    d1 = enforcer.check_and_consume("t1", cost=10.0, now=0.0)
    assert d1.allowed is True
    assert d1.remaining_min == 2.0

    d2 = enforcer.check_and_consume("t1", cost=5.0, now=0.5)
    assert d2.allowed is True
    assert d2.remaining_min == pytest.approx(2.0)

    d3 = enforcer.check_and_consume("t1", cost=2.0, now=10.0)
    assert d3.allowed is True
    assert d3.remaining_min == pytest.approx(10.0)


def test_minute_policy_refill_rate_in_store():
    store = TokenBucketStore()
    enforcer = QuotaEnforcer(store=store)
    p_min = parse_policy("per_min", "120/m burst=120")
    enforcer.register_tenant("t-min", p_min)

    assert p_min.refill_rate_per_sec == pytest.approx(2.0)

    d1 = enforcer.check_and_consume("t-min", cost=120.0, now=100.0)
    assert d1.allowed is True
    assert d1.remaining_min == pytest.approx(0.0)

    d2 = enforcer.check_and_consume("t-min", cost=25.0, now=110.0)
    assert d2.allowed is False
    assert d2.blocked_by == "t-min"

    d3 = enforcer.check_and_consume("t-min", cost=20.0, now=110.0)
    assert d3.allowed is True
    assert d3.remaining_min == pytest.approx(0.0)


def test_hour_policy_refill_rate_calculation():
    enforcer = QuotaEnforcer()
    p_hour = parse_policy("per_hour", "3600/h burst=4000")
    enforcer.register_tenant("t-hour", p_hour)

    assert p_hour.refill_rate_per_sec == pytest.approx(1.0)

    enforcer.check_and_consume("t-hour", cost=4000.0, now=0.0)
    denied = enforcer.check_and_consume("t-hour", cost=50.0, now=30.0)
    assert denied.allowed is False

    allowed = enforcer.check_and_consume("t-hour", cost=30.0, now=30.0)
    assert allowed.allowed is True
    assert allowed.remaining_min == pytest.approx(0.0)


def test_child_rejection_does_not_drain_parent_quota():
    store = TokenBucketStore()
    enforcer = QuotaEnforcer(store=store)
    p_org = parse_policy("org_plan", "20/s")
    p_child = parse_policy("child_plan", "5/s")

    enforcer.register_tenant("org", p_org)
    enforcer.register_tenant("child-1", p_child, parent_id="org")
    enforcer.register_tenant("child-2", p_child, parent_id="org")

    res = enforcer.check_and_consume("child-1", cost=8.0, now=0.0)
    assert res.allowed is False
    assert res.blocked_by == "child-1"

    assert store.peek_tokens(p_org, "org", now=0.0) == pytest.approx(20.0)
    assert store.peek_tokens(p_child, "child-1", now=0.0) == pytest.approx(5.0)

    res2 = enforcer.check_and_consume("child-2", cost=5.0, now=0.0)
    assert res2.allowed is True
    assert store.peek_tokens(p_org, "org", now=0.0) == pytest.approx(15.0)


def test_three_level_hierarchy_atomic_rollback_on_leaf_failure():
    store = TokenBucketStore()
    enforcer = QuotaEnforcer(store=store)
    p_root = parse_policy("root", "100/s")
    p_mid = parse_policy("mid", "50/s")
    p_leaf = parse_policy("leaf", "10/s")

    enforcer.register_tenant("root", p_root)
    enforcer.register_tenant("mid", p_mid, parent_id="root")
    enforcer.register_tenant("leaf", p_leaf, parent_id="mid")

    ok = enforcer.check_and_consume("leaf", cost=6.0, now=1.0)
    assert ok.allowed is True
    assert ok.remaining_min == pytest.approx(4.0)

    fail = enforcer.check_and_consume("leaf", cost=5.0, now=1.0)
    assert fail.allowed is False
    assert fail.blocked_by == "leaf"

    assert store.peek_tokens(p_root, "root", now=1.0) == pytest.approx(94.0)
    assert store.peek_tokens(p_mid, "mid", now=1.0) == pytest.approx(44.0)
    assert store.peek_tokens(p_leaf, "leaf", now=1.0) == pytest.approx(4.0)


def test_parent_rejection_blocks_child_and_reports_parent():
    store = TokenBucketStore()
    enforcer = QuotaEnforcer(store=store)
    p_org = parse_policy("org_tight", "6/s")
    p_team = parse_policy("team_wide", "10/s")

    enforcer.register_tenant("org", p_org)
    enforcer.register_tenant("team-1", p_team, parent_id="org")
    enforcer.register_tenant("team-2", p_team, parent_id="org")

    d1 = enforcer.check_and_consume("team-1", cost=5.0, now=0.0)
    assert d1.allowed is True
    assert d1.remaining_min == pytest.approx(1.0)

    d2 = enforcer.check_and_consume("team-2", cost=3.0, now=0.0)
    assert d2.allowed is False
    assert d2.blocked_by == "org"
    assert store.peek_tokens(p_team, "team-2", now=0.0) == pytest.approx(10.0)
