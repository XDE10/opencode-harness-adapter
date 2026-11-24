# TierCache Write-Through & Header Parsing Issues

## Context
`tiercache` is a deterministic, in-memory multi-tier cache coordinator (`TierCacheCoordinator`) backed by an LRU eviction store (`TierStore`) and an HTTP-like cache-directive header parser (`parse_cache_directive`).

We recently observed two production issues:
1. Directives containing quoted tag lists or whitespace-padded `max-age` values fail to parse properly or register deformed tag names (e.g., retaining surrounding quotes or splitting tags incorrectly).
2. Updating an existing key via `put_with_header` or `put` causes stale tag index memberships and fails to refresh LRU recency order before capacity eviction checks run, resulting in either the updated key or the wrong peer key being evicted and stale keys surviving `invalidate_tag`.

## Specification

### 1. Directive Parsing (`tiercache.directives.parse_cache_directive`)
`parse_cache_directive(header: str, default_ttl: int = 60) -> CachePolicy`
- Parses semicolon-separated directives (case-insensitive keys, whitespace-trimmed around `;` and `=`).
- Supported directives:
  - `max-age=<int>`: Sets `ttl` (in seconds). Must be a non-negative integer (`>= 0`). Leading/trailing spaces around the integer value must be tolerated. If omitted, `ttl` defaults to `default_ttl`. If negative or non-numeric, raise `ValueError`.
  - `tags=<tag_list>`: Comma-separated list of tags. The value may optionally be wrapped in double quotes (e.g. `tags="auth, user:12 , profile"` or `tags=auth,profile`). Each tag must be stripped of surrounding whitespace and quotes, converted to lowercase, and empty tags ignored. Duplicate tags should be deduplicated into a `frozenset[str]`.
  - `no-store`: Boolean flag (no `=value`). Sets `no_store=True`.
  - `tier=<name>`: Optional target tier (`"L1"` or `"L2"`, case-normalized to uppercase, default `"L1"`). Any other tier value raises `ValueError`.

### 2. Tier Store & Tag Registry (`tiercache.store.TierStore`)
- Initialized with `capacity: int` (must be `>= 1`).
- `get(key: str, now: int) -> Any | None`:
  - If `key` is not present, returns `None`.
  - If `entry.expires_at <= now`, the entry is expired: remove it from the store and all tag indices, and return `None`.
  - Otherwise, mark `key` as most-recently-used and return `entry.value`.
- `put(key: str, value: Any, policy: CachePolicy, now: int) -> bool`:
  - If `policy.no_store` is `True` or `policy.ttl == 0`, do not store the entry. If `key` already exists in the store, remove it and clean up its tag registrations. Return `False`.
  - Purge any expired entries (`expires_at <= now`) before checking capacity.
  - If `key` already exists in the store:
    - Unregister `key` from any old tags that are no longer present in `policy.tags`.
    - Update the entry in-place and move `key` to the most-recently-used position **without** evicting another entry (since updating an existing key does not increase the key count).
  - If `key` is new and `len(store) >= capacity`, evict the least-recently-used entry (and clean up its tag indices) before inserting `key` as most-recently-used.
  - Entry expiration is `now + policy.ttl`. Return `True`.
- `invalidate_tag(tag: str) -> list[str]`:
  - Case-insensitively matches `tag` (strip whitespace and lowercase).
  - Removes all currently stored keys associated with that tag from the store and from all other tag memberships.
  - Returns a sorted `list[str]` of removed keys.

### 3. Coordinator (`tiercache.coordinator.TierCacheCoordinator`)
- Coordinates an `L1` (`TierStore`) and `L2` (`TierStore`) cache along with a `backing_store: dict[str, Any]`.
- `put_with_header(key: str, value: Any, header: str, now: int) -> bool`:
  - Always writes `value` through to `backing_store[key]`.
  - Parses `header` using `parse_cache_directive(header, default_ttl=self.default_ttl)`.
  - If `policy.no_store` or `policy.ttl == 0`: removes `key` from both `L1` and `L2` (if present) and returns `False`.
  - Always stores into `L2` using `policy`. If `policy.tier == "L1"`, also stores into `L1` using `policy`; if `policy.tier == "L2"`, ensures `key` is removed from `L1` so `L1` never serves a stale value.
  - Returns `True`.
- `fetch(key: str, now: int) -> tuple[Any | None, str]`:
  - Checks `L1.get(key, now)` -> if hit, returns `(val, "L1")`.
  - Checks `L2.get(key, now)` -> if hit, returns `(val, "L2")`.
  - Otherwise returns `(backing_store.get(key), "ORIGIN" if key in backing_store else "MISS")`.
