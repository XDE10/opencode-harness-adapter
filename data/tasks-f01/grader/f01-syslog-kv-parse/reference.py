_LEVEL_ALIASES = {
    "WARN": "WARNING",
    "ERR": "ERROR",
    "CRIT": "CRITICAL",
}


def _tokenize_kv(line):
    tokens = []
    i = 0
    n = len(line)
    while i < n:
        while i < n and line[i].isspace():
            i += 1
        if i >= n:
            break
        eq_pos = line.find("=", i)
        if eq_pos == -1 or eq_pos == i:
            raise ValueError("missing or empty key")
        key = line[i:eq_pos]
        if any(ch.isspace() for ch in key):
            raise ValueError("whitespace in key")
        i = eq_pos + 1
        if i >= n or line[i].isspace():
            raise ValueError("empty unquoted value")
        if line[i] == '"':
            i += 1
            buf = []
            closed = False
            while i < n:
                ch = line[i]
                if ch == '"':
                    closed = True
                    i += 1
                    break
                if ch == "\\" and i + 1 < n and line[i + 1] in ('"', "\\"):
                    buf.append(line[i + 1])
                    i += 2
                    continue
                buf.append(ch)
                i += 1
            if not closed:
                raise ValueError("unclosed quoted value")
            if i < n and not line[i].isspace():
                raise ValueError("trailing characters after closing quote")
            val = "".join(buf)
        else:
            start = i
            while i < n and not line[i].isspace():
                if line[i] == '"':
                    raise ValueError("unexpected quote in unquoted value")
                i += 1
            val = line[start:i]
        tokens.append((key, val))
    return tokens


def parse_syslog_records(lines, required_fields=None, max_skew_ms=0):
    if max_skew_ms < 0:
        raise ValueError("max_skew_ms must be non-negative")
    req = list(required_fields) if required_fields is not None else []
    max_seen_ts = None
    accepted = []

    for idx, raw in enumerate(lines):
        if not raw.strip():
            continue
        record = {}
        for key, val in _tokenize_kv(raw):
            if key in record:
                raise ValueError(f"duplicate key: {key}")
            record[key] = val
        if "ts" not in record:
            raise ValueError("missing ts field")
        try:
            ts = int(record["ts"], 10)
        except ValueError as exc:
            raise ValueError("invalid ts") from exc
        if ts < 0:
            raise ValueError("negative ts")
        record["ts"] = ts
        if "level" in record:
            upper = record["level"].upper()
            record["level"] = _LEVEL_ALIASES.get(upper, upper)
        for field in req:
            if field not in record:
                raise KeyError(field)
        if max_seen_ts is not None and ts < max_seen_ts - max_skew_ms:
            continue
        if max_seen_ts is None or ts > max_seen_ts:
            max_seen_ts = ts
        accepted.append((ts, idx, record))

    accepted.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in accepted]
