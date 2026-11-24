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
        text = raw.strip()
        parts = text.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(f"Invalid semantic version: {raw!r}")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class Clause:
    op: str
    target: Version

    def matches(self, version: Version) -> bool:
         handlers: dict[str, Callable[[Version, Version], bool]] = {
            "==": lambda v, t: v == t,
            "!=": lambda v, t: v != t,
            ">=": lambda v, t: v >= t,
            "<=": lambda v, t: v <= t,
            ">": lambda v, t: v > t,
            "<": lambda v, t: v < t,
        }
        return handlers[self.op](version, self.target)


@dataclass(frozen=True)
class ConstraintSpec:
    raw: str
    clauses: tuple[Clause, ...]

    @classmethod
    def parse(cls, expr: str) -> ConstraintSpec:
        tokens = [tok.strip() for tok in expr.split(",") if tok.strip()]
        if not tokens:
            raise ValueError("Empty constraint expression")
        clauses: list[Clause] = []
        for token in tokens:
            clauses.extend(cls._expand_token(token))
        return cls(raw=expr.strip(), clauses=tuple(clauses))

    @classmethod
    def _expand_token(cls, token: str) -> list[Clause]:
        if token.startswith("^"):
            base = Version.parse(token[1:])
            upper = Version(base.major + 1, 0, 0)
            return [Clause(">=", base), Clause("<", upper)]
        if token.startswith("~"):
            base = Version.parse(token[1:])
            upper = Version(base.major, base.minor + 1, 0)
            return [Clause(">=", base), Clause("<", upper)]
        for op in (">=", "<=", "==", "!=", ">", "<"):
            if token.startswith(op):
                return [Clause(op, Version.parse(token[len(op):]))]
        return [Clause("==", Version.parse(token))]

    def matches(self, version: Version) -> bool:
        return all(clause.matches(version) for clause in self.clauses)
