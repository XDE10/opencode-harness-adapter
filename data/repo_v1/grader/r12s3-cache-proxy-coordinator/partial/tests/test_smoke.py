from r12s3cache import MultiTierCache, parse_directive


def test_basic_put_and_get():
    cache = MultiTierCache(capacity=2, policy="lru", default_ttl=30)
    assert cache.put("k1", {"user": "alice"}, "max-age=50, tags=auth", now=10) is True
    assert cache.get("k1", now=20) == {"user": "alice"}
    assert cache.get("k1", now=60) is None


def test_single_tag_invalidation():
    cache = MultiTierCache(capacity=2, policy="lru")
    cache.put("a", 100, "max-age=60, tags=group1", now=0)
    cache.put("b", 200, "max-age=60, tags=group2", now=0)
    removed = cache.invalidate_tag("group1")
    assert removed == 1
    assert cache.get("a", now=5) is None
    assert cache.get("b", now=5) == 200


def test_simple_lru_eviction_and_l2_promotion():
    cache = MultiTierCache(capacity=2, policy="lru")
    cache.put("k1", "v1", "max-age=100", now=1)
    cache.put("k2", "v2", "max-age=100", now=2)
    cache.get("k1", now=3)
    cache.put("k3", "v3", "max-age=100", now=4)
    assert "k2" not in cache.l1
    assert "k1" in cache.l1
    assert cache.get("k2", now=5) == "v2"
    assert "k2" in cache.l1
