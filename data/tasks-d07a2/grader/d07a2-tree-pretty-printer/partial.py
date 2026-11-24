def _check_node(node, seen):
    if not isinstance(node, dict) or set(node) != {"id", "label", "children"}:
        raise ValueError
    nid = node["id"]
    label = node["label"]
    children = node["children"]
    if not isinstance(nid, int) or isinstance(nid, bool):
        raise ValueError
    if not isinstance(label, str):
        raise ValueError
    if not isinstance(children, list):
        raise ValueError
    if nid in seen:
        raise ValueError
    seen.add(nid)
    return children


def _validate(nodes):
    if not isinstance(nodes, list):
        raise ValueError
    seen = set()
    def walk(items):
        if not isinstance(items, list):
            raise ValueError
        for node in items:
            children = _check_node(node, seen)
            walk(children)
    walk(nodes)
    return seen


def _ordered(nodes):
    return sorted(nodes, key=lambda n: (n["label"], n["id"]))


def _line(node):
    return f'{node["label"]}#{node["id"]}'


def _emit(node, prefix, is_last, out):
    out.append(prefix + ("└── " if is_last else "├── ") + _line(node))
    child_prefix = prefix + "│   "
    kids = _ordered(node["children"])
    for i, child in enumerate(kids):
        _emit(child, child_prefix, i == len(kids) - 1, out)


def render_tree(nodes):
    _validate(nodes)
    out = []
    roots = _ordered(nodes)
    for node in roots:
        out.append(_line(node))
        kids = _ordered(node["children"])
        for i, child in enumerate(kids):
            _emit(child, "", i == len(kids) - 1, out)
    return out
