"""Probe only the declared local model listing, without generating tokens."""

import http.client
import json
import socket
import sys

MOCK_SOURCE = "scripted_mock"
LIMIT = 128 * 1024


def validate_models(body, model_id, revision):
    if len(body) > LIMIT:
        raise ValueError("model listing exceeded 128 KiB")
    payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("expected an OpenAI-compatible model list")
    if payload.get("harness_adapter_source") == MOCK_SOURCE:
        raise ValueError("scripted mock cannot be used as a model pilot")
    matches = [entry for entry in payload["data"]
               if isinstance(entry, dict) and entry.get("id") == model_id]
    if len(matches) != 1:
        raise ValueError("expected exactly one entry for the declared model ID")
    reported = matches[0].get("revision")
    if reported is not None and reported != revision:
        raise ValueError("server-reported model revision differs from the declared revision")
    return {"revision_source": "server_reported_match" if reported is not None else "operator_declared",
            "weight_identity_verified": False}


def main(port, model_id, revision):
    if [name for _, name in socket.if_nameindex()] != ["lo"]:
        raise ValueError("model network must contain only loopback")
    conn = http.client.HTTPConnection("127.0.0.1", int(port), timeout=5)
    try:
        conn.request("GET", "/v1/models")
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError(f"GET /v1/models returned HTTP {response.status}")
        if response.headers.get_content_type() != "application/json":
            raise ValueError("GET /v1/models did not return application/json")
        return validate_models(response.read(LIMIT + 1), model_id, revision)
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        print(json.dumps(main(*sys.argv[1:])))
    except (OSError, ValueError, http.client.HTTPException) as exc:
        sys.exit(f"Model preflight failed: {exc}")
