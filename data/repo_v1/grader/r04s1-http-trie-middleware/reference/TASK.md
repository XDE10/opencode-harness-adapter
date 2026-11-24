# Issue Report: Typed Path Parameter Coercion & Wildcard Sub-router Middleware Dispatch

## Summary
Our lightweight HTTP router package (`r04s1pkg`) supports typed path parameters (`{name:int}`, `{name:str}`, `{name:slug}`), catch-all wildcard routes (`*filepath`), and composable middleware pipelines. Two issues have been reported in production when integrating typed route definitions with the trie matcher and middleware dispatcher:

1. **Typed path parameter validation & coercion (`{param:int}`, `{param:slug}`) during trie matching**:
   - Route patterns use `{name}` (defaults to `str`), `{name:str}`, `{name:int}`, or `{name:slug}`.
   - `int` parameters must match only ASCII decimal integers (optional leading `-` followed by one or more digits `0-9`, e.g. `42`, `-7`) and **must be coerced to Python `int`** in `RouteMatch.params` (and `Request.params`). Non-integer segments (like `"abc"` or `"12.3"`) must not match an `:int` parameter node, allowing the trie to fall back or return 404.
   - `slug` parameters must match only non-empty strings consisting of lowercase ASCII letters, digits, and hyphens (`^[a-z0-9-]+$`), kept as `str`.
   - When multiple sibling parameter branches or static/param/wildcard branches exist at the same depth, priority order is:
     1. Exact static segment match
     2. Typed parameter match (in registration order; if a segment fails type validation for one param node, matching must continue checking other registered param nodes or wildcard fallbacks)
     3. Catch-all wildcard (`*name`), which captures the remaining relative path segments joined by `"/"`.

2. **Middleware chain state & sub-router prefix/method handling**:
   - `Router.handle(request)` dispatches a `Request` through global middleware (`router.use(mw)`) and route-specific middleware (`router.add_route(..., middlewares=[...])`), in outer-to-inner order: `[global_mw_1, global_mw_2, ..., route_mw_1, route_mw_2] -> handler`.
   - Each middleware has signature `mw(request: Request, next_handler: Callable[[Request], Response]) -> Response`.
   - Before any middleware runs (once a route match is found), `request.params` must be populated with a fresh copy of the matched coerced parameters so both global and route middlewares can read `request.params`.
   - If a path matches one or more routes in the trie across any HTTP method, but **none** of the matched route nodes support `request.method`:
     - If `request.method == "HEAD"` and `"GET"` is registered on that matched node, dispatch to the `"GET"` handler (and its middlewares) and return the response with `body=""` (preserving status and headers).
     - Otherwise, return a `405 Method Not Allowed` `Response(status=405, body="Method Not Allowed", headers={"Allow": "<comma-space-separated sorted allowed methods>"})`, where `"Allow"` lists all registered HTTP methods on that matched path (and includes `"HEAD"` whenever `"GET"` is registered). Global middlewares must still wrap 404 and 405 responses!
   - Registering route-specific middlewares on a route must not mutate or leak into the router's global middleware list or subsequent route dispatches.

## Expected Public API
- `Request(method: str, path: str, headers: dict[str, str] = ..., params: dict[str, Any] = ..., context: dict[str, Any] = ...)`
- `Response(status: int = 200, body: str = "", headers: dict[str, str] = ...)`
- `Router`:
  - `use(middleware: Middleware) -> None`
  - `add_route(method: str, pattern: str, handler: Handler, middlewares: list[Middleware] | None = None) -> None`
  - `mount(prefix: str, subrouter: Router) -> None` (mounts all routes from `subrouter` under `prefix`, prepending `subrouter`'s global middlewares before each mounted route's own route middlewares)
  - `handle(request: Request) -> Response`
