from r04s2pkg import Request, Response, Router


def test_static_and_param_routing() -> None:
    router = Router()
    router.add_route("GET", "/users/me", lambda req: Response(200, "current-user"))
    router.add_route(
        "GET",
        "/users/:id",
        lambda req: Response(200, f"user-{req.params['id']}"),
    )

    res_me = router.dispatch(Request("GET", "/users/me"))
    assert res_me.status == 200
    assert res_me.body == "current-user"

    res_id = router.dispatch(Request("GET", "/users/42"))
    assert res_id.status == 200
    assert res_id.body == "user-42"


def test_middleware_execution_order() -> None:
    router = Router()
    events: list[str] = []

    def global_mw(req: Request, call_next):
        events.append("global:before")
        res = call_next(req)
        events.append("global:after")
        return res

    def route_mw(req: Request, call_next):
        events.append("route:before")
        res = call_next(req)
        events.append("route:after")
        return res

    router.use(global_mw)
    router.add_route(
        "GET",
        "/ping",
        lambda req: (events.append("handler") or Response(200, "pong")),
        middlewares=[route_mw],
    )

    res = router.dispatch(Request("GET", "/ping"))
    assert res.status == 200
    assert events == [
        "global:before",
        "route:before",
        "handler",
        "route:after",
        "global:after",
    ]
