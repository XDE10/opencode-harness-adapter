"""Make only the standalone OpenAI route visible to the offline OpenCode task."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import socket

from .relay import LIMIT, ROUTE, UnixHTTP

PORT = 8135


class IngressSocket(UnixHTTP):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect("/bridge/ingress.sock")


class Shim(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def forward(self, data=None):
        conn = IngressSocket("localhost", timeout=10)
        try:
            conn.request(self.command, self.path, data, {"Content-Type": "application/json"})
            response = conn.getresponse()
            body = response.read(LIMIT + 1)
            status, kind = response.status, response.headers.get_content_type()
        except OSError:
            self.send_error(502, "local capture socket unavailable")
            return
        finally:
            conn.close()
        if len(body) > LIMIT:
            self.send_error(502, "local capture reply exceeded byte budget")
            return
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/v1/models":
            self.send_error(404)
            return
        self.forward()

    def do_POST(self):
        if self.path != ROUTE:
            self.send_error(404)
            return
        try:
            count = int(self.headers["Content-Length"])
        except (TypeError, ValueError):
            count = 0
        if not 0 < count <= LIMIT:
            self.send_error(413)
            return
        self.forward(self.rfile.read(count))


if __name__ == "__main__":
    if [name for _, name in socket.if_nameindex()] != ["lo"]:
        raise RuntimeError("shim must not have an external interface")
    with HTTPServer(("127.0.0.1", PORT), Shim) as server:
        print("shim-ready", flush=True)
        server.serve_forever()
