from r12s3cache.models import CacheDirective


def _split_top_level(header: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_quotes = False
    for ch in header:
        if ch == '"':
            in_quotes = not in_quotes
            current.append(ch)
        elif ch == "," and not in_quotes:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]


def parse_directive(header: str, default_ttl: int = 60) -> CacheDirective:
    if not header or not header.strip():
        return CacheDirective(ttl=default_ttl)

    tokens = _split_top_level(header)
    max_age: int | None = None
    s_maxage: int | None = None
    no_store = False
    pinned = False
    tags: set[str] = set()

    for token in tokens:
        if "=" not in token:
            flag = token.strip().lower()
            if flag == "no-store":
                no_store = True
            elif flag == "pinned":
                pinned = True
            continue

        raw_key, raw_val = token.split("=", 1)
        key = raw_key.strip().lower()
        val = raw_val.strip()

        if key == "max-age":
            parsed = int(val)
            if parsed < 0:
                raise ValueError("max-age cannot be negative")
            max_age = parsed
        elif key == "s-maxage":
            parsed = int(val)
            if parsed < 0:
                raise ValueError("s-maxage cannot be negative")
            s_maxage = parsed
        elif key == "pinned":
            pinned = val.lower() in ("true", "1", "yes")
        elif key == "tags":
            if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            for t in val.split(","):
                cleaned = t.strip()
                if cleaned:
                    tags.add(cleaned)

    if no_store:
        return CacheDirective(ttl=0, tags=frozenset(tags), no_store=True, pinned=pinned)

    if s_maxage is not None:
        ttl = s_maxage
    elif max_age is not None:
        ttl = max_age
    else:
        ttl = default_ttl

    return CacheDirective(
        ttl=ttl,
        tags=frozenset(tags),
        no_store=False,
        pinned=pinned,
    )
