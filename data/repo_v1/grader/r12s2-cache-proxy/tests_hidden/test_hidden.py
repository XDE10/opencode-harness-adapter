from r12s2cache import CacheCoordinator, LRUTier, TagRegistry


def test_version_increment_and_ttl_expiry_reset():
    coord = CacheCoordinator(l1_max_size=3)
    e1 = coord.put("item:1", "alpha", now=100.0, ttl=10.0, tags=["a"])
    assert e1.version == 1

    e2 = coord.put("item:1", "beta", now=105.0, ttl=10.0, tags=["a"])
    assert e2.version == 2

    assert coord.get("item:1", now=120.0) is None
    e3 = coord.put("item:1", "gamma", now=121.0, ttl=10.0, tags=["a"])
    assert e3.version == 1


def test_lru_purges_expired_before_evicting_live_entries():
    coord = CacheCoordinator(l1_max_size=2)
    coord.put("k1", "v1", now=0.0, ttl=5.0)
    coord.put("k2", "v2", now=0.0, ttl=50.0)
    coord.put("k3", "v3", now=10.0, ttl=50.0)

    assert "k2" in coord.l1
    assert "k3" in coord.l1
    assert "k1" not in coord.l1


def test_query_by_tags_match_all_and_match_any():
    coord = CacheCoordinator(l1_max_size=4)
    coord.put("p1", 10, now=0.0, tags=["region:eu", "active"])
    coord.put("p2", 20, now=0.0, tags=["region:us", "active"])
    coord.put("p3", 30, now=0.0, ttl=5.0, tags=["region:eu", "active"])

    assert coord.query_by_tags(["region:eu", "active"], now=2.0, match_all=True) == {
        "p1": 10,
        "p3": 30,
    }
    assert coord.query_by_tags(["region:eu", "active"], now=6.0, match_all=True) == {
        "p1": 10,
    }
    assert coord.query_by_tags(["region:eu", "region:us"], now=6.0, match_all=False) == {
        "p1": 10,
        "p2": 20,
    }


def test_overwrite_key_replaces_old_tags_in_registry():
    coord = CacheCoordinator(l1_max_size=4)
    coord.put("doc:1", "v1", now=0.0, tags=["draft", "team:core"])
    coord.put("doc:1", "v2", now=1.0, tags=["published", "team:core"])

    assert coord.registry.tags_for_key("doc:1") == {"published", "team:core"}
    assert coord.registry.keys_for_tag("draft") == set()
    assert coord.query_by_tags(["draft"], now=2.0) == {}


def test_invalidating_removed_tag_does_not_evict_updated_key():
    coord = CacheCoordinator(l1_max_size=4)
    coord.put("acct:1", "initial", now=0.0, tags=["pending", "v1"])
    coord.put("acct:1", "approved", now=5.0, tags=["active", "v2"])

    invalidated = coord.invalidate_tag("pending", now=6.0)
    assert invalidated == set()
    assert coord.get("acct:1", now=6.0) == "approved"


def test_overwriting_key_with_empty_tags_clears_all_tag_bindings():
    reg = TagRegistry()
    reg.bind("k1", ["t1", "t2"])
    reg.bind("k1", [])

    assert reg.tags_for_key("k1") == set()
    assert reg.keys_for_tag("t1") == set()
    assert reg.keys_for_tag("t2") == set()


def test_batch_put_rollback_restores_overwritten_key_value_version_and_tags():
    coord = CacheCoordinator(l1_max_size=4)
    coord.put("k1", "original_v1", now=10.0, ttl=100.0, tags=["stable", "g1"])
    coord.put("k1", "original_v2", now=20.0, ttl=100.0, tags=["stable", "g1"])

    ok = coord.batch_put(
        items=[
            ("k1", "temp_new", 50.0, ["dirty"]),
            ("k2", "fresh", 50.0, ["dirty"]),
            ("k3", "bad_val", 50.0, ["dirty"]),
        ],
        now=30.0,
        validator=lambda k, v: v != "bad_val",
    )

    assert ok is False
    assert coord.get("k1", now=31.0) == "original_v2"
    assert coord.l2["k1"].version == 2
    assert coord.l2["k1"].expires_at == 120.0
    assert coord.get("k2", now=31.0) is None
    assert coord.query_by_tags(["stable"], now=31.0) == {"k1": "original_v2"}
    assert coord.query_by_tags(["dirty"], now=31.0) == {}


def test_batch_put_rollback_handles_repeated_key_within_same_batch():
    coord = CacheCoordinator(l1_max_size=2)
    coord.put("a", 1, now=0.0, ttl=30.0, tags=["init"])
    coord.put("b", 2, now=1.0, ttl=30.0, tags=["init"])

    ok = coord.batch_put(
        items=[
            ("a", 10, 40.0, ["step1"]),
            ("a", 20, 50.0, ["step2"]),
            ("c", 30, 50.0, ["step3"]),
            ("d", -1, 50.0, ["fail"]),
        ],
        now=5.0,
        validator=lambda k, v: v > 0,
    )

    assert ok is False
    assert coord.get("a", now=6.0) == 1
    assert coord.l2["a"].version == 1
    assert coord.registry.tags_for_key("a") == {"init"}
    assert coord.get("c", now=6.0) is None
    assert "a" in coord.l1
    assert "b" in coord.l1


def test_batch_put_success_commits_all_entries():
    coord = CacheCoordinator(l1_max_size=4)
    coord.put("x", 100, now=0.0, tags=["old"])

    ok = coord.batch_put(
        items=[
            ("x", 200, 20.0, ["new"]),
            ("y", 300, 20.0, ["new"]),
        ],
        now=5.0,
        validator=lambda k, v: v >= 200,
    )
    assert ok is True
    assert coord.get("x", now=6.0) == 200
    assert coord.get("y", now=6.0) == 300
    assert coord.query_by_tags(["new"], now=6.0) == {"x": 200, "y": 300}
    assert coord.query_by_tags(["old"], now=6.0) == {}
