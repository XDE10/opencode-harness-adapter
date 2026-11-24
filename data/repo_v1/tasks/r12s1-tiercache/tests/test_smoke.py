from tiercache import TierCacheCoordinator, parse_cache_directive


def test_basic_directive_parse():
    policy = parse_cache_directive("max-age=120; tags=users,profile; tier=L1")
    assert policy.ttl == 120
    assert policy.tags == frozenset({"users", "profile"})
    assert policy.tier == "L1"
    assert policy.no_store is False


def test_coordinator_basic_put_and_fetch():
    coord = TierCacheCoordinator(l1_capacity=2, l2_capacity=4)
    stored = coord.put_with_header("user:1", {"name": "Ada"}, "max-age=30; tags=users", now=100)
    assert stored is True
    assert coord.fetch("user:1", now=110) == ({"name": "Ada"}, "L1")
    assert coord.fetch("user:1", now=135) == ({"name": "Ada"}, "ORIGIN")
