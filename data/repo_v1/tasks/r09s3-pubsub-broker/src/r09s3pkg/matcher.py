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
    p_idx = 0
    t_idx = 0
    while p_idx < len(pat) and t_idx < len(top):
        token = pat[p_idx]
        if token == "#":
            if p_idx == len(pat) - 1:
                return True
            next_token = pat[p_idx + 1]
            while t_idx < len(top) and top[t_idx] != next_token:
                t_idx += 1
            p_idx += 1
        elif token == "*":
            p_idx += 1
            t_idx += 1
        else:
            if token != top[t_idx]:
                return False
            p_idx += 1
            t_idx += 1

    return p_idx == len(pat) and t_idx == len(top)


def compile_pattern(pattern: str) -> TopicPattern:
    segments = split_topic_segments(pattern, allow_wildcards=True)
    return TopicPattern(raw=pattern, segments=segments)
