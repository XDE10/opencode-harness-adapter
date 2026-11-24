from r04s3pkg import Request, Response, Router


def test_basic_static_route() -> None:
    router = Router()
    router.add_route("GET", "/health", lambda req: Response(status=200, body="ok"))

    resp = router.dispatch(Request(method="GET", path="/health"))
    assert resp.status == 200
    assert resp.body == "ok"


def test_basic_string_param_route() -> None:
    router = Router()
    router.add_route(
        "GET",
        "/users/{username}",
        lambda req: Response(status=200, body=f"hello {req.params['username']}"),
    )

    resp = router.dispatch(Request(method="GET", path="/users/alice"))
    assert resp.status == 200
    assert resp.body == "hello alice"


def test_not_found_with_global_middleware() -> None:
    router = Router()

    def add_trace_header(req: Request, nxt):
        res = nxt(req)
        res.headers["X-Trace"] = "1"
        return res

    router.use(add_trace_header)
    resp = router.dispatch(Request(method="GET", path="/missing"))
    assert resp.status == 404
    assert resp.headers.get("X-Trace") == "1"
