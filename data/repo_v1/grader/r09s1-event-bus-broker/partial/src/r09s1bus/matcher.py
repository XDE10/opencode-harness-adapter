from typing import Tuple


def validate_topic(topic: str, allow_wildcards: bool = False) -> Tuple[str, ...]:
    if not isinstance(topic, str) or not topic:
        raise ValueError("Topic must be a non-empty string")
    segments = tuple(topic.split("."))
    if any(seg == "" for seg in segments):
        raise ValueError(f"Invalid empty segment in topic: {topic!r}")
    if not allow_wildcards and any(seg in ("*", "**") for seg in segments):
        raise ValueError(f"Wildcards are not allowed in published topic: {topic!r}")
    return segments


class TopicPattern:
    def __init__(self, pattern: str) -> None:
        self.raw = pattern
        self.segments = validate_topic(pattern, allow_wildcards=True)

    def matches(self, topic: str) -> bool:
        topic_segments = validate_topic(topic, allow_wildcards=False)
        return self._match_segments(0, 0, topic_segments)

    def _match_segments(
        self, pat_idx: int, top_idx: int, topic_segments: Tuple[str, ...]
    ) -> bool:
        while pat_idx < len(self.segments) and self.segments[pat_idx] == "**":
            if self._match_segments(pat_idx + 1, top_idx, topic_segments):
                return True
            if top_idx < len(topic_segments):
                return self._match_segments(pat_idx, top_idx + 1, topic_segments)
            return False

        if pat_idx == len(self.segments) and top_idx == len(topic_segments):
            return True
        if pat_idx == len(self.segments) or top_idx == len(topic_segments):
            return False

        pat_seg = self.segments[pat_idx]
        if pat_seg == "*" or pat_seg == topic_segments[top_idx]:
            return self._match_segments(pat_idx + 1, top_idx + 1, topic_segments)

        return False
