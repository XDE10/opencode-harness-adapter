def _digits(bs):
    return bool(bs) and all(48 <= c <= 57 for c in bs)

def _int_ok(tok):
    try:
        int(tok.decode("ascii"))
    except ValueError:
        return False
    return True

def _len_ok(tok):
    return _digits(tok) and (tok == b"0" or tok[0] != 48)

def _encode(value):
    t = type(value)
    if t is int: return "i" + str(value) + "e"
    if t is str:
        raw = value.encode("utf-8")
        return str(len(raw)) + ":" + value
    if t is list: return "l" + "".join(_encode(x) for x in value) + "e"
    if t is dict:
        keys = list(value)
        for key in keys:
            if type(key) is not str: raise TypeError("dict keys must be str")
        keys.sort(key=lambda k: k.encode("utf-8"))
        parts = []
        for key in keys:
            parts.append(_encode(key))
            parts.append(_encode(value[key]))
        return "d" + "".join(parts) + "e"
    raise TypeError("unsupported value")

def _decode(text):
    data = text.encode("utf-8")
    pos = 0
    n = len(data)
    def parse():
        nonlocal pos
        if pos >= n: raise ValueError("unexpected end")
        c = data[pos]
        if c == 105:
            end = data.find(b"e", pos + 1)
            tok = data[pos + 1:end] if end >= 0 else b""
            if not _int_ok(tok): raise ValueError("bad integer")
            value = int(tok.decode("ascii"))
            pos = end + 1
            return value
        if c == 108:
            pos += 1
            items = []
            while pos < n and data[pos] != 101: items.append(parse())
            if pos >= n: raise ValueError("unterminated list")
            pos += 1
            return items
        if c == 100:
            pos += 1
            result = {}
            while pos < n and data[pos] != 101:
                key = parse()
                if type(key) is not str: raise ValueError("dict key must be string")
                if key in result: raise ValueError("duplicate key")
                result[key] = parse()
            if pos >= n: raise ValueError("unterminated dict")
            pos += 1
            return result
        if 48 <= c <= 57:
            colon = data.find(b":", pos)
            tok = data[pos:colon] if colon >= 0 else b""
            if not _len_ok(tok): raise ValueError("bad length")
            size = int(tok)
            start = colon + 1
            if start + size > n: raise ValueError("short string")
            try: value = data[start:start + size].decode("utf-8")
            except UnicodeDecodeError: raise ValueError("bad utf8") from None
            pos = start + size
            return value
        raise ValueError("bad token")
    value = parse()
    if pos != n: raise ValueError("trailing data")
    return value

def bencode_codec(mode, payload):
    if mode == "encode": return _encode(payload)
    if mode == "decode":
        if type(payload) is not str: raise TypeError("payload must be str")
        return _decode(payload)
    raise ValueError("bad mode")
