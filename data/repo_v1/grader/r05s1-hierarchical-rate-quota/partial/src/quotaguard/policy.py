from dataclasses import dataclass

UNIT_SECONDS: dict[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
}


@dataclass(frozen=True)
class RatePolicy:
    name: str
    limit: int
    window_seconds: int
    burst_capacity: float

    @property
    def refill_rate_per_sec(self) -> float:
        return float(self.limit) / float(self.window_seconds)


def parse_policy(name: str, spec: str) -> RatePolicy:
    tokens = spec.strip().split()
    if not tokens:
        raise ValueError("Empty policy specification")

    rate_part = tokens[0]
    if "/" not in rate_part:
        raise ValueError(f"Invalid rate format: {rate_part}")

    limit_str, unit_str = rate_part.split("/", 1)
    if unit_str not in UNIT_SECONDS:
        raise ValueError(f"Unsupported time unit: {unit_str}")

    limit = int(limit_str)
    if limit <= 0:
        raise ValueError("Limit must be positive")

    window_seconds = UNIT_SECONDS[unit_str]
    burst_capacity = float(limit)

    for extra in tokens[1:]:
        if extra.startswith("burst="):
            burst_val = float(int(extra.split("=", 1)[1]))
            if burst_val < limit:
                raise ValueError("Burst capacity cannot be less than limit")
            burst_capacity = burst_val
        else:
            raise ValueError(f"Unknown policy parameter: {extra}")

    return RatePolicy(
        name=name,
        limit=limit,
        window_seconds=window_seconds,
        burst_capacity=burst_capacity,
    )
