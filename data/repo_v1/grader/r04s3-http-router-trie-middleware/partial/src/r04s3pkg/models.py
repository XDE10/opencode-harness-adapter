from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Request:
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class Response:
    status: int = 200
    body: Any = ""
    headers: dict[str, str] = field(default_factory=dict)


Handler = Callable[[Request], Response]
Middleware = Callable[[Request, Handler], Response]


@dataclass(frozen=True)
class SegmentSpec:
    raw: str
    kind: str  # "static", "param", "wildcard"
    name: str
    param_type: str = "str"  # "str", "int", "path"

    def coerce(self, value: str) -> tuple[bool, Any]:
        if self.param_type == "int":
            stripped = value.strip()
            if stripped != value or not value:
                return False, None
            if value.startswith("-"):
                if len(value) > 1 and value[1:].isdigit():
                    return True, int(value)
                return False, None
            if value.isdigit():
                return True, int(value)
            return False, None
        return True, value
