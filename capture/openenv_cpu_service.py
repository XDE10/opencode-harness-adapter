"""OpenEnv capture behind a private Unix ingress and its controlled CPU backend."""

from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
import json
import logging
from pathlib import Path
import secrets
import socket
from threading import Thread

from fastapi import FastAPI, Request, Response
import httpx
import uvicorn
from openenv.core.harness import TrainingTrace
from openenv.core.harness.capture.server import create_app

from .budget_transport import BudgetTransport
from .engine_budget import EngineBudget
from .fixture_engine import script_reply
from .relay import LIMIT, ROUTE
from .trace import validate_turn

MODEL = "scripted-openenv-cpu-v1"
FIXTURE_PORT = 8211
SOCKET = "/bridge/ingress.sock"
MAX_CALLS = 6
PER_CALL = 3
PER_TRIAL = 6
SOURCE = "openenv_capture_synthetic_backend"


class FixtureEngine(BaseHTTPRequestHandler):
    """Plain upstream Chat Completions wire fixture, with fake engine metadata."""

    calls = 0
    received_limits = []

    def log_message(self, *_):
        pass

    def do_POST(self):
        if self.path != ROUTE:
            self.send_error(404)
            return
        try:
            length = int(self.headers["Content-Length"])
            if not 0 < length <= LIMIT:
                raise ValueError("bad fixture request size")
            request = json.loads(self.rfile.read(length))
            if (request["model"] != MODEL or request["stream"] is not False
                    or request.get("return_token_ids") is not True or request.get("logprobs") is not True):
                raise ValueError("OpenEnv did not request IDs and logprobs")
            purpose, delta, finish, prompt, completion, _, _ = script_reply(request)
            if request["messages"][-1].get("content") == "probe:missing-logps":
                raise ValueError("unexpected test request")
            # Keep the ordinary tool loop on one branch. These integers are not tokenized text.
            if purpose == "final":
                prompt, completion = [10, 11, 20, 21, 70, 71, 22, 23, 72, 73], [24]
            cap = request["max_tokens"]
            if not len(completion) <= cap <= PER_CALL:
                raise ValueError("unexpected engine output limit")
        except (ValueError, TypeError, KeyError, StopIteration):
            self.send_error(400, "invalid scripted-engine contract")
            return
        type(self).calls += 1
        type(self).received_limits.append(cap)
        body = json.dumps({"id": "fixture-cpu", "object": "chat.completion", "created": 1, "model": MODEL,
            "prompt_token_ids": prompt, "choices": [{"index": 0, "message": {"role": "assistant", **delta},
                "finish_reason": finish, "token_ids": completion,
                "logprobs": {"content": [{"token": f"token_id:{tok}", "logprob": -0.25,
                                          "bytes": None, "top_logprobs": []} for tok in completion]}}],
            "usage": {"prompt_tokens": len(prompt), "completion_tokens": len(completion),
                      "total_tokens": len(prompt) + len(completion)}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def persist(client_result, status, budget):
    trace = TrainingTrace.from_entries(client_result["entries"])
    # Keep the real producer's fields, but exclude conversational text and upstream-local metadata.
    turns = [turn.model_dump(include={"node_id", "prompt_token_ids", "completion_token_ids",
                                      "per_token_logps", "loss_mask"}) for turn in trace.turns]
    for turn in turns:
        validate_turn(turn)
    evidence = {"source": SOURCE, "usable_for_grpo": False, "openenv_version": version("openenv"),
                "export_endpoint": "/sessions/{id}/trace_entries", "turns": turns,
                "fixture_http_calls": FixtureEngine.calls, "upstream_errors": status["upstream_errors"],
                "engine_budget": {"sent_limits": budget.sent_limits, "received_limits": FixtureEngine.received_limits,
                                  "output_tokens": budget.output_tokens}}
    staging = Path("/audit/.trace.tmp")
    staging.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    staging.replace("/audit/openenv-trace.json")


@asynccontextmanager
async def fixture_backend():
    backend = ThreadingHTTPServer(("127.0.0.1", FIXTURE_PORT), FixtureEngine)
    thread = Thread(target=backend.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        backend.shutdown()
        backend.server_close()
        thread.join()


def ingress_app(*, backend_url, served_model, budget, record, source, backend_lifespan,
                provider="openai", sampling=None):
    admin_key = secrets.token_urlsafe(32)
    proxy = create_app(llm_url=backend_url, model=served_model, engine=source, provider=provider,
                       require_registered=True, admin_key=admin_key, max_output_tokens=budget.per_call,
                       max_model_calls=budget.max_calls)
    admin = {"Authorization": "Bearer " + admin_key}

    @asynccontextmanager
    async def lifespan(app):
        async with backend_lifespan():
            # OpenEnv 0.7.0 has no public HTTP transport injection; its pinned client is lazy.
            proxy.state.inference._client = httpx.AsyncClient(base_url=backend_url, timeout=10,
                                                              transport=BudgetTransport(budget, backend_url,
                                                                                        served_model),
                                                              trust_env=False)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=proxy),
                                         base_url="http://openenv.internal", trust_env=False) as client:
                session_config = {"purpose": "train"}
                if sampling is not None:
                    session_config["sampling"] = sampling
                reg = await client.post("/sessions", headers=admin, json=session_config)
                reg.raise_for_status()
                app.state.client = client
                app.state.session_id = reg.json()["session_id"]
                try:
                    yield
                finally:
                    await client.delete("/sessions/" + app.state.session_id, headers=admin)
                    await proxy.state.inference.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/v1/models")
    async def models():
        return {"object": "list", "data": [{"id": served_model}], "harness_adapter_source": source}

    @app.post(ROUTE)
    async def completion(request: Request):
        body = bytearray()
        async for block in request.stream():
            body.extend(block)
            if len(body) > LIMIT:
                return Response(status_code=413)
        result = await app.state.client.post(ROUTE, content=bytes(body), headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + app.state.session_id})
        if len(result.content) > LIMIT:
            return Response(status_code=502)
        if result.is_success:
            session = "/sessions/" + app.state.session_id
            exported = await app.state.client.get(session + "/trace_entries", headers=admin)
            status = await app.state.client.get(session, headers=admin)
            try:
                exported.raise_for_status()
                status.raise_for_status()
                record(exported.json(), status.json(), budget)
            except (httpx.HTTPError, ValueError, KeyError, OSError):
                # Fail closed; credentials and unvalidated engine text never reach the task or evidence.
                return Response(status_code=502, content="OpenEnv capture validation failed")
        return Response(status_code=result.status_code, content=result.content,
                        headers={"Content-Type": result.headers.get("content-type", "application/json")})

    return app


def fixture_app():
    return ingress_app(backend_url=f"http://127.0.0.1:{FIXTURE_PORT}", served_model=MODEL,
                       budget=EngineBudget(max_calls=MAX_CALLS, per_call=PER_CALL, per_trial=PER_TRIAL),
                       record=persist, source=SOURCE, backend_lifespan=fixture_backend)


if __name__ == "__main__":
    if [name for _, name in socket.if_nameindex()] != ["lo"] or version("openenv") != "0.7.0":
        raise RuntimeError("requires isolated loopback and OpenEnv 0.7.0")
    # OpenEnv may log its internal ephemeral session ID, which is not part of the evidence.
    logging.getLogger("intercept").disabled = True
    uvicorn.run(fixture_app(), uds=SOCKET, access_log=False, log_level="warning")
