from dataclasses import dataclass, field


@dataclass(frozen=True)
class CacheDirective:
    ttl: int
    tags: frozenset[str] = field(default_factory=frozenset)
    no_store: bool = False
    pinned: bool = False


@dataclass
class CacheEntry:
    key: str
    value: object
    created_at: int
    expires_at: int
    last_accessed: int
    hits: int = 1
    tags: frozenset[str] = field(default_factory=frozenset)
    pinned: bool = False

    def is_expired(self, now: int) -> bool:
        return self.expires_at <= now

    def clone_for_l1(self, now: int) -> "CacheEntry":
        return CacheEntry(
            key=self.key,
            value=self.value,
            created_at=self.created_at,
            expires_at=self.expires_at,
            last_accessed=now,
            hits=1,
            tags=self.tags,
            pinned=self.pinned,
        )
