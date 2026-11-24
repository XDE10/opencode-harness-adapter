from typing import Iterable


def topic_matches(pattern: str, topic: str) -> bool:
    """Match a dot-delimited subscription pattern (+ and # wildcards) against a topic."""
    if not pattern or not topic:
        return False

    pat_parts = pattern.split(".")
    top_parts = topic.split(".")

    if any(p == "" for p in pat_parts) or any(t == "" for t in top_parts):
        return False

    p_idx = 0
    t_idx = 0
    while p_idx < len(pat_parts) and t_idx < len(top_parts):
        token = pat_parts[p_idx]
        if token == "#":
            if p_idx == len(pat_parts) - 1:
                return True
            p_idx += 1
            t_idx += 1
        elif token == "+" or token == top_parts[t_idx]:
            p_idx += 1
            t_idx += 1
        else:
            return False

    return p_idx == len(pat_parts) and t_idx == len(top_parts)


def filter_matching_patterns(patterns: Iterable[str], topic: str) -> list[str]:
    """Return all patterns from the iterable that match the given topic."""
    return [pattern for pattern in patterns if topic_matches(pattern, topic)]
