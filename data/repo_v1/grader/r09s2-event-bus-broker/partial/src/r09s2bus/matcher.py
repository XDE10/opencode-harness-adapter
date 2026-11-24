from typing import Iterable


def topic_matches(pattern: str, topic: str) -> bool:
    """Match a dot-delimited subscription pattern (+ and # wildcards) against a topic."""
    if not pattern or not topic:
        return False

    pat_parts = pattern.split(".")
    top_parts = topic.split(".")

    if any(p == "" for p in pat_parts) or any(t == "" for t in top_parts):
        return False

    memo: dict[tuple[int, int], bool] = {}

    def _match(p_idx: int, t_idx: int) -> bool:
        state = (p_idx, t_idx)
        if state in memo:
            return memo[state]

        if p_idx == len(pat_parts):
            ans = t_idx == len(top_parts)
        elif pat_parts[p_idx] == "#":
            ans = _match(p_idx + 1, t_idx) or (
                t_idx < len(top_parts) and _match(p_idx, t_idx + 1)
            )
        elif t_idx < len(top_parts) and (
            pat_parts[p_idx] == "+" or pat_parts[p_idx] == top_parts[t_idx]
        ):
            ans = _match(p_idx + 1, t_idx + 1)
        else:
            ans = False

        memo[state] = ans
        return ans

    return _match(0, 0)


def filter_matching_patterns(patterns: Iterable[str], topic: str) -> list[str]:
    """Return all patterns from the iterable that match the given topic."""
    return [pattern for pattern in patterns if topic_matches(pattern, topic)]
