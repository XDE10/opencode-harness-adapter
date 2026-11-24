from r12s2cache import CacheCoordinator


def test_put_get_and_l2_promotion():
    coord = CacheCoordinator(l1_max_size=2)
    coord.put("k1", "v1", now=10.0, ttl=50.0, tags=["t1"])
    coord.put("k2", "v2", now=11.0, ttl=50.0, tags=["t1"])
    coord.put("k3", "v3", now=12.0, ttl=50.0, tags=["t2"])

    assert "k1" not in coord.l1
    assert coord.get("k1", now=15.0) == "v1"
    assert "k1" in coord.l1


def test_tag_invalidation_basic():
    coord = CacheCoordinator(l1_max_size=4)
    coord.put("u:1", {"name": "Ada"}, now=0.0, tags=["users", "tier:gold"])
    coord.put("u:2", {"name": "Bob"}, now=0.0, tags=["users"])

    removed = coord.invalidate_tag("tier:gold", now=1.0)
    assert removed == {"u:1"}
    assert coord.get("u:1", now=1.0) is None
    assert coord.get("u:2", now=1.0) == {"name": "Bob"}
