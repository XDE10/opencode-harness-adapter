def _encode(value):
    t = type(value)
    if t is int: return "i" + str(value) + "e"
    if t is str: return str(len(value.encode("utf-8"))) + ":" + value
    if t is list: return "l" + "".join(_encode(x) for x in value) + "e"
    if t is dict:
        parts = []
        for key in value:
            if type(key) is not str: raise TypeError("dict keys must be str")
            parts.extend((_encode(key), _encode(value[key])))
        return "d" + "".join(parts) + "e"
    raise TypeError("unsupported value")

def _decode(text):
    pos = 0
    n = len(text)
    def parse():
        nonlocal pos
        if pos >= n: raise ValueError("unexpected end")
        ch = text[pos]
        if ch == "i":
            end = text.find("e", pos + 1)
            token = text[pos + 1:end] if end >= 0 else ""
            try: value = int(token)
            except ValueError: raise ValueError("bad integer") from None
            pos = end + 1
            return value
        if ch == "l":
            pos += 1
            items = []
            while pos < n and text[pos] != "e": items.append(parse())
            if pos >= n: raise ValueError("unterminated list")
            pos += 1
            return items
        if ch == "d":
            pos += 1
            result = {}
            while pos < n and text[pos] != "e":
                key = parse()
                if type(key) is not str: raise ValueError("dict key must be string")
                if key in result: raise ValueError("duplicate key")
                result[key] = parse()
            if pos >= n: raise ValueError("unterminated dict")
            pos += 1
            return result
        if "0" <= ch <= "9":
            colon = text.find(":", pos)
            token = text[pos:colon] if colon >= 0 else ""
            if not token or any(c < "0" or c > "9" for c in token): raise ValueError("bad length")
            if len(token) > 1 and token[0] == "0": raise ValueError("bad length")
            size = int(token)
            start = colon + 1
            if start + size > n: raise ValueError("short string")
            value = text[start:start + size]
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
