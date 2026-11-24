import re


def _normalize_header(raw_fields):
    headers = []
    for text, _ in raw_fields:
        norm = re.sub(r"[\s\-]+", "_", text.strip().lower())
        if not norm or norm in headers:
            raise ValueError("Invalid or duplicate header")
        headers.append(norm)
    return headers


def _coerce_field(text, was_quoted):
    if was_quoted:
        return text
    s = text.strip()
    if s == "":
        return None
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if re.fullmatch(r"[+-]?\d+", s):
        return int(s)
    return s


def _parse_record(rec, delimiter):
    fields = []
    cur = []
    in_quotes = False
    was_quoted = False
    i = 0
    n = len(rec)
    while i < n:
        ch = rec[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < n and rec[i + 1] == '"':
                    cur.append('"')
                    i += 2
                    continue
                in_quotes = False
            else:
                cur.append(ch)
        else:
            if ch == '"':
                in_quotes = True
                was_quoted = True
            elif ch == delimiter:
                fields.append(("".join(cur), was_quoted))
                cur = []
                was_quoted = False
            else:
                cur.append(ch)
        i += 1
    if in_quotes:
        raise ValueError("Unclosed quote")
    fields.append(("".join(cur), was_quoted))
    return fields


def run_csv_stream(delimiter, ops):
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in '\n\r"#':
        raise ValueError("Invalid delimiter")

    buf = ""
    headers = None
    rows = []
    out = []

    def consume_complete(flush_tail=False):
        nonlocal buf, headers
        added = 0
        in_q = False
        start = 0
        i = 0
        while i < len(buf):
            ch = buf[i]
            if ch == '"':
                in_q = not in_q
            elif ch == "\n" and not in_q:
                added += handle_record(buf[start:i])
                start = i + 1
            i += 1
        buf = buf[start:]
        if flush_tail:
            if in_q:
                raise ValueError("Unclosed quote at EOF")
            if buf:
                added += handle_record(buf)
                buf = ""
        return added

    def handle_record(rec):
        nonlocal headers
        if rec.endswith("\r"):
            rec = rec[:-1]
        stripped = rec.lstrip(" \t")
        if not stripped or (stripped.startswith("#") and not stripped.startswith('"')):
            return 0
        parsed = _parse_record(rec, delimiter)
        if headers is None:
            headers = _normalize_header(parsed)
            return 0
        if len(parsed) != len(headers):
            raise ValueError("Column count mismatch")
        row = {h: _coerce_field(val, q) for h, (val, q) in zip(headers, parsed)}
        rows.append(row)
        return 1

    for item in ops:
        op = item["op"]
        if op == "feed":
            buf += item["chunk"]
            out.append(consume_complete(False))
        elif op == "finish":
            out.append(consume_complete(True))
        elif op == "take":
            out.append(list(rows))
            rows.clear()
        elif op == "reset":
            buf = ""
            headers = None
            rows.clear()
            out.append(None)
        else:
            raise ValueError(f"Unknown op: {op}")
    return out
