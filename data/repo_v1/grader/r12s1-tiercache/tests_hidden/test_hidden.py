import pytest
from tiercache import CachePolicy, TierCacheCoordinator, TierStore, parse_cache_directive


def test_parse_empty_and_defaults():
    policy = parse_cache_directive("", default_ttl=45)
    assert policy == CachePolicy(ttl=45, tags=frozenset(), no_store=False, tier="L1")


def test_parse_invalid_directives():
    with pytest.raises(ValueError):
        parse_cache_directive("max-age=-5")
    with pytest.raises(ValueError):
        parse_cache_directive("max-age=abc")
    with pytest.raises(ValueError):
        parse_cache_directive("tier=L3")
    with pytest.raises(ValueError):
        parse_cache_directive("unknown-flag")


def test_no_store_evicts_existing_and_writes_backing():
    coord = TierCacheCoordinator(l1_capacity=2, l2_capacity=2)
    coord.put_with_header("k1", "v1", "max-age=50; tags=t1", now=10)
    assert coord.fetch("k1", now=15) == ("v1", "L1")

    res = coord.put_with_header("k1", "v2", "no-store", now=20)
    assert res is False
    assert coord.fetch("k1", now=25) == ("v2", "ORIGIN")


def test_lru_eviction_on_distinct_keys():
    store = TierStore(capacity=2)
    p = CachePolicy(ttl=100)
    store.put("a", 1, p, now=0)
    store.put("b", 2, p, now=0)
    assert store.get("a", now=10) == 1
    store.put("c", 3, p, now=20)
    assert store.get("b", now=20) is None
    assert store.get("a", now=20) == 1
    assert store.get("c", now=20) == 3


def test_quoted_tags_parsed_and_invalidated():
    coord = TierCacheCoordinator(l1_capacity=3, l2_capacity=3)
    coord.put_with_header(
        "item:10",
        {"sku": "A"},
        'max-age=60; tags="Catalog, Promo:Summer , "',
        now=100,
    )
    policy = parse_cache_directive('tags="Catalog, Promo:Summer , "')
    assert policy.tags == frozenset({"catalog", "promo:summer"})

    removed = coord.invalidate_tag("CATALOG")
    assert removed == ["item:10"]
    assert coord.fetch("item:10", now=110) == ({"sku": "A"}, "ORIGIN")


def test_quoted_single_tag_and_tier_directive():
    policy = parse_cache_directive('max-age = 90 ; tags="auth" ; tier=l2')
    assert policy.ttl == 90
    assert policy.tags == frozenset({"auth"})
    assert policy.tier == "L2"


def test_overwrite_existing_key_at_capacity_does_not_evict_peer():
    store = TierStore(capacity=2)
    p = CachePolicy(ttl=100, tags=frozenset({"g1"}))
    store.put("k1", "v1", p, now=0)
    store.put("k2", "v2", p, now=0)

    store.put("k2", "v2-updated", p, now=10)
    assert len(store) == 2
    assert store.get("k1", now=15) == "v1"
    assert store.get("k2", now=15) == "v2-updated"


def test_overwrite_key_updates_tag_membership_and_lru_order():
    store = TierStore(capacity=2)
    store.put("k1", "v1", CachePolicy(ttl=100, tags=frozenset({"old_tag", "shared"})), now=0)
    store.put("k2", "v2", CachePolicy(ttl=100, tags=frozenset({"other"})), now=0)

    store.put("k1", "v1_new", CachePolicy(ttl=100, tags=frozenset({"new_tag", "shared"})), now=10)

    assert store.invalidate_tag("old_tag") == []
    assert store.get("k1", now=15) == "v1_new"

    store.put("k3", "v3", CachePolicy(ttl=100), now=20)
    assert store.get("k2", now=25) is None
    assert store.get("k1", now=25) == "v1_new"


def test_coordinator_demote_l1_to_l2_removes_stale_l1_entry():
    coord = TierCacheCoordinator(l1_capacity=2, l2_capacity=4)
    coord.put_with_header("doc:1", "v1", "max-age=100; tier=L1", now=0)
    assert coord.fetch("doc:1", now=10) == ("v1", "L1")

    coord.put_with_header("doc:1", "v2", "max-age=100; tier=L2", now=20)
    assert coord.fetch("doc:1", now=30) == ("v2", "L2")
