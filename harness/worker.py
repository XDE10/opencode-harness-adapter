"""Evaluate untrusted submission functions inside the offline container."""

import contextlib
import json
import runpy
import sys


def decode(value):
    if isinstance(value, list):
        return [decode(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {"$float"}:
            return float(value["$float"])
        return {key: decode(item) for key, item in value.items()}
    return value


def main():
    request = json.load(sys.stdin)
    responses = []
    # Submission print calls go to stderr and cannot serve as response frames.
    with contextlib.redirect_stdout(sys.stderr):
        namespace = runpy.run_path("/submission/solution.py")
        function = namespace[request["function"]]
        for args in request["inputs"]:
            try:
                value = function(*decode(args))
            except Exception as exc:
                responses.append({"raises": type(exc).__name__})
            else:
                responses.append({"value": value})
    print(json.dumps(responses, ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
