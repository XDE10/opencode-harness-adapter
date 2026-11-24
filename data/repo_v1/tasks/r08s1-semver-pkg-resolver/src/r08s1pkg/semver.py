from __future__ import annotations
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> Version:
        cleaned = text.strip()
        parts = cleaned.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(f"Invalid version: {text!r}")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class SpecSet:
    def __init__(self, raw: str = "*") -> None:
        self.raw = raw.strip() or "*"
        self._predicates: list[Callable[[Version], bool]] = []
        for token in [t.strip() for t in self.raw.split(",") if t.strip()]:
            self._predicates.append(self._compile_token(token))

    @staticmethod
    def _compile_token(token: str) -> Callable[[Version], bool]:
        if token == "*":
            return lambda v: True
        if token.startswith("^"):
            base = Version.parse(token[1:])
            upper = Version(base.major + 1, 0, 0)
            return lambda v, b=base, u=upper: b <= v < u
        if token.startswith("~"):
            base = Version.parse(token[1:])
            upper = Version(base.major, base.minor + 1, 0)
            return lambda v, b=base, u=upper: b <= v < u
        if token.startswith(">="):
            target = Version.parse(token[2:])
            return lambda v, t=target: v >= t
        if token.startswith("<="):
            target = Version.parse(token[2:])
            return lambda v, t=target: v <= t
        if token.startswith(">"):
            target = Version.parse(token[1:])
            return lambda v, t=target: v > t
        if token.startswith("<"):
            target = Version.parse(token[1:])
            return lambda v, t=target: v < t
        if token.startswith("="):
            target = Version.parse(token[1:])
            return lambda v, t=target: v == t
        target = Version.parse(token)
        return lambda v, t=target: v == t

    def matches(self, version: Version | str) -> bool:
        v = Version.parse(version) if isinstance(version, str) else version
        return all(pred(v) for pred in self._predicates)

    def combine(self, other: SpecSet) -> SpecSet:
        if self.raw == "*":
            return other
        if other.raw == "*":
            return self
        return SpecSet(f"{self.raw},{other.raw}")

    def __repr__(self) -> str:
        return f"SpecSet({self.raw!r})"
