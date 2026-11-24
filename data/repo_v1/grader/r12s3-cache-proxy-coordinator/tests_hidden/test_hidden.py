import pytest
from r12s3cache import MultiTierCache, parse_directive


def test_lfu_eviction_and_pinned_protection():
    cache = MultiTierCache(capacity=2, policy="lfu")
    cache.put("p1", "pinned_val", "max-age=100, pinned", now=1)
    cache.put("u1", "unpinned_1", "max-age=100", now=2)
    cache.get("u1", now=3)
    cache.get("u1", now=4)
    cache.put("u2", "unpinned_2", "max-age=100", now=5)
    assert "p1" in cache.l1
    assert "u2" in cache.l1
    assert "u1" not in cache.l1


def test_no_store_purges_existing_entries():
    cache = MultiTierCache(capacity=2, policy="lru")
    cache.put("session", "abc", "max-age=100, tags=auth", now=10)
    assert cache.put("session", "xyz", "no-store", now=20) is False
    assert cache.get("session", now=21) is None
    assert "session" not in cache.l1
    assert "session" not in cache.l2


def test_negative_ttl_raises_value_error():
    with pytest.raises(ValueError):
        parse_directive("max-age=-5")
    with pytest.raises(ValueError):
        parse_directive("s-maxage=-1")


def test_quoted_multi_tag_parsing_and_invalidation():
    cache = MultiTierCache(capacity=3, policy="lru")
    header = 'max-age=120, tags="user:42, org:7, billing", pinned=true'
    directive = parse_directive(header)
    assert directive.tags == frozenset({"user:42", "org:7", "billing"})
    assert directive.pinned is True

    cache.put("profile:42", {"id": 42}, header, now=0)
    assert cache.invalidate_tag("org:7") == 1
    assert cache.get("profile:42", now=10) is None


def test_s_maxage_zero_overrides_max_age():
    cache = MultiTierCache(capacity=2, policy="lru")
    cache.put("doc", "v1", "max-age=300", now=0)
    stored = cache.put("doc", "v2", "max-age=300, s-maxage=0", now=10)
    assert stored is False
    assert cache.get("doc", now=11) is None


def test_s_maxage_precedence_over_max_age():
    cache = MultiTierCache(capacity=2, policy="lru")
    cache.put("feed", [1, 2, 3], "s-maxage=15, max-age=120", now=100)
    assert cache.get("feed", now=114) == [1, 2, 3]
    assert cache.get("feed", now=115) is None


def test_in_place_update_at_capacity_does_not_evict_peer():
    cache = MultiTierCache(capacity=2, policy="lru")
    cache.put("k1", "v1", "max-age=100", now=1)
    cache.put("k2", "v2", "max-age=100", now=2)
    cache.put("k2", "v2_updated", "max-age=100", now=3)
    assert set(cache.l1.keys()) == {"k1", "k2"}
    assert cache.l1["k2"].value == "v2_updated"


def test_overwrite_key_cleans_up_stale_tags_in_l1():
    cache = MultiTierCache(capacity=2, policy="lru")
    cache.put("item", "v1", "max-age=100, tags=old_tag", now=1)
    cache.put("item", "v2", "max-age=100, tags=new_tag", now=2)
    assert cache.invalidate_tag("old_tag") == 0
    assert cache.get("item", now=3) == "v2"
    assert cache.invalidate_tag("new_tag") == 1
    assert cache.get("item", now=4) is None


def test_expired_l1_entries_purged_before_evicting_valid_entry():
    cache = MultiTierCache(capacity=2, policy="lru")
    cache.put("short_lived", "s", "max-age=10", now=0)
    cache.put("long_lived", "l", "max-age=100", now=0)
    cache.get("short_lived", now=5)
    cache.put("newcomer", "n", "max-age=100", now=20)
    assert set(cache.l1.keys()) == {"long_lived", "newcomer"}
