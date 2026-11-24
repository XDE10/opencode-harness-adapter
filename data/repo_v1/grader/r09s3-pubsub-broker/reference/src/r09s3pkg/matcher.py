from dataclasses import dataclass


def split_topic_segments(raw: str, *, allow_wildcards: bool) -> tuple[str, ...]:
    if not isinstance(raw, str) or not raw:
        raise ValueError("Topic or pattern must be a non-empty string")
    segments = tuple(raw.split("."))
    if any(seg == "" for seg in segments):
        raise ValueError(f"Empty segment in '{raw}'")
    if not allow_wildcards:
        for seg in segments:
            if seg in ("*", "#") or "*" in seg or "#" in seg:
                raise ValueError(f"Wildcards not allowed in concrete topic '{raw}'")
    return segments


@dataclass(frozen=True)
class TopicPattern:
    raw: str
    segments: tuple[str, ...]

    def matches(self, topic: str) -> bool:
        topic_segs = split_topic_segments(topic, allow_wildcards=False)
        return _match_segments(self.segments, topic_segs)


def _match_segments(pat: tuple[str, ...], top: tuple[str, ...]) -> bool:
    memo: dict[tuple[int, int], bool] = {}

    def dfs(p_idx: int, t_idx: int) -> bool:
        state = (p_idx, t_idx)
        if state in memo:
            return memo[state]

        if p_idx == len(pat):
            ans = t_idx == len(top)
        elif pat[p_idx] == "#":
            ans = dfs(p_idx + 1, t_idx) or (
                t_idx < len(top) and dfs(p_idx, t_idx + 1)
            )
        elif t_idx == len(top):
            ans = False
        elif pat[p_idx] == "*" or pat[p_idx] == top[t_idx]:
            ans = dfs(p_idx + 1, t_idx + 1)
        else:
            ans = False

        memo[state] = ans
        return ans

    return dfs(0, 0)


def compile_pattern(pattern: str) -> TopicPattern:
    segments = split_topic_segments(pattern, allow_wildcards=True)
    return TopicPattern(raw=pattern, segments=segments)
