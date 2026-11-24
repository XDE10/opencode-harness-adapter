from r04s3pkg.models import Handler, Middleware, Request, Response
from r04s3pkg.trie import RouteTrie


class Router:
    def __init__(self) -> None:
        self._trie = RouteTrie()
        self._middlewares: list[Middleware] = []

    def use(self, middleware: Middleware) -> None:
        self._middlewares.append(middleware)

    def add_route(
        self,
        method: str,
        pattern: str,
        handler: Handler,
        middlewares: list[Middleware] | None = None,
    ) -> None:
        self._trie.insert(method.upper(), pattern, handler, middlewares)

    def _build_chain(self, middlewares: list[Middleware], terminal: Handler) -> Handler:
        chain = terminal
        for mw in reversed(middlewares):
            prev = chain

            def wrapped(req: Request, _mw: Middleware = mw, _next: Handler = prev) -> Response:
                return _mw(req, _next)

            chain = wrapped
        return chain

    def dispatch(self, request: Request) -> Response:
        method = request.method.upper()
        matched = self._trie.match(request.path)

        if matched is None:
            terminal: Handler = lambda _req: Response(status=404, body="Not Found")
            pipeline = self._build_chain(self._middlewares, terminal)
            return pipeline(request)

        if method not in matched.node.routes:
            allow_header = ", ".join(sorted(matched.node.routes.keys()))
            terminal_405: Handler = lambda _req: Response(
                status=405,
                body="Method Not Allowed",
                headers={"Allow": allow_header},
            )
            pipeline = self._build_chain(self._middlewares, terminal_405)
            return pipeline(request)

        request.params.update(matched.params)
        entry = matched.node.routes[method]
        combined_middlewares = [*self._middlewares, *entry.middlewares]
        pipeline = self._build_chain(combined_middlewares, entry.handler)
        return pipeline(request)
