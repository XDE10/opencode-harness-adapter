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


def _match(parsed, parts):
    params = {}
    i = 0
    for kind, value in parsed:
        if kind == "wild":
            if i >= len(parts):
                return None
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
    for _, name, parsed in _prepare(routes):
        params = _match(parsed, path_parts)
        if params is not None:
            return {"name": name, "params": params}
    return None
