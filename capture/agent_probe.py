"""Checks performed with the same container template as the OpenCode worker."""

import http.client
import json
import os
from pathlib import Path
import socket
import sys


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


PORT = int(sys.argv[1])
MODEL = sys.argv[2]
ROUTE = "/v1/chat/completions"


def request(method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    try:
        conn.request(method, path, body, {"Content-Type": "application/json", "Authorization": "Bearer dummy"})
        response = conn.getresponse()
        return response.status, response.read(512 * 1024)
    finally:
        conn.close()


def body(text):
    return json.dumps({"stream": True, "model": MODEL, "messages": [{"role": "user", "content": text}]})


interfaces = [name for _, name in socket.if_nameindex()]
check(interfaces == ["lo"], "task has an external interface")
routes = Path("/proc/net/route").read_text().splitlines()[1:]
check(all(row.split()[0] == "lo" for row in routes if row.strip()), "task has a non-loopback route")
expected_mount_absences = ("/ipc", "/workspace", "/var/run/docker.sock", "/root/.aws", "/root/.codex")
check(not any(os.path.lexists(name) for name in expected_mount_absences), "unexpected accessible mount or path")
credential_keys = ("OCA_CAPTURE_SESSION", "OPENAI_API_KEY", "HF_TOKEN", "AWS_SECRET_ACCESS_KEY",
                   "GOOGLE_APPLICATION_CREDENTIALS", "ANTHROPIC_API_KEY", "HTTP_PROXY", "HTTPS_PROXY")
check(not any(key in os.environ for key in credential_keys), "task inherited a credential or proxy variable")
config = json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])
check(config["provider"]["local"]["options"]["apiKey"] == "dummy", "task did not receive an inert API value")
check(request("GET", "/v1/models")[0] == 200, "relay not visible")
check(request("GET", "/ipc/session")[0] == 404, "relay unexpectedly exposes private control path")

first = request("POST", ROUTE, body("probe:replay"))
second = request("POST", ROUTE, body("probe:replay"))
check(first[0] == 200 and first == second, "dedup replay differs")
check(b"synthetic_capture" not in first[1] and b"[DONE]" in first[1], "private frame leaked or stream incomplete")
bad = {}
for kind in ("ids", "logps"):
    status, response = request("POST", ROUTE, body("probe:missing-" + kind))
    check(status == 502 and b"[DONE]" not in response, "invalid engine capture exposed")
    bad[kind] = status
print(json.dumps({"interfaces": interfaces, "non_loopback_routes": 0, "credential_variables_present": [],
                  "private_mounts_accessible": [], "agent_api_credential": "inert_dummy",
                  "external_target_contacted": False, "socket_exported_to_agent": False,
                  "replay_identical": True, "capture_frames_hidden": True, "rejections": bad}))
