"""Deterministic OpenAI Chat Completions fixture; runs on private loopback."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import socket

PORT = 8127
MODEL = "scripted-smoke-v1"
MAX_CALLS = 4
ORIGINAL = "return 0 <= index <= length"
FIXED = "def is_within(index: int, length: int) -> bool:\n    return 0 <= index < length\n"


def log(**event):
    print(json.dumps(event), flush=True)


def tool_response(name, args):
    return {"tool_calls": [{"index": 0, "id": f"call_smoke_{name}", "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}, "tool_calls"


class Handler(BaseHTTPRequestHandler):
    completion_requests = 0

    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path != "/v1/models":
            self.send_error(404)
            return
        body = json.dumps({"data": [{"id": MODEL}],
                           "harness_adapter_source": "scripted_mock"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        type(self).completion_requests += 1
        number = self.completion_requests
        if number > MAX_CALLS:
            log(event="budget_exhausted", request=number)
            self.send_error(429, "mock completion call budget exhausted")
            return
        try:
            size = int(self.headers["Content-Length"])
            if not 0 < size < 512 * 1024:
                raise ValueError("invalid request size")
            request = json.loads(self.rfile.read(size))
            if request["model"] != MODEL or request["stream"] is not True:
                raise ValueError("unexpected model or nonstreaming request")
            tools = {tool["function"]["name"] for tool in request.get("tools", [])}
            messages = request["messages"]
            results = {msg["tool_call_id"]: msg.get("content")
                       for msg in messages if msg["role"] == "tool"}
            purpose = "task"
            if not tools and not results:
                purpose = "auxiliary_no_tools"
                delta, finish = {"content": "Fix the boundary check"}, "stop"
            elif not results and "read" in tools:
                delta, finish = tool_response("read", {"path": "/work/solution.py"})
            elif results.get("call_smoke_write"):
                delta, finish = {"content": "Updated the exclusive upper bound."}, "stop"
            elif "write" in tools and ORIGINAL in str(results.get("call_smoke_read")):
                delta, finish = tool_response("write", {"path": "/work/solution.py", "content": FIXED})
            else:
                raise ValueError(f"expected read/write tool or tool result "
                                 f"(tools={sorted(tools)}, results={sorted(results)}, "
                                 f"roles={[msg['role'] for msg in messages]})")
        except (ValueError, KeyError, TypeError) as exc:
            log(event="protocol_error", request=number, detail=str(exc))
            self.send_error(400, str(exc))
            return

        log(event="completion", request=number, purpose=purpose, tool_results=list(results),
            tool_requested=delta.get("tool_calls", [{}])[0].get("function", {}).get("name"))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        for content, reason in [({"role": "assistant", **delta}, None), ({}, finish)]:
            response = {"id": f"mock-{number}", "object": "chat.completion.chunk", "created": 1,
                        "model": MODEL, "choices": [{"index": 0, "delta": content,
                                                    "finish_reason": reason}]}
            self.wfile.write(f"data: {json.dumps(response)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


if __name__ == "__main__":
    interfaces = [name for _, name in socket.if_nameindex()]
    if interfaces != ["lo"]:
        raise RuntimeError(f"mock requires loopback-only networking, got {interfaces}")
    with HTTPServer(("127.0.0.1", PORT), Handler) as server:
        log(event="ready", interfaces=interfaces)
        server.serve_forever()
