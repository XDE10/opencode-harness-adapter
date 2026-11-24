from collections import defaultdict
import heapq


def _build_graph(nodes, edges):
    seen_nodes = set()
    for node in nodes:
        if node in seen_nodes:
            raise ValueError(f"duplicate node: {node}")
        seen_nodes.add(node)

    adj = defaultdict(list)
    indegree = {node: 0 for node in nodes}
    seen_edges = set()
    for edge in edges:
        if len(edge) != 2:
            raise ValueError(f"invalid edge: {edge}")
        u, v = edge
        if u not in seen_nodes:
            raise KeyError(u)
        if v not in seen_nodes:
            raise KeyError(v)
        if (u, v) in seen_edges:
            continue
        seen_edges.add((u, v))
        adj[u].append(v)
        indegree[v] += 1
    return adj, indegree


def topo_order(nodes, edges, reverse=False):
    if not nodes:
        if edges:
            u, _ = edges[0]
            raise KeyError(u)
        return []

    adj, indegree = _build_graph(nodes, edges)
    rank = {node: i for i, node in enumerate(sorted(nodes))}
    heap = []
    for node in nodes:
        if indegree[node] == 0:
            key = -rank[node] if reverse else rank[node]
            heapq.heappush(heap, (key, node))

    order = []
    while heap:
        _, current = heapq.heappop(heap)
        order.append(current)
        for nxt in adj[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                key = -rank[nxt] if reverse else rank[nxt]
                heapq.heappush(heap, (key, nxt))

    if len(order) != len(nodes):
        raise ValueError("cycle detected in dependency graph")
    return order
