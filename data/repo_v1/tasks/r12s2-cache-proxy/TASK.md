# Issue Report: Stale tag registrations on update and corrupt batch write rollback in `r12s2cache`

## Background
`r12s2cache` implements a multi-tier write-through cache proxy with L1 (bounded LRU) and L2 (unbounded backing store) tiers, tag-based invalidation via `TagRegistry`, and transactional multi-key batch writes via `CacheCoordinator`.

We observed two production failures during multi-step cache workflows:
1. **Orphaned tags after overwriting an existing key**: When an existing key is overwritten with a different set of tags (or re-indexed in the tag registry), invalidating a tag that was *removed* from that key still invalidates the key. Conversely, querying keys by the old tag still returns the updated key.
2. **Failed batch write-through corrupts previously existing keys**: `CacheCoordinator.batch_put` supports an optional validation hook (`validator(key, value) -> bool`). When a batch fails mid-flight on key $k_i$, the rollback procedure is supposed to restore both L1 and L2 (plus tag mappings and L1 capacity state) to their exact pre-batch state. Currently, if a batch overwrites an already-cached key and a subsequent entry in the same batch fails validation, the overwritten key is completely deleted instead of being restored to its prior value, TTL, and tags.

## Behavioral Specification

### `CacheEntry` & `TagRegistry` (`r12s2cache.registry`)
- `CacheEntry(key, value, expires_at, tags, version=1)`:
  - `is_expired(now: float) -> bool`: Returns `True` when `expires_at is not None and now >= expires_at`.
- `TagRegistry`:
  - `bind(key: str, tags: Iterable[str]) -> None`: Associates `key` with the exact set of `tags` provided, completely replacing any previous tag associations for `key`. If a previous tag loses its last associated key, that tag set should remain clean.
  - `unbind(key: str) -> set[str]`: Removes all tag associations for `key` and returns the set of tags that were bound to it.
  - `keys_for_tag(tag: str) -> set[str]`: Returns a copy of the set of keys currently bound to `tag`.
  - `tags_for_key(key: str) -> set[str]`: Returns a copy of the set of tags currently bound to `key`.
  - `invalidate_tags(tags: Iterable[str]) -> set[str]`: Collects all keys bound to any tag in `tags`, unbinds every affected key from *all* of its tags, and returns the set of invalidated keys.

### `LRUTier` (`r12s2cache.tier`)
- Bounded LRU cache of capacity `max_size`.
- `get(key: str, now: float) -> CacheEntry | None`:
  - If `key` is not present, returns `None`.
  - If the entry is expired at `now`, deletes it from the tier and returns `None`.
  - Otherwise marks `key` as most-recently-used and returns the `CacheEntry`.
- `put(entry: CacheEntry, now: float) -> list[str]`:
  - Before inserting, purges any currently expired entries in the tier so expired items do not cause live items to be evicted.
  - Inserts or updates `entry` and marks `entry.key` as most-recently-used.
  - If size exceeds `max_size`, evicts the least-recently-used key(s) and returns the list of evicted keys (excluding expired keys purged earlier).

### `CacheCoordinator` (`r12s2cache.coordinator`)
- Coordinates `l1: LRUTier`, `l2: dict[str, CacheEntry]`, and `registry: TagRegistry`.
- `put(key, value, now, ttl=None, tags=()) -> CacheEntry`:
  - If `key` already exists in `l2` and is *not* expired at `now`, the new entry's `version` is `old_entry.version + 1`; otherwise `version = 1`.
  - `expires_at = (now + ttl) if ttl is not None else None`.
  - Writes the new `CacheEntry` to both `l1` and `l2`, and updates `registry.bind(key, tags)`.
- `get(key, now) -> Any | None`:
  - Checks `l1.get(key, now)`. On hit, returns `entry.value`.
  - On L1 miss, checks `l2`. If present in `l2` and not expired at `now`, promotes the entry back into `l1.put(entry, now)` and returns `entry.value`.
  - If present in `l2` and expired at `now`, removes `key` from `l2` and `registry.unbind(key)`, returning `None`.
- `invalidate_tag(tag, now) -> set[str]`:
  - Uses `registry.invalidate_tags([tag])` to find and unbind all keys for `tag`, removes those keys from `l1` and `l2`, and returns the set of invalidated keys.
- `batch_put(items, now, validator=None) -> bool`:
  - `items` is a sequence of `(key, value, ttl, tags)` tuples.
  - If `validator` is provided and `validator(key, value)` returns `False` for any item, the entire batch must abort and return `False`, restoring `l2`, `l1`, and `registry` so that any keys modified or created during the batch have their exact pre-batch entries (including original `value`, `expires_at`, `tags`, and `version`) restored, and newly added keys are removed.
  - If all items pass validation, applies all writes in order and returns `True`.
- `query_by_tags(tags, now, match_all=True) -> dict[str, Any]`:
  - Finds keys matching **all** tags (if `match_all=True`) or **any** tag (if `match_all=False`), fetches each key via `self.get(key, now)` (filtering out expired keys), and returns `{key: value}` for live entries.
