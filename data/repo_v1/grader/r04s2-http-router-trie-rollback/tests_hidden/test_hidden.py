import pytest
from r04s2pkg import Request, Response, RouteConflictError, Router


def test_method_not_allowed_and_allow_header() -> None:
    router = Router()
    router.add_route("POST", "/items/:id", lambda req: Response(201, "created"))
    router.add_route("DELETE", "/items/:id", lambda req: Response(204, ""))

    res = router.dispatch(Request("GET", "/items/99"))
    assert res.status == 405
    assert res.headers["Allow"] == "DELETE, POST"


def test_wildcard_route_matching() -> None:
    router = Router()
    router.add_route(
        "GET",
        "/assets/*filepath",
        lambda req: Response(200, req.params["filepath"]),
    )

    res = router.dispatch(Request("GET", "/assets/css/theme/dark.css"))
    assert res.status == 200
    assert res.body == "css/theme/dark.css"


def test_subrouter_mount_and_middleware_composition() -> None:
    api = Router()
    v1 = Router()

    def auth_mw(req: Request, call_next):
        req.headers["X-Auth"] = "verified"
        return call_next(req)

    def v1_mw(req: Request, call_next):
        res = call_next(req)
        res.headers["X-API-Version"] = "v1"
        return res

    v1.use(v1_mw)
    v1.add_route(
        "GET",
        "/accounts/:acc_id",
        lambda req: Response(
            200, f"{req.params['acc_id']}:{req.headers.get('X-Auth')}"
        ),
    )

    api.mount("/api/v1", v1, middlewares=[auth_mw])

    res = api.dispatch(Request("GET", "/api/v1/accounts/ac_7"))
    assert res.status == 200
    assert res.body == "ac_7:verified"
    assert res.headers["X-API-Version"] == "v1"


def test_backtracking_from_dead_end_static_branch_to_param() -> None:
    router = Router()
    router.add_route("GET", "/items/export", lambda req: Response(200, "static-export"))
    router.add_route(
        "GET",
        "/items/:id/details",
        lambda req: Response(200, f"details:{req.params['id']}"),
    )

    res_static = router.dispatch(Request("GET", "/items/export"))
    assert res_static.status == 200
    assert res_static.body == "static-export"

    res_backtrack = router.dispatch(Request("GET", "/items/export/details"))
    assert res_backtrack.status == 200
    assert res_backtrack.body == "details:export"


def test_backtracking_from_param_branch_to_wildcard_cleans_up_params() -> None:
    router = Router()
    router.add_route(
        "GET",
        "/docs/:section/edit",
        lambda req: Response(200, f"edit:{req.params['section']}"),
    )
    router.add_route(
        "GET",
        "/docs/*slug",
        lambda req: Response(200, f"keys={sorted(req.params.keys())}|slug={req.params['slug']}"),
    )

    res = router.dispatch(Request("GET", "/docs/guides/intro/install"))
    assert res.status == 200
    assert res.body == "keys=['slug']|slug=guides/intro/install"


def test_backtracking_multi_level_static_to_param_to_wildcard() -> None:
    router = Router()
    router.add_route("GET", "/a/b/c", lambda req: Response(200, "static-abc"))
    router.add_route(
        "GET",
        "/a/:p1/d",
        lambda req: Response(200, f"param-{req.params['p1']}"),
    )
    router.add_route(
        "GET",
        "/a/*rest",
        lambda req: Response(200, f"wild-{req.params['rest']}-{sorted(req.params.keys())}"),
    )

    assert router.dispatch(Request("GET", "/a/b/d")).body == "param-b"
    assert router.dispatch(Request("GET", "/a/b/x")).body == "wild-b/x-['rest']"


def test_mount_conflict_rollback_cleans_routes_list_and_re_mounts() -> None:
    main = Router()
    main.add_route("GET", "/v1/conflict", lambda req: Response(200, "original"))

    sub = Router()
    sub.add_route("GET", "/ok1", lambda req: Response(200, "ok1"))
    sub.add_route("GET", "/ok2", lambda req: Response(200, "ok2"))
    sub.add_route("GET", "/conflict", lambda req: Response(200, "sub-conflict"))

    with pytest.raises(RouteConflictError):
        main.mount("/v1", sub)

    assert len(main.routes) == 1
    assert main.routes[0].pattern == "/v1/conflict"
    assert main.dispatch(Request("GET", "/v1/ok1")).status == 404
    assert main.dispatch(Request("GET", "/v1/ok2")).status == 404
    assert main.dispatch(Request("GET", "/v1/conflict")).body == "original"


def test_transaction_rollback_invalidates_negative_and_positive_match_cache() -> None:
    router = Router()
    router.add_route("GET", "/existing", lambda req: Response(200, "existing"))

    assert router.dispatch(Request("GET", "/temp")).status == 404

    with pytest.raises(RouteConflictError):
        with router.transaction():
            router.add_route("GET", "/temp", lambda req: Response(200, "temp-body"))
            assert router.dispatch(Request("GET", "/temp")).status == 200
            router.add_route("GET", "/existing", lambda req: Response(200, "dup"))

    res_after_rollback = router.dispatch(Request("GET", "/temp"))
    assert res_after_rollback.status == 404
    assert len(router.routes) == 1


def test_mount_rollback_allows_subsequent_clean_mount_into_parent() -> None:
    parent = Router()
    parent.add_route("POST", "/admin/users", lambda req: Response(201, "created"))

    bad_sub = Router()
    bad_sub.add_route("GET", "/audit", lambda req: Response(200, "bad-audit"))
    bad_sub.add_route("POST", "/users", lambda req: Response(200, "conflict"))

    with pytest.raises(RouteConflictError):
        parent.mount("/admin", bad_sub)

    good_sub = Router()
    good_sub.add_route("GET", "/audit", lambda req: Response(200, "good-audit"))

    parent.mount("/admin", good_sub)
    assert len(parent.routes) == 2
    assert parent.dispatch(Request("GET", "/admin/audit")).body == "good-audit"
