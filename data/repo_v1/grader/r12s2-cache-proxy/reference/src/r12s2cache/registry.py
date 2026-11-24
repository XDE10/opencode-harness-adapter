from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class CacheEntry:
    key: str
    value: Any
    expires_at: float | None = None
    tags: frozenset[str] = field(default_factory=frozenset)
    version: int = 1

    def is_expired(self, now: float) -> bool:
        return self.expires_at is not None and now >= self.expires_at


class TagRegistry:
    def __init__(self) -> None:
        self._tag_to_keys: dict[str, set[str]] = {}
        self._key_to_tags: dict[str, set[str]] = {}

    def bind(self, key: str, tags: Iterable[str]) -> None:
        self.unbind(key)
        tag_set = set(tags)
        if not tag_set:
            return
        self._key_to_tags[key] = tag_set
        for tag in tag_set:
            self._tag_to_keys.setdefault(tag, set()).add(key)

    def unbind(self, key: str) -> set[str]:
        old_tags = self._key_to_tags.pop(key, set())
        for tag in old_tags:
            bucket = self._tag_to_keys.get(tag)
            if bucket is not None:
                bucket.discard(key)
                if not bucket:
                    del self._tag_to_keys[tag]
        return set(old_tags)

    def keys_for_tag(self, tag: str) -> set[str]:
        return set(self._tag_to_keys.get(tag, set()))

    def tags_for_key(self, key: str) -> set[str]:
        return set(self._key_to_tags.get(key, set()))

    def invalidate_tags(self, tags: Iterable[str]) -> set[str]:
        affected: set[str] = set()
        for tag in tags:
            affected.update(self._tag_to_keys.get(tag, set()))
        for key in list(affected):
            self.unbind(key)
        return affected
