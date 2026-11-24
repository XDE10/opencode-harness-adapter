from __future__ import annotations

from r04s1pkg.models import Handler, Middleware, Request, Response
from r04s1pkg.trie import RouteTrie, split_path


class Router:
    def __init__(self) -> None:
        self._trie = RouteTrie()
        self._middlewares: list[Middleware] = []
        self._routes: list[tuple[str, str, Handler, list[Middleware]]] = []

    def use(self, middleware: Middleware) -> None:
        self._middlewares.append(middleware)

    def add_route(
        self,
        method: str,
        pattern: str,
        handler: Handler,
        middlewares: list[Middleware] | None = None,
    ) -> None:
        mw_list = list(middlewares) if middlewares else []
        self._routes.append((method.upper(), pattern, handler, mw_list))
        self._trie.insert(method, pattern, handler, mw_list)

    def mount(self, prefix: str, subrouter: Router) -> None:
        prefix_segs = split_path(prefix)
        prefix_str = "/" + "/".join(prefix_segs) if prefix_segs else ""
        for method, pattern, handler, route_mws in subrouter._routes:
            sub_segs = split_path(pattern)
            full_path = prefix_str + ("/" + "/".join(sub_segs) if sub_segs else "")
            if not full_path:
                full_path = "/"
            combined_mws = list(subrouter._middlewares) + list(route_mws)
            self.add_route(method, full_path, handler, middlewares=combined_mws)

    def handle(self, request: Request) -> Response:
        match = self._trie.match(request.method, request.path)
        global_chain = list(self._middlewares)

        if match is None:
            return self._execute_chain(
                request,
                global_chain,
                lambda _req: Response(status=404, body="Not Found"),
            )

        request.params = dict(match.params)
        target = match.target
        is_head_fallback = False

        if target is None and request.method == "HEAD" and "GET" in match.allowed_methods:
            get_match = self._trie.match("GET", request.path)
            if get_match is not None and get_match.target is not None:
                target = get_match.target
                is_head_fallback = True

        if target is None:
            allowed = set(match.allowed_methods)
            if "GET" in allowed:
                allowed.add("HEAD")
            allowed_header = ", ".join(sorted(allowed))
            return self._execute_chain(
                request,
                global_chain,
                lambda _req: Response(
                    status=405,
                    body="Method Not Allowed",
                    headers={"Allow": allowed_header},
                ),
            )

        full_chain = global_chain + list(target.middlewares)

        def terminal(req: Request) -> Response:
            resp = target.handler(req)
            if is_head_fallback:
                return Response(status=resp.status, body="", headers=dict(resp.headers))
            return resp

        return self._execute_chain(request, full_chain, terminal)

    @staticmethod
    def _execute_chain(
        request: Request,
        middlewares: list[Middleware],
        terminal: Handler,
    ) -> Response:
        handler = terminal
        for mw in reversed(middlewares):
            next_h = handler
            handler = lambda req, _mw=mw, _next=next_h: _mw(req, _next)
        return handler(request)
