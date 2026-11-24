import re


def _normalize_headers(raw_headers):
    seen = set()
    counts = {}
    result = []
    for h in raw_headers:
        norm = re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_")
        if not norm:
            raise ValueError("Empty header name")
        if norm not in seen:
            seen.add(norm)
            counts[norm] = 1
            result.append(norm)
        else:
            k = counts.get(norm, 1) + 1
            while f"{norm}_{k}" in seen:
                k += 1
            counts[norm] = k
            candidate = f"{norm}_{k}"
            seen.add(candidate)
            result.append(candidate)
    return result


def _coerce_value(val, is_quoted, null_set):
    if is_quoted:
        return val
    if val in null_set:
        return None
    low = val.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if re.fullmatch(r"[+-]?\d+", val):
        digits = val.lstrip("+-")
        if len(digits) > 1 and digits[0] == "0":
            return val
        return int(val)
    return val


def _parse_records(text, delimiter):
    text = text.replace("\r\n", "\n")
    pad = "".join(ch for ch in (" ", "\t") if ch != delimiter)
    n = len(text)
    i = 0
    records = []
    while i < n:
        line_start = i
        while i < n and text[i] in pad:
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
            while i < n and text[i] in pad:
                i += 1
            if i < n and text[i] == '"':
                i += 1
                buf = []
                closed = False
                while i < n:
                    ch = text[i]
                    if ch == '"':
                        if i + 1 < n and text[i + 1] == '"':
                            buf.append('"')
                            i += 2
                        else:
                            i += 1
                            closed = True
                            break
                    else:
                        buf.append(ch)
                        i += 1
                if not closed:
                    raise ValueError("Unclosed quoted field")
                while i < n and text[i] in pad:
                    i += 1
                if i < n and text[i] not in (delimiter, "\n"):
                    raise ValueError("Unexpected characters after closing quote")
                row.append(("".join(buf), True))
            else:
                start = i
                while i < n and text[i] not in (delimiter, "\n"):
                    if text[i] == '"':
                        raise ValueError("Quote inside unquoted field")
                    i += 1
                raw = text[start:i].strip(pad)
                row.append((raw, False))
            if i < n and text[i] == delimiter:
                i += 1
                continue
            if i < n and text[i] == "\n":
                i += 1
            break
        records.append(row)
    return records


def parse_table(text, delimiter=",", null_tokens=("", "NULL", "N/A")):
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in ('"', "#", "\n", "\r"):
        raise ValueError("Invalid delimiter")
    null_set = set(null_tokens)
    records = _parse_records(text, delimiter)
    if not records:
        return []
    headers = _normalize_headers([val for val, _ in records[0]])
    width = len(headers)
    out = []
    for rec in records[1:]:
        if len(rec) != width:
            raise ValueError("Row width mismatch")
        row_dict = {}
        for h, (val, is_quoted) in zip(headers, rec):
            row_dict[h] = _coerce_value(val, is_quoted, null_set)
        out.append(row_dict)
    return out
