from __future__ import annotations
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, raw: str) -> Version:
        parts = raw.strip().split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(f"Invalid semver version: {raw!r}")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class ConstraintSpec:
    def __init__(self, raw: str, predicates: list[Callable[[Version], bool]]) -> None:
        self.raw = raw
        self._predicates = predicates

    @classmethod
    def parse(cls, expr: str) -> ConstraintSpec:
        expr = expr.strip()
        if not expr or expr == "*":
            return cls(expr or "*", [lambda v: True])

        predicates: list[Callable[[Version], bool]] = []
        for token in expr.split(","):
            token = token.strip()
            if not token or token == "*":
                continue
            predicates.extend(cls._parse_token(token))
        return cls(expr, predicates)

    @classmethod
    def _parse_token(cls, token: str) -> list[Callable[[Version], bool]]:
        if token.startswith("^"):
            base = Version.parse(token[1:])
            if base.major > 0:
                upper = Version(base.major + 1, 0, 0)
            elif base.minor > 0:
                upper = Version(0, base.minor + 1, 0)
            else:
                upper = Version(0, 0, base.patch + 1)
            return [lambda v, b=base, u=upper: b <= v < u]
        if token.startswith("~"):
            base = Version.parse(token[1:])
            upper = Version(base.major, base.minor + 1, 0)
            return [lambda v, b=base, u=upper: b <= v < u]
        for op in (">=", "<=", "==", "!=", ">", "<"):
            if token.startswith(op):
                target = Version.parse(token[len(op):])
                return [cls._make_op_predicate(op, target)]
        target = Version.parse(token)
        return [lambda v, t=target: v == t]

    @staticmethod
    def _make_op_predicate(op: str, target: Version) -> Callable[[Version], bool]:
        if op == ">=":
            return lambda v, t=target: v >= t
        if op == "<=":
            return lambda v, t=target: v <= t
        if op == ">":
            return lambda v, t=target: v > t
        if op == "<":
            return lambda v, t=target: v < t
        if op == "==":
            return lambda v, t=target: v == t
        if op == "!=":
            return lambda v, t=target: v != t
        raise ValueError(f"Unsupported operator: {op}")

    def matches(self, version: Version) -> bool:
        return all(pred(version) for pred in self._predicates)

    def combine(self, other: ConstraintSpec) -> ConstraintSpec:
        combined_raw = f"{self.raw},{other.raw}" if self.raw != "*" else other.raw
        return ConstraintSpec(combined_raw, [*self._predicates, *other._predicates])
