from r04s1pkg import Request, Response, Router


def test_static_route_dispatch() -> None:
    router = Router()
    router.add_route("GET", "/health", lambda req: Response(status=200, body="ok"))

    resp = router.handle(Request("GET", "/health"))
    assert resp.status == 200
    assert resp.body == "ok"


def test_str_param_and_not_found() -> None:
    router = Router()
    router.add_route(
        "GET",
        "/users/{username}",
        lambda req: Response(status=200, body=f"hello {req.params['username']}"),
    )

    ok_resp = router.handle(Request("GET", "/users/alice"))
    assert ok_resp.status == 200
    assert ok_resp.body == "hello alice"

    missing_resp = router.handle(Request("GET", "/unknown/path"))
    assert missing_resp.status == 404
