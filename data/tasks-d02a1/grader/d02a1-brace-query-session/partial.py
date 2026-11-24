import copy


def expand_braces(text: str) -> list[str]:
    parts = []
    i = 0
    n = len(text)
    cur = []
    while i < n:
        ch = text[i]
        if ch == "\\":
            if i + 1 >= n:
                raise ValueError("Trailing backslash")
            cur.append(text[i + 1])
            i += 2
            continue
        if ch == "}":
            raise ValueError("Unmatched closing brace")
        if ch == "{":
            parts.append(["".join(cur)])
            cur = []
            i += 1
            alts = []
            alt_buf = []
            has_comma = False
            while i < n and text[i] != "}":
                if text[i] == "\\":
                    if i + 1 >= n:
                        raise ValueError("Trailing backslash in brace")
                    alt_buf.append(text[i + 1])
                    i += 2
                elif text[i] == "{":
                    raise ValueError("Nested brace")
                elif text[i] == ",":
                    has_comma = True
                    alts.append("".join(alt_buf))
                    alt_buf = []
                    i += 1
                else:
                    alt_buf.append(text[i])
                    i += 1
            if i >= n:
                raise ValueError("Unclosed brace")
            alts.append("".join(alt_buf))
            i += 1
            if has_comma:
                parts.append(alts)
            else:
                parts.append(["{" + alts[0] + "}"])
            continue
        cur.append(ch)
        i += 1
    if cur or not parts:
        parts.append(["".join(cur)])

    res = [""]
    for group in parts:
        res = [prefix + item for prefix in res for item in group]
    return res


def parse_key_path(key: str) -> list[str]:
    if not key or key[0] in "[]":
        raise ValueError("Invalid key root")
    bracket_idx = key.find("[")
    if bracket_idx == -1:
        if "]" in key:
            raise ValueError("Unmatched bracket")
        return [key]
    root = key[:bracket_idx]
    segs = [root]
    i = bracket_idx
    n = len(key)
    while i < n:
        if key[i] != "[":
            raise ValueError("Unexpected char outside brackets")
        close = key.find("]", i + 1)
        if close == -1:
            raise ValueError("Unclosed bracket")
        sub = key[i + 1 : close]
        if "[" in sub:
            raise ValueError("Nested bracket")
        segs.append(sub)
        i = close + 1
    for s in segs[:-1]:
        if s == "":
            raise ValueError("Empty bracket not at end")
    return segs


def apply_set(state: dict, segs: list[str], val: str):
    cur = state
    for s in segs[:-2]:
        if s not in cur:
            cur[s] = {}
        elif not isinstance(cur[s], dict):
            raise ValueError("Path conflict")
        cur = cur[s]
    if len(segs) == 1:
        cur[segs[0]] = val
        return
    parent_key = segs[-2]
    last_key = segs[-1]
    if last_key == "":
        if parent_key not in cur or not isinstance(cur[parent_key], list):
            cur[parent_key] = []
        cur[parent_key].append(val)
    else:
        if parent_key not in cur:
            cur[parent_key] = {}
        elif not isinstance(cur[parent_key], dict):
            raise ValueError("Path conflict")
        cur[parent_key][last_key] = val


def apply_unset(state: dict, segs: list[str]) -> bool:
    if segs[-1] == "":
        raise ValueError("Cannot unset list push key")
    cur = state
    for s in segs[:-1]:
        if not isinstance(cur, dict) or s not in cur:
            return False
        cur = cur[s]
    if not isinstance(cur, dict) or segs[-1] not in cur:
        return False
    del cur[segs[-1]]
    return True


def run_query_session(ops: list[dict]) -> list:
    state = {}
    out = []
    for item in ops:
        op = item.get("op")
        if op == "ingest":
            q = item["query"]
            count = 0
            for part in q.split("&"):
                if not part:
                    continue
                if "=" in part:
                    rk, rv = part.split("=", 1)
                else:
                    rk, rv = part, ""
                keys = expand_braces(rk)
                vals = expand_braces(rv)
                for k in keys:
                    segs = parse_key_path(k)
                    for v in vals:
                        apply_set(state, segs, v)
                        count += 1
            out.append(count)
        elif op == "unset":
            keys = expand_braces(item["key"])
            removed = 0
            for k in keys:
                segs = parse_key_path(k)
                if apply_unset(state, segs):
                    removed += 1
            out.append(removed)
        elif op == "snapshot":
            out.append(copy.deepcopy(state))
        elif op == "reset":
            state.clear()
            out.append(None)
        else:
            raise ValueError(f"Unknown op: {op}")
    return out
