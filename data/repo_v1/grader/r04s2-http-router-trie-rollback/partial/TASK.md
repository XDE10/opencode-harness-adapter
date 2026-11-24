# Issue Report: Trie Backtracking & Sub-Router Transaction Rollback Bugs in `r04s2pkg`

## Summary
Our lightweight HTTP router and middleware dispatcher (`r04s2pkg`) is failing in two production scenarios involving overlapping dynamic route patterns and transactional sub-router mounts.

## Expected Behavioral Specification

### 1. Trie Route Resolution & Priority Backtracking (`trie.py`)
The router supports three segment types in URL patterns:
- **Static segments**: e.g. `/users/profile`
- **Parameter segments**: prefixed with `:` (e.g. `/users/:id/settings`). Matches any single non-empty path segment and captures `params["id"] = segment`.
- **Wildcard segments**: prefixed with `*` (e.g. `/files/*filepath`). Must appear at the end of a pattern. Matches one or more remaining path segments joined by `/` and captures `params["filepath"] = "a/b/c"`.

**Resolution Priority & Backtracking**:
When matching a request path (normalized by stripping leading/trailing `/`), at any trie node:
1. Try an exact **static** child match first.
2. If no static match succeeds (or if a deeper branch inside the static child fails to reach a registered endpoint), **backtrack** and try any **parameter** (`:param`) child.
3. If the parameter branch also fails to reach a node with registered handlers, **backtrack** and try any **wildcard** (`*wildcard`) child.

**Method Dispatch & `405 Method Not Allowed`**:
- A trie node is considered a valid endpoint match **only if** it has at least one registered HTTP method handler (`bool(node.handlers)` is True).
- If a path matches a node with registered handlers, and the requested HTTP method (e.g., `"GET"`) is present in `node.handlers`, that endpoint is selected.
- If a path matches a node that has registered handlers for *other* HTTP methods (e.g., `"POST"` is registered on `/users/:id`, and `"GET /users/123"` is requested), the router should return a `405` response with header `"Allow"` set to a comma-separated sorted list of allowed methods on that path (e.g. `"POST, PUT"`).
- Importantly, if a deeper static prefix has **no terminal endpoint** for the full path (e.g., `/items/export` is registered, and `/items/:id/details` is registered, and a request arrives for `/items/export/details`), the static branch `/items/export` fails to match the remaining `/details` segment. The trie matcher **must backtrack** to `/items/:id/details` (capturing `id="export"`) rather than failing with a `404`!
- Similarly, captured parameters from an aborted branch must not leak into `params` if backtracking falls back to another branch.

### 2. Middleware Pipeline & Transactional Sub-Router Mounting (`router.py`)
`Router` supports:
- Global and scoped middlewares (`Middleware = Callable[[Request, NextHandler], Response]`) executed in outer-to-inner registration order.
- `router.mount(prefix, sub_router, middlewares=...)`: Mounts all routes from `sub_router` under `prefix`, prepending the router's and mount's middlewares before each route's own middlewares.
- **Conflict Resolution & Atomic Rollback**:
  - Registering a duplicate `(method, normalized_pattern)` on the same `Router` (either directly via `add_route` or during `mount`) raises `RouteConflictError` if a handler for that exact method already exists at the resolved trie node.
  - `router.mount(...)` and `router.transaction()` must be **atomic**: if mounting a `sub_router` fails partway through (for example, the 3rd route in `sub_router` conflicts with an existing route), **all** routes added earlier in that `mount()` or `transaction()` block must be rolled back from both the trie and `router.routes`, and the router's lookup cache must be completely invalidated and restored to its pre-mount state.
