def _index(by_parent, cid, pid):
    if pid is not None:
        by_parent.setdefault(pid, set()).add(cid)


def _unindex(by_parent, cid, pid):
    if pid is not None:
        holders = by_parent.get(pid)
        if holders is not None:
            holders.discard(cid)
            if not holders:
                del by_parent[pid]


def _snapshot(parents, children, by_parent):
    bad = []
    for pid, cids in by_parent.items():
        if pid not in parents:
            bad.extend(cids)
    return {
        "parents": sorted(parents),
        "children": sorted(children),
        "bad_children": sorted(bad),
    }


def run(ops):
    parents = set()
    children = {}
    by_parent = {}
    out = []
    for op in ops:
        kind = op.get("op")
        if kind == "add_parent":
            pid = op["id"]
            if pid in parents:
                raise ValueError("duplicate parent")
            parents.add(pid)
        elif kind == "del_parent":
            parents.discard(op["id"])
        elif kind == "upsert_child":
            cid = op["id"]
            pid = op["pid"]
            if cid in children:
                _unindex(by_parent, cid, children[cid])
            children[cid] = pid
            _index(by_parent, cid, pid)
        elif kind == "del_child":
            cid = op["id"]
            if cid in children:
                old_pid = children.pop(cid)
                _unindex(by_parent, cid, old_pid)
        elif kind == "reset":
            parents.clear()
            children.clear()
        elif kind == "report":
            out.append(_snapshot(parents, children, by_parent))
        else:
            raise ValueError("unknown op")
    return out
