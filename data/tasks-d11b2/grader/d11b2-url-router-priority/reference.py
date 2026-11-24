import re

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _split_path(text):
    if not isinstance(text, str) or not text.startswith("/"):
        raise ValueError("path must start with /")
    if text == "/":
        return []
    parts = text.split("/")[1:]
    if any(part == "" for part in parts):
        raise ValueError("empty path segment")
    return parts


def _parse_template(template):
    parts = _split_path(template)
    parsed = []
    seen = set()
    for i, part in enumerate(parts):
        if part == "*":
            if i != len(parts) - 1:
                raise ValueError("wildcard must be final")
            parsed.append(("wild", None))
        elif part.startswith(":"):
            name = part[1:]
            if not IDENT.fullmatch(name) or name == "wildcard" or name in seen:
                raise ValueError("bad parameter")
            seen.add(name)
            parsed.append(("param", name))
        else:
            parsed.append(("lit", part))
    return parsed


def _prepare(routes):
    if not isinstance(routes, list):
        raise ValueError("routes must be a list")
    prepared = []
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            raise ValueError("route must be a dict")
        name = route.get("name")
        template = route.get("template")
        if not isinstance(name, str) or not isinstance(template, str):
            raise ValueError("bad route")
        prepared.append((index, name, _parse_template(template)))
    return prepared


def _rank(kind):
    return {"lit": 2, "param": 1, "wild": 0}[kind]


def _more_specific(a, b):
    pa, pb = a[2], b[2]
    n = min(len(pa), len(pb))
    for i in range(n):
        ra, rb = _rank(pa[i][0]), _rank(pb[i][0])
        if ra != rb:
            return ra > rb
    if len(pa) == len(pb):
        return a[0] < b[0]
    if len(pa) > len(pb):
        if len(pa) == len(pb) + 1 and pa[-1][0] == "wild":
            return False
        return True
    if len(pb) == len(pa) + 1 and pb[-1][0] == "wild":
        return True
    return False


def _match(parsed, parts):
    params = {}
    i = 0
    for kind, value in parsed:
        if kind == "wild":
            params["wildcard"] = parts[i:]
            return params
        if i >= len(parts):
            return None
        segment = parts[i]
        if kind == "lit":
            if segment != value:
                return None
        else:
            params[value] = segment
        i += 1
    return params if i == len(parts) else None


def route_request(routes, path):
    path_parts = _split_path(path)
    best = None
    best_params = None
    for item in _prepare(routes):
        params = _match(item[2], path_parts)
        if params is None:
            continue
        if best is None or _more_specific(item, best):
            best = item
            best_params = params
    if best is None:
        return None
    return {"name": best[1], "params": best_params}
