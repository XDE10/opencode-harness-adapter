def _percent_decode(s: str) -> str:
    s = s.replace("+", " ")
    out = bytearray()
    i, n = 0, len(s)
    while i < n:
        if s[i] == "%":
            if i + 2 >= n:
                raise ValueError("Incomplete percent encoding")
            hx = s[i + 1 : i + 3]
            try:
                out.append(int(hx, 16))
            except ValueError as e:
                raise ValueError("Invalid hex in percent encoding") from e
            i += 3
        else:
            out.extend(s[i].encode("utf-8"))
            i += 1
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("Invalid UTF-8 sequence") from e


def _parse_key_path(key: str) -> list[str]:
    if not key:
        raise ValueError("Empty key")
    first_br = key.find("[")
    if first_br == -1:
        if "]" in key:
            raise ValueError("Stray closing bracket")
        return [key]
    root = key[:first_br]
    if not root or "]" in root:
        raise ValueError("Invalid root key")
    path = [root]
    i, n = first_br, len(key)
    while i < n:
        if key[i] != "[":
            raise ValueError("Unexpected characters outside brackets")
        close = key.find("]", i + 1)
        if close == -1:
            raise ValueError("Unclosed bracket")
        sub = key[i + 1 : close]
        if "[" in sub or "]" in sub:
            raise ValueError("Nested brackets not allowed")
        if sub == "" and path[-1] == "":
            raise ValueError("Consecutive empty brackets [] not allowed")
        path.append(sub)
        i = close + 1
    return path


def _has_path(node: object, rest: list[str]) -> bool:
    cur = node
    for seg in rest:
        if seg == "":
            return False
        if not isinstance(cur, dict) or seg not in cur:
            return False
        cur = cur[seg]
    return True


def _insert_path(root: dict, path: list[str], val: str) -> None:
    cur: object = root
    for idx in range(len(path) - 1):
        seg = path[idx]
        nxt = path[idx + 1]
        if seg != "":
            if not isinstance(cur, dict):
                raise ValueError("Type conflict: expected dict")
            if seg not in cur:
                cur[seg] = [] if nxt == "" else {}
            else:
                expected = list if nxt == "" else dict
                if not isinstance(cur[seg], expected):
                    raise ValueError("Type conflict on intermediate node")
            cur = cur[seg]
        else:
            if not isinstance(cur, list):
                raise ValueError("Type conflict: expected list")
            rest = path[idx + 1 :]
            if not cur or not isinstance(cur[-1], dict) or _has_path(cur[-1], rest):
                cur.append({})
            cur = cur[-1]

    last = path[-1]
    if last == "":
        if not isinstance(cur, list):
            raise ValueError("Type conflict: expected list at leaf")
        cur.append(val)
    else:
        if not isinstance(cur, dict):
            raise ValueError("Type conflict: expected dict at leaf")
        if last in cur and not isinstance(cur[last], str):
            raise ValueError("Type conflict: cannot overwrite container with scalar")
        cur[last] = val


def parse_query_string(query: str) -> dict:
    if query.startswith("?"):
        query = query[1:]
    if not query:
        return {}

    result: dict = {}
    for part in query.split("&"):
        if not part:
            continue
        if "=" in part:
            raw_k, raw_v = part.split("=", 1)
        else:
            raw_k, raw_v = part, ""
        k = _percent_decode(raw_k)
        v = _percent_decode(raw_v)
        path = _parse_key_path(k)
        _insert_path(result, path, v)
    return result
