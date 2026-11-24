def _parse_segment(seg):
    tokens = []
    i = 0
    while i < len(seg):
        ch = seg[i]
        if ch == "\\":
            if i + 1 >= len(seg):
                raise ValueError("trailing escape")
            tokens.append(("lit", seg[i + 1]))
            i += 2
        elif ch == "*":
            tokens.append(("star", ""))
            i += 1
        elif ch == "?":
            tokens.append(("q", ""))
            i += 1
        else:
            tokens.append(("lit", ch))
            i += 1
    return tokens


def _segment_match(seg, text):
    tokens = _parse_segment(seg)
    prev = [False] * (len(text) + 1)
    prev[0] = True
    for kind, ch in tokens:
        cur = [False] * (len(text) + 1)
        if kind == "star":
            cur[0] = prev[0]
            for j in range(1, len(text) + 1):
                cur[j] = prev[j] or cur[j - 1]
        elif kind == "q":
            for j in range(1, len(text) + 1):
                cur[j] = prev[j - 1]
        else:
            for j in range(1, len(text) + 1):
                cur[j] = prev[j - 1] and text[j - 1] == ch
        prev = cur
    return prev[len(text)]


def match_route(pattern, path):
    if not isinstance(pattern, str) or not isinstance(path, str):
        raise TypeError("pattern and path must be strings")
    pparts = pattern.split("/")
    sparts = path.split("/")
    if any(part == "**" for part in pparts[:-1]):
        raise ValueError("** must be final")
    recursive = pparts[-1] == "**"
    if recursive:
        if len(sparts) < len(pparts):
            return False
        fixed = pparts[:-1]
    else:
        if len(sparts) != len(pparts):
            return False
        fixed = pparts
    return all(_segment_match(p, s) for p, s in zip(fixed, sparts))
