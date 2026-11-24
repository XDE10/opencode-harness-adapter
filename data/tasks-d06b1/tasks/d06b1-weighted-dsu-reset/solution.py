def run(ops):
    parent = {}
    pot = {}
    rank = {}
    known = set()
    out = []

    def ensure(name):
        if not isinstance(name, str):
            raise ValueError
        if name not in parent:
            parent[name] = name
            pot[name] = 0
            rank[name] = 0
            known.add(name)

    def find(x):
        if parent[x] != x:
            root, _ = find(parent[x])
            parent[x] = root
        return parent[x], pot[x]

    for op in ops:
        if not isinstance(op, dict):
            raise ValueError
        kind = op.get("op")
        if kind == "add":
            x = op.get("x")
            y = op.get("y")
            d = op.get("d")
            ensure(x)
            ensure(y)
            if not isinstance(d, int) or isinstance(d, bool):
                raise ValueError
            rx, px = find(x)
            ry, py = find(y)
            if rx == ry:
                out.append({"ok": px - py == d})
            elif rank[rx] < rank[ry]:
                parent[rx] = ry
                pot[rx] = py - px - d
                out.append({"ok": True})
            else:
                parent[ry] = rx
                pot[ry] = px + d - py
                if rank[rx] == rank[ry]:
                    rank[rx] += 1
                out.append({"ok": True})
        elif kind == "diff":
            x = op.get("x")
            y = op.get("y")
            ensure(x)
            ensure(y)
            rx, px = find(x)
            ry, py = find(y)
            if rx == ry:
                out.append({"connected": True, "diff": py - px})
            else:
                out.append({"connected": False, "diff": None})
        elif kind == "components":
            groups = {}
            for name in sorted(known):
                if name not in parent:
                    parent[name] = name
                    pot[name] = 0
                    rank[name] = 0
                root, _ = find(name)
                groups.setdefault(root, []).append(name)
            result = [sorted(group) for group in groups.values()]
            result.sort(key=lambda group: group[0])
            out.append(result)
        elif kind == "reset":
            parent.clear()
            pot.clear()
            rank.clear()
            out.append({"ok": True})
        else:
            raise ValueError
    return out
