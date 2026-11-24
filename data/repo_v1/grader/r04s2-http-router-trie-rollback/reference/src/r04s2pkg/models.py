from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


class RouteConflictError(ValueError):
    """Raised when registering a duplicate HTTP method and route pattern."""


@dataclass
class Request:
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    context: dict[str, object] = field(default_factory=dict)


@dataclass
class Response:
    status: int
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)


Handler = Callable[[Request], Response]
NextHandler = Callable[[Request], Response]
Middleware = Callable[[Request, NextHandler], Response]


@dataclass
class RouteEntry:
    method: str
    pattern: str
    handler: Handler
    middlewares: tuple[Middleware, ...] = ()


@dataclass
class RouteMatch:
    node_handlers: dict[str, RouteEntry]
    params: dict[str, str]
