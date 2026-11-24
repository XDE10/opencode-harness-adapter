from dataclasses import dataclass


@dataclass(frozen=True)
class CachePolicy:
    ttl: int
    tags: frozenset[str] = frozenset()
    no_store: bool = False
    tier: str = "L1"


def parse_cache_directive(header: str, default_ttl: int = 60) -> CachePolicy:
    ttl = default_ttl
    tags: set[str] = set()
    no_store = False
    tier = "L1"

    if not header or not header.strip():
        return CachePolicy(ttl=ttl, tags=frozenset(), no_store=no_store, tier=tier)

    parts = [p.strip() for p in header.split(";") if p.strip()]
    for part in parts:
        if "=" not in part:
            token = part.lower()
            if token == "no-store":
                no_store = True
            else:
                raise ValueError(f"Unknown flag directive: {part}")
            continue

        raw_key, raw_val = part.split("=", 1)
        key = raw_key.strip().lower()
        val = raw_val.strip()

        if key == "max-age":
            try:
                parsed_ttl = int(val)
            except ValueError as exc:
                raise ValueError(f"Invalid max-age value: {val}") from exc
            if parsed_ttl < 0:
                raise ValueError(f"max-age cannot be negative: {parsed_ttl}")
            ttl = parsed_ttl
        elif key == "tags":
            for raw_tag in val.split(","):
                cleaned = raw_tag.strip().lower()
                if cleaned:
                    tags.add(cleaned)
        elif key == "tier":
            norm_tier = val.strip().upper()
            if norm_tier not in ("L1", "L2"):
                raise ValueError(f"Unsupported tier: {val}")
            tier = norm_tier
        else:
            raise ValueError(f"Unknown directive key: {key}")

    return CachePolicy(ttl=ttl, tags=frozenset(tags), no_store=no_store, tier=tier)
