from collections import defaultdict


def _build_dag(nodes, edges):
    seen_nodes = set()
    for node in nodes:
        if node in seen_nodes:
            raise ValueError(f"duplicate node: {node}")
        seen_nodes.add(node)

    adj = defaultdict(list)
    indegree = {node: 0 for node in nodes}
    for edge in edges:
        if len(edge) != 2:
            raise ValueError(f"invalid edge: {edge}")
        u, v = edge
        if u not in seen_nodes:
            raise KeyError(u)
        if v not in seen_nodes:
            raise KeyError(v)
        adj[u].append(v)
        indegree[v] += 1
    return adj, indegree


def _select_wave(ready, limit):
    ready.sort()
    return ready[:limit]


def plan_waves(nodes, edges, batch_limit=None):
    if batch_limit is not None and batch_limit < 0:
        raise ValueError(f"invalid batch_limit: {batch_limit}")
    if not nodes:
        if edges:
            raise KeyError(edges[0][0])
        return []

    limit = batch_limit or len(nodes)
    adj, indegree = _build_dag(nodes, edges)
    ready = [node for node in nodes if indegree[node] == 0]
    waves = []
    scheduled = 0

    while ready:
        wave = _select_wave(ready, limit)
        waves.append(wave)
        scheduled += len(wave)

        taken = set(wave)
        next_ready = [node for node in ready if node not in taken]
        for node in wave:
            for nxt in adj[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    next_ready.append(nxt)
        ready = next_ready

    if scheduled != len(nodes):
        raise ValueError("cycle detected in dependency graph")
    return waves
