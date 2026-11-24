from r04s1pkg import Handler, Request, Response, Router


def test_basic_static_and_wildcard_routes() -> None:
    router = Router()
    router.add_route("GET", "/files/readme.txt", lambda req: Response(200, "static-readme"))
    router.add_route("GET", "/files/*filepath", lambda req: Response(200, f"wc:{req.params['filepath']}"))

    r1 = router.handle(Request("GET", "/files/readme.txt"))
    assert r1.status == 200
    assert r1.body == "static-readme"

    r2 = router.handle(Request("GET", "/files/docs/guide/install.md"))
    assert r2.status == 200
    assert r2.body == "wc:docs/guide/install.md"


def test_head_fallback_to_get_clears_body() -> None:
    router = Router()
    router.add_route(
        "GET",
        "/items",
        lambda req: Response(status=200, body="payload-data", headers={"X-Custom": "yes"}),
    )

    resp = router.handle(Request("HEAD", "/items"))
    assert resp.status == 200
    assert resp.body == ""
    assert resp.headers["X-Custom"] == "yes"


def test_global_middleware_ordering_and_404_wrapping() -> None:
    router = Router()
    events: list[str] = []

    def mw1(req: Request, nxt: Handler) -> Response:
        events.append("mw1_in")
        resp = nxt(req)
        events.append("mw1_out")
        resp.headers["X-MW1"] = "1"
        return resp

    def mw2(req: Request, nxt: Handler) -> Response:
        events.append("mw2_in")
        resp = nxt(req)
        events.append("mw2_out")
        return resp

    router.use(mw1)
    router.use(mw2)
    router.add_route("GET", "/ping", lambda req: Response(200, "pong"))

    ok_resp = router.handle(Request("GET", "/ping"))
    assert ok_resp.status == 200
    assert events == ["mw1_in", "mw2_in", "mw2_out", "mw1_out"]

    not_found = router.handle(Request("GET", "/missing"))
    assert not_found.status == 404
    assert not_found.headers.get("X-MW1") == "1"


def test_int_param_coerced_to_python_int() -> None:
    router = Router()
    captured: dict[str, object] = {}

    def handler(req: Request) -> Response:
        captured["val"] = req.params["order_id"]
        captured["type"] = type(req.params["order_id"])
        return Response(200, f"id={req.params['order_id'] + 1}")

    router.add_route("GET", "/orders/{order_id:int}", handler)

    resp = router.handle(Request("GET", "/orders/41"))
    assert resp.status == 200
    assert resp.body == "id=42"
    assert captured["val"] == 41
    assert captured["type"] is int

    neg_resp = router.handle(Request("GET", "/orders/-10"))
    assert neg_resp.status == 200
    assert neg_resp.body == "id=-9"


def test_sibling_typed_param_fallback_int_then_slug_then_wildcard() -> None:
    router = Router()
    router.add_route(
        "GET",
        "/posts/{post_id:int}",
        lambda req: Response(200, f"int:{req.params['post_id']}"),
    )
    router.add_route(
        "GET",
        "/posts/{slug:slug}",
        lambda req: Response(200, f"slug:{req.params['slug']}"),
    )
    router.add_route(
        "GET",
        "/posts/*rest",
        lambda req: Response(200, f"rest:{req.params['rest']}"),
    )

    r_int = router.handle(Request("GET", "/posts/123"))
    assert r_int.status == 200
    assert r_int.body == "int:123"

    r_slug = router.handle(Request("GET", "/posts/hello-world-2"))
    assert r_slug.status == 200
    assert r_slug.body == "slug:hello-world-2"

    r_wc = router.handle(Request("GET", "/posts/INVALID_SLUG!"))
    assert r_wc.status == 200
    assert r_wc.body == "rest:INVALID_SLUG!"


def test_deep_backtracking_across_typed_param_branches() -> None:
    router = Router()
    router.add_route(
        "GET",
        "/api/{version:int}/users/{uid:int}",
        lambda req: Response(200, f"v={req.params['version']},u={req.params['uid']}"),
    )
    router.add_route(
        "GET",
        "/api/{channel:slug}/users/{uname:str}",
        lambda req: Response(200, f"c={req.params['channel']},u={req.params['uname']}"),
    )

    resp = router.handle(Request("GET", "/api/v2-beta/users/john_doe"))
    assert resp.status == 200
    assert resp.body == "c=v2-beta,u=john_doe"


def test_route_middleware_does_not_leak_to_other_routes() -> None:
    router = Router()

    def global_mw(req: Request, nxt: Handler) -> Response:
        req.context.setdefault("trace", []).append("global")
        return nxt(req)

    def admin_mw(req: Request, nxt: Handler) -> Response:
        req.context.setdefault("trace", []).append("admin")
        return nxt(req)

    router.use(global_mw)
    router.add_route(
        "GET",
        "/admin",
        lambda req: Response(200, ",".join(req.context.get("trace", []))),
        middlewares=[admin_mw],
    )
    router.add_route(
        "GET",
        "/public",
        lambda req: Response(200, ",".join(req.context.get("trace", []))),
    )

    r_admin = router.handle(Request("GET", "/admin"))
    assert r_admin.status == 200
    assert r_admin.body == "global,admin"

    r_public = router.handle(Request("GET", "/public"))
    assert r_public.status == 200
    assert r_public.body == "global"


def test_405_method_not_allowed_includes_head_and_runs_global_middleware() -> None:
    router = Router()

    def audit_mw(req: Request, nxt: Handler) -> Response:
        resp = nxt(req)
        resp.headers["X-Audited"] = "true"
        return resp

    router.use(audit_mw)
    router.add_route("GET", "/articles", lambda req: Response(200, "list"))
    router.add_route("POST", "/articles", lambda req: Response(201, "created"))

    resp = router.handle(Request("DELETE", "/articles"))
    assert resp.status == 405
    assert resp.body == "Method Not Allowed"
    assert resp.headers["Allow"] == "GET, HEAD, POST"
    assert resp.headers.get("X-Audited") == "true"


def test_mounted_subrouter_middleware_isolation() -> None:
    api = Router()

    def api_auth_mw(req: Request, nxt: Handler) -> Response:
        req.context.setdefault("mws", []).append("api_auth")
        return nxt(req)

    def item_mw(req: Request, nxt: Handler) -> Response:
        req.context.setdefault("mws", []).append("item")
        return nxt(req)

    api.use(api_auth_mw)
    api.add_route(
        "GET",
        "/items",
        lambda req: Response(200, ",".join(req.context.get("mws", []))),
        middlewares=[item_mw],
    )
    api.add_route(
        "GET",
        "/status",
        lambda req: Response(200, ",".join(req.context.get("mws", []))),
    )

    root = Router()
    root.use(lambda req, nxt: (req.context.setdefault("mws", []).append("root"), nxt(req))[1])
    root.mount("/v1", api)
    root.add_route(
        "GET",
        "/home",
        lambda req: Response(200, ",".join(req.context.get("mws", []))),
    )

    r1 = root.handle(Request("GET", "/v1/items"))
    assert r1.body == "root,api_auth,item"

    r2 = root.handle(Request("GET", "/v1/status"))
    assert r2.body == "root,api_auth"

    r3 = root.handle(Request("GET", "/home"))
    assert r3.body == "root"
