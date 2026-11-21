"""Loopback SSE relay for a single synthetic CPU trial."""

from hashlib import sha256
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import socket

from .trace import validate_turn

MODEL = "scripted-relay-v1"
PORT = 8133
IPC = "/ipc/engine.sock"
LIMIT = 512 * 1024
MAX_REQUESTS = 12
MAX_TOKENS = 2048
ROUTE = "/v1/chat/completions"


def log(event, **detail):
    print(json.dumps({"event": event, **detail}, separators=(",", ":")), flush=True)


class StreamInterrupted(RuntimeError):
    pass


class UnixHTTP(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(IPC)


def encode_event(value):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    return f"data: {value}\n\n".encode()


def read_stream(response):
    """Require a full SSE response, including an engine capture and a terminal marker."""
    visible = bytearray()
    capture = None
    seen_bytes = 0
    finished = False
    response_id = None
    while line := response.readline(LIMIT + 1):
        seen_bytes += len(line)
        if seen_bytes > LIMIT:
            raise ValueError("upstream stream exceeded byte budget")
        if not line.strip():
            continue
        if not line.startswith(b"data: "):
            raise ValueError("unsupported synthetic SSE frame")
        data = line[6:].strip()
        if data == b"[DONE]":
            if not finished or capture is None:
                raise ValueError("terminal stream is missing finish frame or engine capture")
            return bytes(visible) + encode_event("[DONE]"), capture
        try:
            event = json.loads(data)
        except json.JSONDecodeError as exc:
            if not line.endswith(b"\n"):
                raise StreamInterrupted("stream broke inside an SSE frame") from exc
            raise
        if not isinstance(event, dict):
            raise ValueError("expected SSE object")
        if "synthetic_capture" in event:
            if capture is not None or not finished:
                raise ValueError("duplicate or early capture")
            capture = event["synthetic_capture"]
            validate_turn(capture)
            if capture["node_id"] != response_id:
                raise ValueError("capture node does not match response ID")
            continue
        if finished or "id" not in event or event["model"] != MODEL or len(event["choices"]) != 1:
            raise ValueError("invalid response order, identity or choices")
        if response_id is not None and event["id"] != response_id:
            raise ValueError("response identity changed within stream")
        response_id = event["id"]
        finished = event["choices"][0]["finish_reason"] is not None
        visible.extend(encode_event(event))
    raise StreamInterrupted("stream closed before [DONE]")


class Relay(BaseHTTPRequestHandler):
    cached = {}
    calls = 0
    completion_tokens = 0
    nodes = set()
    session = None

    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path != "/v1/models":
            self.send_error(404)
            return
        self.reply("application/json", json.dumps(
            {"data": [{"id": MODEL}], "harness_adapter_source": "scripted_mock"}).encode())

    def reply(self, content_type, data):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            log("downstream_disconnected")

    def do_POST(self):
        if self.path != ROUTE:
            self.send_error(404)
            return
        try:
            length = int(self.headers["Content-Length"])
            if not 0 < length <= LIMIT:
                raise ValueError("request exceeds byte budget")
            request = json.loads(self.rfile.read(length))
            if request["model"] != MODEL or request["stream"] is not True or not isinstance(request["messages"], list):
                raise ValueError("expected a streaming request for the scripted model")
            body = json.dumps(request, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()
            key = sha256(body).hexdigest()
        except (TypeError, ValueError, KeyError):
            self.send_error(400, "bad synthetic request")
            return
        state = type(self)
        if key in state.cached:
            log("deduplicated", request_sha256=key)
            self.reply("text/event-stream", state.cached[key])
            return
        if state.calls >= MAX_REQUESTS:
            self.send_error(429, "synthetic request budget exceeded")
            return
        state.calls += 1
        for attempt in (1, 2):
            conn = UnixHTTP("localhost", timeout=5)
            try:
                # The agent's Authorization, Cookie and arbitrary headers are not forwarded.
                conn.request("POST", ROUTE, body, {"Content-Type": "application/json",
                             "Authorization": "Bearer " + state.session, "X-Request-Hash": key})
                response = conn.getresponse()
                if response.status != 200 or response.headers.get_content_type() != "text/event-stream":
                    raise ValueError("synthetic upstream refused the streaming request")
                stream, turn = read_stream(response)
                tokens = len(turn["completion_token_ids"])
                if turn["node_id"] in state.nodes or state.completion_tokens + tokens > MAX_TOKENS:
                    raise ValueError("duplicate engine node or token budget exceeded")
            except (StreamInterrupted, http.client.IncompleteRead, http.client.RemoteDisconnected, ConnectionError, TimeoutError) as exc:
                log("upstream_interrupted", request_sha256=key, attempt=attempt, detail=str(exc))
                if attempt == 2:
                    self.send_error(502, "synthetic stream incomplete after retry")
                    return
                continue
            except (ValueError, TypeError, KeyError, OSError) as exc:
                log("capture_rejected", request_sha256=key, detail=str(exc))
                self.send_error(502, "invalid synthetic engine capture")
                return
            finally:
                conn.close()
            state.nodes.add(turn["node_id"])
            state.completion_tokens += tokens
            state.cached[key] = stream
            log("committed", request_sha256=key, attempt=attempt, synthetic_capture=turn)
            self.reply("text/event-stream", stream)
            return


if __name__ == "__main__":
    if [name for _, name in socket.if_nameindex()] != ["lo"]:
        raise RuntimeError("relay requires a loopback-only network")
    Relay.session = Path("/ipc/session").read_text().strip()
    with HTTPServer(("127.0.0.1", PORT), Relay) as server:
        log("ready", transport="unix_socket")
        server.serve_forever()
