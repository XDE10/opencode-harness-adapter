import heapq

_ALLOWED = {"none", "first", "last"}


def _validate(streams, keys, dedup):
    if not isinstance(keys, list) or not keys:
        raise ValueError
    if any(not isinstance(k, str) for k in keys):
        raise ValueError
    if not isinstance(dedup, str) or dedup not in _ALLOWED:
        raise ValueError
    if not isinstance(streams, list):
        raise ValueError
    for stream in streams:
        if not isinstance(stream, list):
            raise ValueError
        for item in stream:
            if not isinstance(item, dict):
                raise ValueError
            for k in keys:
                if k not in item:
                    raise ValueError
    return tuple(keys)


def _key(item, fields):
    return tuple(item[f] for f in fields)


def _first_only(ordered):
    seen = set()
    kept = []
    for k, item in ordered:
        if k not in seen:
            kept.append(item)
            seen.add(k)
    return kept


def _last_only(ordered):
    last_pos = {}
    for i, (k, _) in enumerate(ordered):
        last_pos[k] = i
    return [item for i, (k, item) in enumerate(ordered) if last_pos[k] == i]


def merge_sorted(streams, keys, dedup):
    fields = _validate(streams, keys, dedup)
    heap = []
    for si, stream in enumerate(streams):
        if stream:
            first = _key(stream[0], fields)
            heapq.heappush(heap, (first, si, 0, stream[0]))
    ordered = []
    while heap:
        k, si, pos, item = heapq.heappop(heap)
        ordered.append((k, item))
        nxt = pos + 1
        if nxt < len(streams[si]):
            nk = _key(streams[si][nxt], fields)
            heapq.heappush(heap, (nk, si, nxt, streams[si][nxt]))
    if dedup == "none":
        return [item for _, item in ordered]
    if dedup == "last":
        return _last_only(ordered)
    return _first_only(ordered)
