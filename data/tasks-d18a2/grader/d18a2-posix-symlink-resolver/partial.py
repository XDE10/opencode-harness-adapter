def _absolute_input(cwd, path):
    if path.startswith("/"):
        return path
    if cwd == "/":
        return "/" + path
    return cwd.rstrip("/") + "/" + path


def _node_at(tree, candidate):
    return tree.get(candidate)


def _is_link(node):
    return isinstance(node, dict) and node.get("type") == "link"


def _target_parts(target):
    return [part for part in target.split("/") if part not in ("", ".", "..")]


def _target_of(node):
    target = node.get("target", "")
    if not isinstance(target, str):
        raise TypeError("symlink target must be a string")
    return target


def _canonical(parts):
    return "/" + "/".join(parts)


def resolve_path(tree, path, cwd="/"):
    if not isinstance(path, str) or not isinstance(cwd, str):
        raise TypeError("path and cwd must be strings")
    pending = _absolute_input(cwd, path).split("/")
    resolved = []
    expansions = 0
    i = 0
    while i < len(pending):
        part = pending[i]
        i += 1
        if part == "" or part == ".":
            continue
        if part == "..":
            if resolved:
                resolved.pop()
            continue
        candidate = _canonical(resolved + [part])
        node = _node_at(tree, candidate)
        if _is_link(node):
            expansions += 1
            if expansions > 40:
                raise ValueError("symlink loop")
            target = _target_of(node)
            if target.startswith("/"):
                resolved = []
            pending[i:i] = _target_parts(target)
        else:
            resolved.append(part)
    return _canonical(resolved)
