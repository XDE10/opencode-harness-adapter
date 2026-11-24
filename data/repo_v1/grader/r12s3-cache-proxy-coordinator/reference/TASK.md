# Issue Report: Multi-Tier Cache Proxy Directive Parsing and Write-Through Eviction Drift

## Summary
Our two-tier cache proxy (`r12s3cache`) coordinates an L1 memory cache (capacity-bounded with LRU/LFU eviction and TTL expiration) and an L2 backing store, controlled by header directives (`Cache-Control` style headers).

In production we are seeing two distinct regressions:
1. **Stale reads and tag leaks after `s-maxage` / quoted tag directives**: Upstream responses often specify shared proxy TTL overrides (`s-maxage`) alongside `max-age`, or supply quoted tag lists such as `tags="auth, profile"`. Entries either ignore the proxy override or fail to invalidate when a tag is purged.
2. **Capacity overflow and tag index corruption during L1 updates and evictions**: When an existing key is overwritten via write-through (`put`) or promoted from L2 on an L1 miss, the tier's capacity accounting and tag index drift out of sync. Existing keys that are updated in-place unexpectedly trigger evictions of other keys, or stale tags from prior versions of an updated/evicted key remain in the tag registry and cause false invalidations later.

## Behavioral Specification

### 1. Directive Parsing (`r12s3cache.directives`)
`parse_directive(header: str, default_ttl: int = 60) -> CacheDirective` parses a comma-separated directive header string (e.g. `"max-age=120, s-maxage=30, tags=\"user:1, org:9\", policy=lfu"`):
- Tokens are separated by commas Outside of double quotes (`"`). Whitespace around keys and values is stripped.
- **TTL precedence**:
  - If `no-store` is present (case-insensitive flag), `no_store=True` and `ttl=0`.
  - Otherwise, if `s-maxage=<int>` is present, `ttl` MUST use the integer value of `s-maxage` (even if `s-maxage=0` or `max-age` appears later in the header).
  - Otherwise, if `max-age=<int>` is present, `ttl` uses `max-age`.
  - Otherwise, `ttl` defaults to `default_ttl`.
  - Negative integer TTL values must raise `ValueError`.
- **Tags**:
  - `tags=<val>` may be a single unquoted token (`tags=billing`) or a double-quoted comma/space-separated list (`tags="user:1, org:9"`).
  - Surrounding quotes must be stripped, inner items split on commas, stripped of whitespace, deduplicated, and stored as a `frozenset[str]` (empty tokens ignored).
- **Pinned flag**:
  - If `pinned` flag or `pinned=true` (case-insensitive) is present, `pinned=True`.

### 2. Multi-Tier Coordinator & Eviction (`r12s3cache.coordinator` & `r12s3cache.models`)
`MultiTierCache(capacity: int, policy: str = "lru", default_ttl: int = 60)` manages L1 (`dict[str, CacheEntry]`) and L2 (`dict[str, CacheEntry]`):
- **Expiration (`is_expired(now)`)**: An entry with `expires_at <= now` is expired. Before admitting a new entry or serving a `get`, expired L1 entries encountered (or purged during capacity checks) must be removed from L1 and its tag index.
- **Updating an Existing Key in L1**:
  - When `put(key, value, header, now)` is called for a `key` that is *already present and un-expired* in L1, updating it in-place does **not** increase the number of keys in L1 and MUST NOT evict another valid key when L1 is at capacity.
  - When an existing L1 key is overwritten (or evicted/expired), any tags that belonged to the old entry but are not on the new entry MUST be removed from the L1 tag registry so `invalidate_tag(old_tag)` does not delete the newly updated key.
  - Calling `put` with a `no-store` directive must remove `key` from both L1 (and its tags) and L2 if present, and not store the new value.
- **Eviction Policy (`lru` vs `lfu`)**:
  - Before evicting a valid entry to make room for a new key, purge any expired entries in L1 at timestamp `now`. If purging expired entries frees enough space, no valid entry should be evicted.
  - Pinned entries (`entry.pinned == True`) cannot be evicted for capacity (unless all current L1 entries are pinned, in which case raise `RuntimeError("Cache full of pinned entries")`).
  - `lru` evicts the non-pinned entry with the smallest `last_accessed` timestamp (tie-breaking by smallest `created_at`, then lexicographically smallest `key`).
  - `lfu` evicts the non-pinned entry with the smallest `hits` count (tie-breaking by smallest `last_accessed`, then lexicographically smallest `key`).
- **Read Path (`get(key, now)`)**:
  - If `key` is in L1 and not expired at `now`: increment `hits` by 1, update `last_accessed = now`, and return `entry.value`.
  - If `key` is missing or expired in L1, check L2. If present and not expired in L2, promote a copy into L1 (with `hits=1`, `last_accessed=now`, subject to L1 capacity eviction), register its tags in L1, and return `entry.value`. If expired in L2, remove from L2 and return `None`.
