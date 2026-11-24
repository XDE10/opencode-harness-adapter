from r04s3pkg import Request, Response, Router


def test_root_and_static_precedence() -> None:
    router = Router()
    router.add_route("GET", "/", lambda req: Response(status=200, body="root"))
    router.add_route("GET", "/items/featured", lambda req: Response(status=200, body="featured"))
    router.add_route(
        "GET", "/items/{slug}", lambda req: Response(status=200, body=f"slug:{req.params['slug']}")
    )

    assert router.dispatch(Request("GET", "/")).body == "root"
    assert router.dispatch(Request("GET", "/items/featured")).body == "featured"
    assert router.dispatch(Request("GET", "/items/keyboard")).body == "slug:keyboard"


def test_wildcard_tail_capture() -> None:
    router = Router()
    router.add_route(
        "GET",
        "/assets/{*filepath}",
        lambda req: Response(status=200, body=req.params["filepath"]),
    )

    resp = router.dispatch(Request("GET", "/assets/css/theme/dark.css"))
    assert resp.status == 200
    assert resp.body == "css/theme/dark.css"


def test_global_middleware_execution_order() -> None:
    router = Router()
    events: list[str] = []

    def mw1(req: Request, nxt):
        events.append("mw1_in")
        res = nxt(req)
        events.append("mw1_out")
        return res

    def mw2(req: Request, nxt):
        events.append("mw2_in")
        res = nxt(req)
        events.append("mw2_out")
        return res

    router.use(mw1)
    router.use(mw2)
    router.add_route(
        "GET",
        "/ping",
        lambda req: (events.append("handler") or Response(status=200, body="pong")),
    )

    resp = router.dispatch(Request("GET", "/ping"))
    assert resp.status == 200
    assert events == ["mw1_in", "mw2_in", "handler", "mw2_out", "mw1_out"]


def test_int_param_coercion_to_python_int() -> None:
    router = Router()
    router.add_route(
        "GET",
        "/orders/{order_id:int}",
        lambda req: Response(
            status=200,
            body=(type(req.params["order_id"]).__name__, req.params["order_id"] * 2),
        ),
    )

    resp = router.dispatch(Request("GET", "/orders/42"))
    assert resp.status == 200
    assert resp.body == ("int", 84)


def test_int_param_backtracks_to_str_or_wildcard_on_non_int() -> None:
    router = Router()
    router.add_route(
        "GET",
        "/users/{user_id:int}/profile",
        lambda req: Response(status=200, body=f"int:{req.params['user_id']}"),
    )
    router.add_route(
        "GET",
        "/users/{handle:str}/profile",
        lambda req: Response(status=200, body=f"str:{req.params['handle']}"),
    )

    r_int = router.dispatch(Request("GET", "/users/105/profile"))
    assert r_int.status == 200
    assert r_int.body == "int:105"

    r_str = router.dispatch(Request("GET", "/users/octocat/profile"))
    assert r_str.status == 200
    assert r_str.body == "str:octocat"


def test_int_param_rejects_non_numeric_when_no_fallback() -> None:
    router = Router()
    router.add_route(
        "GET",
        "/invoices/{inv_id:int}",
        lambda req: Response(status=200, body=req.params["inv_id"]),
    )

    resp = router.dispatch(Request("GET", "/invoices/not-a-number"))
    assert resp.status == 404


def test_method_not_allowed_returns_405_with_sorted_allow_header() -> None:
    router = Router()
    router.add_route("POST", "/articles", lambda req: Response(status=201, body="created"))
    router.add_route("GET", "/articles", lambda req: Response(status=200, body="list"))

    def tag_mw(req: Request, nxt):
        res = nxt(req)
        res.headers["X-MW"] = "ran"
        return res

    router.use(tag_mw)

    resp = router.dispatch(Request("DELETE", "/articles"))
    assert resp.status == 405
    assert resp.body == "Method Not Allowed"
    assert resp.headers.get("Allow") == "GET, POST"
    assert resp.headers.get("X-MW") == "ran"


def test_route_scoped_middleware_does_not_leak_across_requests_or_routes() -> None:
    router = Router()
    calls: list[str] = []

    def global_mw(req: Request, nxt):
        calls.append("global")
        return nxt(req)

    def admin_mw(req: Request, nxt):
        calls.append("admin_only")
        return nxt(req)

    router.use(global_mw)
    router.add_route(
        "GET",
        "/admin",
        lambda req: Response(status=200, body="admin"),
        middlewares=[admin_mw],
    )
    router.add_route(
        "GET",
        "/public",
        lambda req: Response(status=200, body="public"),
    )

    router.dispatch(Request("GET", "/admin"))
    assert calls == ["global", "admin_only"]

    calls.clear()
    router.dispatch(Request("GET", "/admin"))
    assert calls == ["global", "admin_only"]

    calls.clear()
    router.dispatch(Request("GET", "/public"))
    assert calls == ["global"]
