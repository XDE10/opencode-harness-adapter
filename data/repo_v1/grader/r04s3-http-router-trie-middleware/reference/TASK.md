# Issue Report: Typed Path Parameters & Method Fallback / Middleware Scope in `r04s3pkg`

## Summary
Our lightweight HTTP router and middleware library (`r04s3pkg`) is failing in production under two scenarios:

1. **Typed path parameter routes fail to match or lose type coercion when competing with sibling routes or wildcard suffixes**:
   Routes defined with typed parameter segments like `/items/{item_id:int}` or `/files/{*filepath:path}` are parsed into segment specifications by `r04s3pkg.trie` and matched during request dispatch. Currently, typed parameters (such as `:int`) are either failing to coerce extracted values to their Python type (`int`) or failing to backtrack when a non-numeric segment like `/items/featured` or `/items/abc` is requested alongside a wildcard/untyped sibling route.

2. **HTTP method mismatch returns 404 instead of 405 (with `Allow` header), and route-scoped middlewares leak across requests**:
   When a path matches a node in the routing trie that has handlers registered for other HTTP methods (e.g. `GET`, `POST`), dispatching an unregistered method (e.g. `DELETE`) currently returns `404 Not Found` or misses the required `Allow` header listing the supported methods in sorted comma-separated order (e.g. `"GET, POST"`). Additionally, when route-specific middlewares are attached to a route, dispatching multiple requests causes middleware lists to accumulate or mutate state across dispatches.

## Expected Behavioral Specification

### 1. Path Pattern Parsing & Trie Matching (`r04s3pkg.trie`)
- Static segments match exact segment strings (`"items"`).
- Parameter segments have the syntax `{name}` (default type `str`) or `{name:type}` where `type` is `"str"`, `"int"`, or `"path"`:
  - `str`: matches any single non-empty path segment and produces a `str` value in `Request.params[name]`.
  - `int`: matches a single path segment ONLY if it consists purely of ASCII digits (optionally with a leading `-` for negative integers, i.e. convertible via `int` without whitespace) and produces an `int` value in `Request.params[name]`. If the segment is not a valid integer (e.g. `"abc"`), the `:int` param branch **must not match**, allowing the trie to fall back to untyped `{other:str}` or wildcard branches if present.
  - `path` (or `{*name}` / `{name:path}`): wildcard tail matcher that captures the remainder of the path (one or more remaining segments joined by `"/"`) as a `str` in `Request.params[name]`.
- Matching precedence at each trie level:
  1. Exact static segment match
  2. Typed `:int` parameter segment match (if segment parses as `int`)
  3. Untyped/`:str` parameter segment match
  4. Wildcard (`:path` / `*`) match

### 2. Method Dispatch, `405 Method Not Allowed`, and Middleware Pipeline (`r04s3pkg.router`)
- `Router.add_route(method, pattern, handler, middlewares=None)` registers a handler for `method.upper()` at `pattern`.
- `Router.use(middleware)` registers a global middleware `(request, next_handler) -> Response`.
- Global middlewares run in registration order on **every** matched route (and if a path matches a route node with wrong HTTP method, global middlewares also wrap the generated `405` response handler).
- Route-specific `middlewares` passed to `add_route` run *after* global middlewares and *before* the route handler, in the order provided to `add_route`. Dispatching a request must **never** mutate the router's global middleware list or any route's middleware list across consecutive requests.
- If a request path matches a trie node that has registered handlers, but not for `request.method.upper()`:
  - The router must return a `Response(status=405, body="Method Not Allowed", headers={"Allow": ", ".join(sorted(allowed_methods))})` (still executed through global middlewares).
- If no trie node with any registered handlers matches the path, return `Response(status=404, body="Not Found")` (also executed through global middlewares).
