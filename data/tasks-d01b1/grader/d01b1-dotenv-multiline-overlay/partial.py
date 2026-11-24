import re

KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}")


def _unescape_double(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        if s[i] == "\\":
            i += 1
            if i >= len(s):
                raise ValueError("Trailing backslash")
            if s[i] == "n":
                out.append("\n")
            elif s[i] in ('"', "\\"):
                out.append(s[i])
            else:
                out.append("\\" + s[i])
        else:
            out.append(s[i])
        i += 1
    return "".join(out)


def _parse_dotenv(text: str) -> dict[str, tuple[str, bool]]:
    lines = text.splitlines()
    n = len(lines)
    i = 0
    env: dict[str, tuple[str, bool]] = {}

    while i < n:
        raw = lines[i]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        line = raw.lstrip()
        if line.startswith("export ") or line.startswith("export\t"):
            line = line[6:].lstrip()
        if "=" not in line:
            raise ValueError("Missing '='")
        k_part, v_part = line.split("=", 1)
        key = k_part.strip()
        if not KEY_RE.match(key):
            raise ValueError(f"Invalid key: {key}")
        v_str = v_part.lstrip(" \t")

        if v_str.startswith('"""'):
            rem = v_str[3:]
            chunks = []
            closed = False
            while True:
                pos = 0
                found_end = -1
                while pos < len(rem):
                    if rem[pos] == "\\":
                        pos += 2
                        continue
                    if rem.startswith('"""', pos):
                        found_end = pos
                        break
                    pos += 1
                if found_end != -1:
                    chunks.append(rem[:found_end])
                    tail = rem[found_end + 3 :].strip()
                    if tail and not tail.startswith("#"):
                        raise ValueError("Trailing chars after triple quote")
                    closed = True
                    break
                chunks.append(rem)
                i += 1
                if i >= n:
                    break
                rem = lines[i]
            if not closed:
                raise ValueError("Unclosed triple quote")
            val = _unescape_double("\n".join(chunks))
            env[key] = (val, True)
        elif v_str.startswith("'"):
            end_idx = v_str.find("'", 1)
            if end_idx == -1:
                raise ValueError("Unclosed single quote")
            tail = v_str[end_idx + 1 :].strip()
            if tail and not tail.startswith("#"):
                raise ValueError("Trailing chars after single quote")
            env[key] = (v_str[1:end_idx], False)
        elif v_str.startswith('"'):
            pos = 1
            end_idx = -1
            while pos < len(v_str):
                if v_str[pos] == "\\":
                    pos += 2
                    continue
                if v_str[pos] == '"':
                    end_idx = pos
                    break
                pos += 1
            if end_idx == -1:
                raise ValueError("Unclosed double quote")
            tail = v_str[end_idx + 1 :].strip()
            if tail and not tail.startswith("#"):
                raise ValueError("Trailing chars after double quote")
            env[key] = (_unescape_double(v_str[1:end_idx]), True)
        else:
            for idx, ch in enumerate(v_part):
                if ch == "#" and idx > 0 and v_part[idx - 1] in (" ", "\t"):
                    v_part = v_part[:idx]
                    break
            env[key] = (v_part.strip(" \t"), True)
        i += 1
    return env


def run_dotenv(ops: list[dict]) -> list:
    layers: dict[str, dict[str, tuple[str, bool]]] = {}
    active: list[str] = []

    def lookup(key: str) -> tuple[str, bool] | None:
        for layer_name in reversed(active):
            layer = layers[layer_name]
            if key in layer:
                return layer[key]
        return None

    def eval_key(key: str, stack: set[str]) -> str:
        if key in stack:
            raise ValueError(f"Cycle detected at {key}")
        entry = lookup(key)
        if entry is None:
            raise KeyError(key)
        raw_val, expandable = entry
        if not expandable:
            return raw_val
        next_stack = stack | {key}

        def repl(m: re.Match) -> str:
            var_name = m.group(1)
            has_fallback = m.group(2) is not None
            fallback = m.group(3) or ""
            if lookup(var_name) is None:
                if has_fallback:
                    return fallback
                raise KeyError(var_name)
            return eval_key(var_name, next_stack)

        return VAR_RE.sub(repl, raw_val)

    results = []
    for op in ops:
        kind = op["op"]
        if kind == "parse":
            layers[op["layer"]] = _parse_dotenv(op["text"])
            results.append("OK")
        elif kind == "activate":
            req = op["layers"]
            for name in req:
                if name not in layers:
                    raise KeyError(name)
            active = list(req)
            results.append("OK")
        elif kind == "resolve":
            k = op["key"]
            if lookup(k) is None:
                results.append(None)
            else:
                results.append(eval_key(k, set()))
        elif kind == "export_all":
            all_keys = set()
            for name in active:
                all_keys.update(layers[name].keys())
            results.append({k: eval_key(k, set()) for k in sorted(all_keys)})
        else:
            raise ValueError(f"Unknown op: {kind}")
    return results
