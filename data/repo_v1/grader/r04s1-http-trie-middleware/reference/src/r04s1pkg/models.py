from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
_INT_RE = re.compile(r"^-?[0-9]+$")


@dataclass
class Request:
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.method = self.method.upper()


@dataclass
class Response:
    status: int = 200
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)


Handler = Callable[[Request], Response]
Middleware = Callable[[Request, Handler], Response]


@dataclass(frozen=True)
class ParamSpec:
    name: str
    kind: str = "str"

    @classmethod
    def parse(cls, token: str) -> ParamSpec:
        inner = token[1:-1].strip()
        if ":" in inner:
            name, kind = inner.split(":", 1)
            name, kind = name.strip(), kind.strip()
        else:
            name, kind = inner, "str"
        if not name or kind not in ("str", "int", "slug"):
            raise ValueError(f"Invalid param token: {token}")
        return cls(name=name, kind=kind)

    def coerce(self, raw: str) -> tuple[bool, Any]:
        if raw == "":
            return False, None
        if self.kind == "int":
            if _INT_RE.match(raw):
                return True, int(raw)
            return False, None
        if self.kind == "slug":
            if _SLUG_RE.match(raw):
                return True, raw
            return False, None
        return True, raw


@dataclass
class RouteMatch:
    target: Any
    params: dict[str, Any] = field(default_factory=dict)
    allowed_methods: set[str] = field(default_factory=set)
