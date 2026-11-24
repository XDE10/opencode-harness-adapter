def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _parse_hunk(hunk):
    if not isinstance(hunk, list) or not hunk:
        raise ValueError
    old = []
    new = []
    dels = []
    for item in hunk:
        if not isinstance(item, str) or not item:
            raise ValueError
        tag, text = item[0], item[1:]
        if tag == " ":
            old.append(text)
            new.append(text)
        elif tag == "-":
            old.append(text)
            dels.append(text)
        elif tag == "+":
            new.append(text)
        else:
            raise ValueError
    return old, new, dels


def _matches(lines, old, start):
    return 0 <= start and start + len(old) <= len(lines) and lines[start:start + len(old)] == old


def run_patch(ops):
    if not isinstance(ops, list):
        raise ValueError
    lines = []
    cursor = 0
    out = []
    for op in ops:
        if not isinstance(op, dict):
            raise ValueError
        name = op.get("op")
        if name == "load":
            data = op.get("lines")
            if not isinstance(data, list) or any(not isinstance(x, str) for x in data):
                raise ValueError
            lines = list(data)
            cursor = 0
            out.append(None)
        elif name == "seek":
            idx = op.get("index")
            if not _is_int(idx) or idx < 0 or idx > len(lines):
                raise ValueError
            cursor = idx
            out.append(None)
        elif name == "apply":
            old, new, dels = _parse_hunk(op.get("hunk"))
            start = op.get("start", None)
            if start is not None and not _is_int(start):
                raise ValueError
            if start is None:
                pos = None
                for i in range(cursor, len(lines) - len(dels) + 1):
                    if _matches(lines, dels, i):
                        pos = i
                        break
            else:
                pos = start if _matches(lines, dels, start) else None
            if pos is None:
                out.append(False)
                continue
            lines[pos:pos + len(old)] = new
            cursor = pos + len(new)
            out.append(True)
        elif name == "get":
            out.append(list(lines))
        elif name == "cursor":
            out.append(cursor)
        else:
            raise ValueError
    return out
