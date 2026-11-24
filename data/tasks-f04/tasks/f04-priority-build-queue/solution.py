from collections import defaultdict
import heapq


def _validate_jobs(jobs):
    by_name = {}
    for job in jobs:
        name = job["name"]
        if name in by_name:
            raise ValueError(f"duplicate job: {name}")
        duration = job["duration"]
        if duration <= 0:
            raise ValueError(f"invalid duration for {name}: {duration}")
        by_name[name] = {
            "name": name,
            "priority": job["priority"],
            "duration": duration,
        }
    return by_name


def _build_deps(by_name, deps):
    adj = defaultdict(list)
    indegree = {name: 0 for name in by_name}
    for pair in deps:
        if len(pair) != 2:
            raise ValueError(f"invalid dependency: {pair}")
        prereq, dependent = pair
        if prereq not in by_name:
            raise KeyError(prereq)
        if dependent not in by_name:
            raise KeyError(dependent)
        adj[prereq].append(dependent)
        indegree[dependent] += 1
    return adj, indegree


def _push_job(heap, job):
    key = (-job["priority"], -job["duration"], job["name"])
    heapq.heappush(heap, (key, job["name"]))


def build_sequence(jobs, deps):
    if not jobs:
        if deps:
            raise KeyError(deps[0][0])
        return []

    by_name = _validate_jobs(jobs)
    adj, indegree = _build_deps(by_name, deps)

    heap = []
    for name, job in by_name.items():
        if indegree[name] == 0:
            _push_job(heap, job)

    sequence = []
    while heap:
        _, name = heapq.heappop(heap)
        sequence.append(name)
        for nxt in adj[name]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                _push_job(heap, by_name[nxt])

    if len(sequence) != len(by_name):
        raise ValueError("dependency cycle detected")
    return sequence
