import heapq

def run(ops):
    adj = {}
    nodes = set()
    out = []

    def add(u, v, w):
        if type(w) is not int or w <= 0:
            raise ValueError("weight must be a positive integer")
        adj.setdefault(u, {})[v] = w
        nodes.add(u)
        nodes.add(v)
        out.append(None)

    def remove(u, v):
        if u in adj:
            adj[u].pop(v, None)
        out.append(None)

    def reset():
        adj.clear()
        nodes.clear()
        out.append(None)

    def path(s, t):
        if s not in nodes or t not in nodes:
            out.append(None)
            return
        if s == t:
            out.append({"dist": 0, "path": [s]})
            return
        best = {s: (0, 0, [s])}
        heap = [(0, 0, [s], s)]
        while heap:
            d, h, p, u = heapq.heappop(heap)
            if (d, h, p) != best.get(u):
                continue
            if u == t:
                out.append({"dist": d, "path": p})
                return
            for v, w in adj.get(u, {}).items():
                nd = d + w
                nh = h + 1
                np = p + [v]
                cand = (nd, nh, np)
                if v not in best or cand < best[v]:
                    best[v] = cand
                    heapq.heappush(heap, (nd, nh, np, v))
        out.append(None)

    for op in ops:
        name = op["op"]
        if name == "add":
            add(op["u"], op["v"], op["w"])
        elif name == "remove":
            remove(op["u"], op["v"])
        elif name == "reset":
            reset()
        elif name == "path":
            path(op["s"], op["t"])
        else:
            raise ValueError("unknown op")
    return out
