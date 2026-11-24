from collections import defaultdict, deque


def _build_graph(nodes, edges):
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


def _initial_ready(nodes, indegree, reverse):
    ready = [node for node in nodes if indegree[node] == 0]
    ready.sort(reverse=reverse)
    return deque(ready)


def _expand_neighbors(node, adj, indegree, reverse):
    unlocked = []
    for nxt in adj[node]:
        indegree[nxt] -= 1
        if indegree[nxt] == 0:
            unlocked.append(nxt)
    unlocked.sort(reverse=reverse)
    return unlocked


def topo_order(nodes, edges, reverse=False):
    if not nodes:
        if edges:
            u, v = edges[0]
            raise KeyError(u)
        return []

    adj, indegree = _build_graph(nodes, edges)
    queue = _initial_ready(nodes, indegree, reverse)
    order = []

    while queue:
        current = queue.popleft()
        order.append(current)
        for nxt in _expand_neighbors(current, adj, indegree, reverse):
            queue.append(nxt)

    return order
