from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

_RATE_PATTERN = re.compile(r"^\s*(\d+)\s*/\s*(\d+)?\s*([smhd])\s*$")

_UNIT_SECONDS: dict[str, float] = {
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
    "d": 86400.0,
}

_VALID_ALGORITHMS = {"token_bucket", "sliding_window"}


@dataclass(frozen=True)
class QuotaPolicy:
    name: str
    scope: str
    algorithm: str
    limit: int
    window_seconds: float
    burst: int

    @property
    def refill_rate(self) -> float:
        return self.limit / self.window_seconds


def parse_rate_string(rate_str: str) -> tuple[int, float]:
    if not isinstance(rate_str, str):
        raise ValueError("rate must be a string")
    match = _RATE_PATTERN.match(rate_str)
    if not match:
        raise ValueError(f"Invalid rate specification: {rate_str!r}")

    limit = int(match.group(1))
    count_str = match.group(2)
    unit = match.group(3)

    count = int(count_str) if count_str is not None else 1
    if limit <= 0 or count <= 0:
        raise ValueError("Rate limit and window count must be positive integers")

    if count_str is not None:
        window_seconds = float(count)
    else:
        window_seconds = _UNIT_SECONDS[unit]
    return limit, window_seconds


def parse_policy_spec(spec: dict[str, Any]) -> QuotaPolicy:
    name = str(spec.get("name", "")).strip()
    scope = str(spec.get("scope", "")).strip()
    algorithm = str(spec.get("algorithm", "")).strip()
    if not name or not scope:
        raise ValueError("Policy 'name' and 'scope' must be non-empty strings")
    if algorithm not in _VALID_ALGORITHMS:
        raise ValueError(f"Unsupported algorithm: {algorithm!r}")

    limit, window_seconds = parse_rate_string(spec.get("rate", ""))

    raw_burst = spec.get("burst")
    if algorithm == "sliding_window" or raw_burst is None:
        burst = limit
    else:
        burst = int(raw_burst)
        if burst <= 0:
            raise ValueError("burst must be a positive integer")

    return QuotaPolicy(
        name=name,
        scope=scope,
        algorithm=algorithm,
        limit=limit,
        window_seconds=window_seconds,
        burst=burst,
    )
