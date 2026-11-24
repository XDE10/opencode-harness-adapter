from functools import lru_cache


def _parse_segment(seg: str):
    tokens = []
    i = 0
    n = len(seg)
    while i < n:
        ch = seg[i]
        if ch == "\\":
            if i + 1 >= n:
                raise ValueError("trailing backslash")
            tokens.append(("LIT", seg[i + 1]))
            i += 2
        elif ch == "*":
            while i < n and seg[i] == "*":
                i += 1
            tokens.append(("STAR", None))
        elif ch == "?":
            tokens.append(("Q", None))
            i += 1
        elif ch == "[":
            i += 1
            neg = False
            if i < n and seg[i] in ("!", "^"):
                neg = True
                i += 1
            end = seg.find("]", i)
            if end == -1 or end == i:
                raise ValueError("invalid character class")
            body = seg[i:end]
            chars = set()
            ranges = []
            k = 0
            while k < len(body):
                if k + 2 < len(body) and body[k + 1] == "-":
                    lo, hi = body[k], body[k + 2]
                    if ord(lo) > ord(hi):
                        raise ValueError("descending range")
                    ranges.append((ord(lo), ord(hi)))
                    k += 3
                else:
                    chars.add(body[k])
                    k += 1
            tokens.append(("CLASS", (neg, chars, ranges)))
            i = end + 1
        else:
            tokens.append(("LIT", ch))
            i += 1
    return tokens


def _match_seg(tokens, text: str) -> bool:
    @lru_cache(maxsize=None)
    def dp(ti: int, si: int) -> bool:
        if ti == len(tokens):
            return si == len(text)
        kind, val = tokens[ti]
        if kind == "STAR":
            return dp(ti + 1, si) or (si < len(text) and dp(ti, si + 1))
        if si == len(text):
            return False
        ch = text[si]
        if kind == "Q":
            return dp(ti + 1, si + 1)
        if kind == "LIT":
            return ch == val and dp(ti + 1, si + 1)
        neg, chars, ranges = val
        hit = ch in chars or any(lo <= ord(ch) <= hi for lo, hi in ranges)
        return (not hit if neg else hit) and dp(ti + 1, si + 1)

    return dp(0, 0)


def match_glob(pattern, path):
    pat_segs = pattern.split("/")
    path_segs = path.split("/")
    compiled = [None if seg == "**" else _parse_segment(seg) for seg in pat_segs]

    @lru_cache(maxsize=None)
    def match_parts(pi: int, si: int) -> bool:
        if pi == len(compiled):
            return si == len(path_segs)
        if compiled[pi] is None:
            return match_parts(pi + 1, si) or (si < len(path_segs) and match_parts(pi, si + 1))
        if si == len(path_segs):
            return False
        return _match_seg(compiled[pi], path_segs[si]) and match_parts(pi + 1, si + 1)

    return match_parts(0, 0)
