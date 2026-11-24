from dataclasses import dataclass


@dataclass
class UsageEvent:
    timestamp: int
    amount: int


class SlidingWindowStore:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], list[UsageEvent]] = {}

    def current_usage(self, scope: str, metric: str, window_seconds: int, now: int) -> int:
        events = self._events.get((scope, metric), [])
        cutoff = now - window_seconds + 1
        return sum(ev.amount for ev in events if cutoff <= ev.timestamp <= now)

    def record(self, scope: str, metric: str, amount: int, now: int) -> None:
        key = (scope, metric)
        self._events.setdefault(key, []).append(UsageEvent(timestamp=now, amount=amount))

    def snapshot(self) -> dict[tuple[str, str], list[UsageEvent]]:
        return {
            key: [UsageEvent(ev.timestamp, ev.amount) for ev in events]
            for key, events in self._events.items()
        }

    def restore(self, snap: dict[tuple[str, str], list[UsageEvent]]) -> None:
        self._events = {
            key: [UsageEvent(ev.timestamp, ev.amount) for ev in events]
            for key, events in snap.items()
        }

    def clear_keys(self, keys: list[tuple[str, str]]) -> int:
        removed = 0
        for key in keys:
            if key in self._events:
                del self._events[key]
                removed += 1
        return removed

    def keys(self) -> list[tuple[str, str]]:
        return list(self._events.keys())
