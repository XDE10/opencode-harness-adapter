def _is_id_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_id_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _read_var(cmd: str, i: int, env: dict[str, str]) -> tuple[str, int]:
    n = len(cmd)
    if i < n and cmd[i] == "{":
        end = cmd.find("}", i + 1)
        if end == -1:
            raise ValueError("Unclosed ${")
        name = cmd[i + 1 : end]
        if not name or not _is_id_start(name[0]) or not all(_is_id_char(c) for c in name):
            raise ValueError(f"Invalid variable name: {name}")
        return env.get(name, ""), end + 1
    if i < n and _is_id_start(cmd[i]):
        j = i + 1
        while j < n and _is_id_char(cmd[j]):
            j += 1
        return env.get(cmd[i:j], ""), j
    return "$", i


def _expand_token(parts: list[tuple[str, str]]) -> list[str]:
    open_idx = -1
    close_idx = -1
    comma_indices: list[int] = []
    for idx, (kind, val) in enumerate(parts):
        if kind == "meta":
            if val == "{" and open_idx == -1:
                open_idx = idx
            elif val == "," and open_idx != -1 and close_idx == -1:
                comma_indices.append(idx)
            elif val == "}" and open_idx != -1 and close_idx == -1:
                close_idx = idx
                break
    if open_idx == -1 or close_idx == -1 or not comma_indices:
        return ["".join(v for _, v in parts)]

    prefix = "".join(v for _, v in parts[:open_idx])
    suffix = "".join(v for _, v in parts[close_idx + 1 :])
    bounds = [open_idx] + comma_indices + [close_idx]
    out: list[str] = []
    for a, b in zip(bounds, bounds[1:]):
        alt = "".join(v for _, v in parts[a + 1 : b])
        out.append(prefix + alt + suffix)
    return out


def tokenize_command(cmd: str, env: dict[str, str]) -> list[str]:
    tokens: list[list[tuple[str, str]]] = []
    cur: list[tuple[str, str]] = []
    i, n = 0, len(cmd)

    while i < n:
        ch = cmd[i]
        if ch in " \t\n":
            if cur:
                tokens.append(cur)
                cur = []
            i += 1
        elif ch == "\\":
            if i + 1 >= n:
                raise ValueError("Trailing backslash")
            cur.append(("lit", cmd[i + 1]))
            i += 2
        elif ch == "'":
            end = cmd.find("'", i + 1)
            if end == -1:
                raise ValueError("Unclosed single quote")
            if end > i + 1:
                cur.append(("lit", cmd[i + 1 : end]))
            i = end + 1
        elif ch == '"':
            i += 1
            buf: list[str] = []
            closed = False
            while i < n:
                c = cmd[i]
                if c == '"':
                    closed = True
                    i += 1
                    break
                if c == "\\":
                    if i + 1 >= n:
                        raise ValueError("Unclosed double quote")
                    nxt = cmd[i + 1]
                    if nxt in {'"', "\\", "$", "{", "}"}:
                        buf.append(nxt)
                    else:
                        buf.append("\\" + nxt)
                    i += 2
                elif c == "$":
                    val, i = _read_var(cmd, i + 1, env)
                    buf.append(val)
                else:
                    buf.append(c)
                    i += 1
            if not closed:
                raise ValueError("Unclosed double quote")
            if buf:
                cur.append(("lit", "".join(buf)))
        elif ch == "$":
            val, i = _read_var(cmd, i + 1, env)
            cur.append(("lit", val))
        elif ch in "{,}":
            cur.append(("meta", ch))
            i += 1
        else:
            cur.append(("lit", ch))
            i += 1

    if cur:
        tokens.append(cur)

    result: list[str] = []
    for tok in tokens:
        result.extend(_expand_token(tok))
    return result
