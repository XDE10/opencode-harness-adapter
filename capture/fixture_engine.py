"""Hand-scripted tool calls and fake capture fields; no model is used."""

import hmac
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import socketserver

from .relay import IPC, LIMIT, MODEL, ROUTE, encode_event, log

READ = "call_relay_read"
EDIT = "call_relay_edit"
OLD = "return 0 <= index <= length"
NEW = "return 0 <= index < length"


def script_reply(request):
    tools = {entry["function"]["name"]: entry["function"].get("parameters", {})
             for entry in request.get("tools", [])}
    results = {m["tool_call_id"]: str(m.get("content")) for m in request["messages"] if m["role"] == "tool"}
    user = request["messages"][-1].get("content")
    missing = ({"probe:missing-ids": "prompt_token_ids", "probe:missing-logps": "per_token_logps"}.get(user)
               if isinstance(user, str) else None)
    prompt, completion, trained = [30, 31], [40], [1]
    finish = "stop"
    if results.get(EDIT):
        # Simulate a context rewrite at the engine boundary.
        purpose, delta = "final", {"content": "The interval endpoint is now exclusive."}
        prompt, completion = [90, 91, 92], [93]
    elif OLD in results.get(READ, "") and "edit" in tools:
        purpose = "edit"
        names = tools["edit"]["properties"]
        old = next(field for field in ("oldString", "oldText", "old") if field in names)
        new = next(field for field in ("newString", "newText", "new") if field in names)
        tool = "edit", EDIT, {"path": "/work/solution.py", old: OLD, new: NEW}
        prompt, completion, trained = [10, 11, 20, 21, 70, 71], [22, 23], [1, 1]
    elif not results and "read" in tools:
        purpose = "read"
        tool = "read", READ, {"path": "/work/solution.py"}
        prompt, completion, trained = [10, 11], [20, 21], [1, 0]
    elif not tools and not results:
        purpose = "probe" if isinstance(user, str) and user.startswith("probe:") else "auxiliary"
        delta = {"content": "Synthetic fixture response."}
    else:
        raise ValueError("unexpected tool path")
    if purpose in ("read", "edit"):
        name, call_id, params = tool
        finish = "tool_calls"
        delta = {"tool_calls": [{"index": 0, "id": call_id, "type": "function",
                                 "function": {"name": name, "arguments": json.dumps(params)}}]}
    return purpose, delta, finish, prompt, completion, trained, missing


class Fixture(BaseHTTPRequestHandler):
    expected = None
    interrupted = False

    def log_message(self, *_):
        pass

    def do_POST(self):
        if self.path != ROUTE or not hmac.compare_digest(self.headers.get("Authorization", ""), self.expected):
            self.send_error(403)
            return
        try:
            size = int(self.headers["Content-Length"])
            if not 0 < size <= LIMIT:
                raise ValueError("invalid request size")
            request = json.loads(self.rfile.read(size))
            if request["model"] != MODEL or request["stream"] is not True:
                raise ValueError("unexpected model")
            key = self.headers["X-Request-Hash"]
            purpose, delta, finish, prompt, completion, trained, missing = script_reply(request)
        except (ValueError, TypeError, KeyError, StopIteration) as exc:
            log("fixture_rejected", detail=str(exc))
            self.send_error(400)
            return

        node = "synthetic-" + key[:24]
        turn = {"node_id": node, "purpose": purpose, "prompt_token_ids": prompt,
                "completion_token_ids": completion, "per_token_logps": [-0.2] * len(completion),
                "loss_mask": [0] * len(prompt) + trained}
        if missing:
            del turn[missing]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        first = encode_event(self.chunk(node, {"role": "assistant", **delta}, None))
        if purpose == "read" and not type(self).interrupted:
            type(self).interrupted = True
            self.wfile.write(first)
            self.wfile.flush()
            log("fixture_cut", request_sha256=key)
            return
        try:
            self.wfile.write(first + encode_event(self.chunk(node, {}, finish))
                             + encode_event({"synthetic_capture": turn}) + encode_event("[DONE]"))
        except (BrokenPipeError, ConnectionResetError):
            if not missing:
                raise
            # A rejected capture can be closed by the relay before it reads [DONE].
        log("fixture_completed", request_sha256=key, purpose=purpose)

    @staticmethod
    def chunk(node, delta, finish):
        return {"id": node, "object": "chat.completion.chunk", "created": 1,
                "model": MODEL, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


if __name__ == "__main__":
    Fixture.expected = "Bearer " + Path("/ipc/session").read_text().strip()
    with socketserver.UnixStreamServer(IPC, Fixture) as server:
        log("ready", transport="unix_socket")
        server.serve_forever()
