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
        adj = {}
        nodes = set()
        out.append(None)

    def path(s, t):
        if s not in nodes or t not in nodes:
            out.append(None)
            return
        if s == t:
            out.append({"dist": 0, "path": [s]})
            return
        best = {s: (0, [s])}
        heap = [(0, s, [s])]
        while heap:
            d, u, p = heapq.heappop(heap)
            if p != best.get(u, (None, None))[1]:
                continue
            if u == t:
                out.append({"dist": d, "path": p})
                return
            for v, w in adj.get(u, {}).items():
                nd = d + w
                np = p + [v]
                if v not in best or nd < best[v][0]:
                    best[v] = (nd, np)
                    heapq.heappush(heap, (nd, v, np))
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
