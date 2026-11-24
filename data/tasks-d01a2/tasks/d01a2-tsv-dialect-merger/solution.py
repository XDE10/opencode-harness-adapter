import re


def _norm(name):
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not s:
        raise ValueError("Empty column name")
    return s


def _coerce(val, quoted):
    if quoted:
        return val
    if val in ("", "NULL"):
        return None
    if re.fullmatch(r"[+-]?\d+", val):
        digits = val.lstrip("+-")
        if len(digits) > 1 and digits[0] == "0":
            return val
        return int(val)
    return val


def _parse_dialect(text, delimiter):
    text = text.replace("\r\n", "\n")
    n = len(text)
    i = 0
    rows = []
    while i < n:
        line_start = i
        while i < n and text[i] == " ":
            i += 1
        if i >= n:
            break
        if text[i] == "\n":
            i += 1
            continue
        if text[i] == "#":
            while i < n and text[i] != "\n":
                i += 1
            if i < n:
                i += 1
            continue
        i = line_start
        row = []
        while True:
            while i < n and text[i] == " ":
                i += 1
            if i < n and text[i] == '"':
                i += 1
                buf = []
                closed = False
                while i < n:
                    if text[i] == '"':
                        if i + 1 < n and text[i + 1] == '"':
                            buf.append('"')
                            i += 2
                        else:
                            i += 1
                            closed = True
                            break
                    else:
                        buf.append(text[i])
                        i += 1
                if not closed:
                    raise ValueError("Unclosed quote")
                while i < n and text[i] == " ":
                    i += 1
                if i < n and text[i] not in (delimiter, "\n"):
                    raise ValueError("Trailing characters after quote")
                row.append(("".join(buf), True))
            else:
                start = i
                while i < n and text[i] not in (delimiter, "\n"):
                    if text[i] == '"':
                        raise ValueError("Unexpected quote")
                    i += 1
                row.append((text[start:i].strip(" "), False))
            if i < n and text[i] == delimiter:
                i += 1
                continue
            if i < n and text[i] == "\n":
                i += 1
            break
        rows.append(row)
    if not rows:
        raise ValueError("Missing header row")
    headers = [_norm(v) for v, _ in rows[0]]
    if len(set(headers)) != len(headers):
        raise ValueError("Duplicate headers")
    data = []
    for r in rows[1:]:
        if len(r) != len(headers):
            raise ValueError("Width mismatch")
        data.append({h: _coerce(v, q) for h, (v, q) in zip(headers, r)})
    return headers, data


def _collapse_table(headers, rows, key):
    by_key = {}
    for r in rows:
        kv = r[key]
        if kv is None or kv == "":
            raise ValueError("Missing key value")
        k_str = str(kv)
        if k_str not in by_key:
            entry = dict(r)
            entry[key] = k_str
            by_key[k_str] = entry
        else:
            existing = by_key[k_str]
            for h in headers:
                if h == key:
                    continue
                existing[h] = r[h]
    return by_key


def merge_dialect_tables(primary_csv, secondary_tsv, key_col, prefer="latest"):
    if prefer not in ("primary", "secondary", "latest"):
        raise ValueError("Invalid prefer mode")
    key = _norm(key_col)
    h1, r1 = _parse_dialect(primary_csv, ",")
    h2, r2 = _parse_dialect(secondary_tsv, "\t")
    if key not in h1 or key not in h2:
        raise ValueError("Key column missing")
    all_cols = list(dict.fromkeys(h1 + h2))
    m1 = _collapse_table(h1, r1, key)
    m2 = _collapse_table(h2, r2, key)
    all_keys = list(dict.fromkeys(list(m1.keys()) + list(m2.keys())))
    merged = []
    for k in all_keys:
        d1 = m1.get(k, {})
        d2 = m2.get(k, {})
        row = {c: None for c in all_cols}
        row[key] = k
        for c in all_cols:
            if c == key:
                continue
            v1 = d1.get(c)
            v2 = d2.get(c)
            if prefer == "primary":
                row[c] = v1 or v2
            else:
                row[c] = v2 or v1
        merged.append(row)
    if all(re.fullmatch(r"[+-]?\d+", k) for k in all_keys):
        merged.sort(key=lambda r: int(r[key]))
    else:
        merged.sort(key=lambda r: r[key])
    return merged
