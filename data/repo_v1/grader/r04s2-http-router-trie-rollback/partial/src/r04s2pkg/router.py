from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from r04s2pkg.models import (
    Handler,
    Middleware,
    NextHandler,
    Request,
    Response,
    RouteConflictError,
    RouteEntry,
    RouteMatch,
)
from r04s2pkg.trie import RouteTrie, normalize_pattern


class Router:
    def __init__(self) -> None:
        self._trie = RouteTrie()
        self._middlewares: list[Middleware] = []
        self._routes: list[RouteEntry] = []
        self._match_cache: dict[str, RouteMatch | None] = {}

    @property
    def routes(self) -> list[RouteEntry]:
        return list(self._routes)

    def use(self, middleware: Middleware) -> None:
        self._middlewares.append(middleware)
        self._match_cache.clear()

    def add_route(
        self,
        method: str,
        pattern: str,
        handler: Handler,
        middlewares: list[Middleware] | tuple[Middleware, ...] = (),
    ) -> RouteEntry:
        norm_pattern = normalize_pattern(pattern)
        entry = RouteEntry(
            method=method.upper(),
            pattern=norm_pattern,
            handler=handler,
            middlewares=tuple(middlewares),
        )
        self._trie.insert(entry)
        self._routes.append(entry)
        self._match_cache.clear()
        return entry

    @contextmanager
    def transaction(self) -> Iterator[Router]:
        snapshot_count = len(self._routes)
        try:
            yield self
        except Exception:
            added = self._routes[snapshot_count:]
            for entry in added:
                self._trie.remove(entry.method, entry.pattern)
            raise

    def mount(
        self,
        prefix: str,
        sub_router: Router,
        middlewares: list[Middleware] | tuple[Middleware, ...] = (),
    ) -> None:
        norm_prefix = normalize_pattern(prefix)
        mount_mws = tuple(middlewares) + tuple(sub_router._middlewares)
        with self.transaction():
            for sub_entry in sub_router.routes:
                if norm_prefix == "/":
                    full_pattern = sub_entry.pattern
                elif sub_entry.pattern == "/":
                    full_pattern = norm_prefix
                else:
                    full_pattern = f"{norm_prefix}{sub_entry.pattern}"
                combined_mws = mount_mws + sub_entry.middlewares
                self.add_route(
                    sub_entry.method,
                    full_pattern,
                    sub_entry.handler,
                    middlewares=combined_mws,
                )

    def dispatch(self, request: Request) -> Response:
        norm_path = normalize_pattern(request.path)
        if norm_path in self._match_cache:
            match = self._match_cache[norm_path]
        else:
            match = self._trie.match(norm_path)
            self._match_cache[norm_path] = match

        if match is None:
            return Response(status=404, body="Not Found")

        method = request.method.upper()
        if method not in match.node_handlers:
            allowed = ", ".join(sorted(match.node_handlers.keys()))
            return Response(
                status=405,
                body="Method Not Allowed",
                headers={"Allow": allowed},
            )

        entry = match.node_handlers[method]
        req = Request(
            method=method,
            path=request.path,
            headers=dict(request.headers),
            params=dict(match.params),
            context=dict(request.context),
        )

        chain = tuple(self._middlewares) + entry.middlewares
        return self._execute_chain(chain, entry.handler, req)

    def _execute_chain(
        self,
        middlewares: tuple[Middleware, ...],
        handler: Handler,
        request: Request,
    ) -> Response:
        def build_next(idx: int) -> NextHandler:
            if idx >= len(middlewares):
                return handler

            def next_fn(req: Request) -> Response:
                return middlewares[idx](req, build_next(idx + 1))

            return next_fn

        return build_next(0)(request)
