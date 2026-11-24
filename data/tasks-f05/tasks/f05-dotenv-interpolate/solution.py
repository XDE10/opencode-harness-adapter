import re

KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "$": "\\$"}


def _parse_line_value(raw):
    raw = raw.split("#", 1)[0].strip()
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return raw[1:-1], False
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        out = []
        i = 1
        while i < len(raw) - 1:
            if raw[i] == "\\" and i + 1 < len(raw) - 1 and raw[i + 1] in ESCAPES:
                out.append(ESCAPES[raw[i + 1]])
                i += 2
            else:
                out.append(raw[i])
                i += 1
        return "".join(out), True
    if raw.startswith(("'", '"')):
        raise ValueError("unclosed quote")
    return raw, True


def _find_closing_brace(text, start):
    depth = 1
    i = start
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            i += 2
            continue
        if text.startswith("${", i):
            depth += 1
            i += 2
            continue
        if text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unclosed variable interpolation")


def _expand(text, raw_map, interp_map, resolved, seen):
    out = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text) and text[i + 1] == "$":
            out.append("$")
            i += 2
        elif text.startswith("${", i):
            end = _find_closing_brace(text, i + 2)
            expr = text[i + 2 : end]
            if ":-" in expr:
                name, default = expr.split(":-", 1)
                val = _resolve_key(name, raw_map, interp_map, resolved, seen)
                out.append(val or _expand(default, raw_map, interp_map, resolved, seen))
            elif "-" in expr:
                name, default = expr.split("-", 1)
                val = _resolve_key(name, raw_map, interp_map, resolved, seen)
                out.append(val or _expand(default, raw_map, interp_map, resolved, seen))
            else:
                out.append(_resolve_key(expr, raw_map, interp_map, resolved, seen))
            i = end + 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _resolve_key(key, raw_map, interp_map, resolved, seen):
    if key in seen:
        raise ValueError(f"cycle detected at {key}")
    if key in resolved:
        return resolved[key]
    if key not in raw_map:
        return ""
    seen.add(key)
    val = _expand(raw_map[key], raw_map, interp_map, resolved, seen) if interp_map[key] else raw_map[key]
    resolved[key] = val
    return val


def parse_dotenv(text, overrides=None):
    raw_map, interp_map = {}, {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export") and len(stripped) > 6 and stripped[6] in (" ", "\t"):
            stripped = stripped[6:].lstrip()
        if "=" not in stripped:
            raise ValueError(f"invalid line: {line}")
        key, val = stripped.split("=", 1)
        key = key.strip()
        if not KEY_RE.match(key):
            raise ValueError(f"invalid key: {key}")
        parsed, should_interp = _parse_line_value(val.lstrip())
        raw_map[key] = parsed
        interp_map[key] = should_interp
    resolved = dict(overrides or {})
    for key in resolved:
        raw_map[key] = resolved[key]
        interp_map[key] = False
    return {k: _resolve_key(k, raw_map, interp_map, resolved, set()) for k in raw_map}
