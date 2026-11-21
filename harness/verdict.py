"""Evaluate the independent test manifest against a worker response."""

import json
import time


def result(status, started, **extra):
    return {"status": status, "wall_seconds": round(time.monotonic() - started, 3), **extra}



def evaluate_response(cases, out, err, started):
    try:
        observed = json.loads(out)
        if not isinstance(observed, list) or len(observed) != len(cases):
            raise ValueError("incorrect number of responses")
        if any(not isinstance(item, dict) or set(item) not in ({"raises"}, {"value"})
               or ("raises" in item and not isinstance(item["raises"], str)) for item in observed):
            raise ValueError("invalid response frame")
    except ValueError as exc:
        return result("test_error", started, detail=str(exc), stdout=out, stderr=err)

    outcomes = []
    for case, actual in zip(cases, observed):
        expected = {key: case[key] for key in ("raises", "value") if key in case}
        verdict = "pass" if json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True) else "fail"
        if "raises" in actual and verdict != "pass":
            verdict = "test_error"
        outcomes.append({"id": case["id"], "status": verdict, "expected": expected, "actual": actual})
    status = next((status for status in ("test_error", "fail") if any(
        case["status"] == status for case in outcomes)), "pass")
    return result(status, started, cases=outcomes)
