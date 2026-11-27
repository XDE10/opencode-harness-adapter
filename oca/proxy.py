"""Capture proxy between coding agent harnesses (OpenCode / Pi) and vLLM.

Each trial connects to  http://127.0.0.1:<port>/t/<trial_id>/v1  (OpenAI-compatible).
For every call the proxy:
- Forwards a non-streaming request to vLLM with `return_token_ids` + `logprobs`;
- Records exact engine prompt/completion token IDs and processed behaviour logprobs;
- Optionally runs real in-the-loop SafeAgents tool-call interception (`safe_intercept=True`),
  rewriting forbidden bash/edit tool calls into deterministic refusal responses BEFORE the
  harness executes them so the policy learns safe recovery trajectories in-loop;
- Enforces per-trial call/token budgets safely under concurrency and replays SSE to the harness.
"""
import asyncio
import json
import re
import time
import uuid

from aiohttp import ClientSession, ClientTimeout, web

from .reward import detect_bash_hacks

_PROTECTED_PATH_RE = re.compile(r"(^|[\\/])(TASK\.md|tests[\\/]|tests_hidden[\\/]|grader[\\/])", re.IGNORECASE)
_PROTECTED_PATH_NO_TESTS_RE = re.compile(r"(^|[\\/])(TASK\.md|tests_hidden[\\/]|grader[\\/])", re.IGNORECASE)


def _inspect_and_sanitize_tool_calls(
    msg: dict,
    protected_paths: set[str] | None = None,
    protect_repo_tests: bool = True,
    allow_requests_lib: bool = False,
) -> list[str]:
    """In-the-loop SafeAgents interceptor: detect & neutralize unsafe tool calls in place.

    Returns list of triggered reason codes (empty if clean).
    """
    reasons: list[str] = []
    tcs = msg.get("tool_calls") or []
    path_re = _PROTECTED_PATH_RE if protect_repo_tests else _PROTECTED_PATH_NO_TESTS_RE
    for tc in tcs:
        fn = tc.get("function") or {}
        name = (fn.get("name") or "").lower()
        raw_args = fn.get("arguments") or ""
        try:
            parsed = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args if isinstance(raw_args, dict) else {})
        except ValueError:
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}

        if name in ("bash", "shell", "exec", "run_command", "terminal"):
            cmd = ""
            cmd_key = "command"
            for k in ("command", "cmd", "script", "input"):
                if isinstance(parsed.get(k), str):
                    cmd = parsed[k]
                    cmd_key = k
                    break
            hits = detect_bash_hacks(cmd or str(raw_args), allow_requests_lib=allow_requests_lib)
            if hits:
                reasons.extend(hits)
                safe_msg = f"[SafeAgents BLOCKED: {','.join(sorted(set(hits)))}] Forbidden shell command; stay inside workspace source files."
                if parsed:
                    parsed[cmd_key] = f"printf '%s\\n' {json.dumps(safe_msg)} && exit 126"
                    fn["arguments"] = json.dumps(parsed)
                else:
                    fn["arguments"] = json.dumps({"command": f"printf '%s\\n' {json.dumps(safe_msg)} && exit 126"})
        elif name in ("edit", "write", "write_file", "patch"):
            target_path = ""
            for k in ("filePath", "file_path", "path", "file"):
                if isinstance(parsed.get(k), str):
                    target_path = parsed[k]
                    break
            norm_p = target_path.replace("\\", "/").lstrip("./")
            is_protected = (norm_p in (protected_paths or set())) or bool(path_re.search(norm_p))
            if is_protected:
                reasons.append("protected_file_edit")
                # Neutralize write/edit into a harmless no-op error path so TASK.md / tests/ stay untouched
                for k in ("filePath", "file_path", "path", "file"):
                    if k in parsed:
                        parsed[k] = ".safeagents_blocked_readonly_target"
                if "oldString" in parsed:
                    parsed["oldString"] = "__SAFEAGENTS_BLOCKED_EDIT_PROTECTED_FILE__"
                fn["arguments"] = json.dumps(parsed)

    return sorted(set(reasons))


class Trial:
    def __init__(self, trial_id, model, seed, budget, aux_mode="no_tools",
                 safe_intercept=False, protected_paths=None,
                 protect_repo_tests=True, allow_requests_lib=False):
        self.id, self.model, self.seed, self.budget = trial_id, model, seed, budget
        self.aux_mode = aux_mode  # "no_tools" (OpenCode) | "none" (Pi / all calls trained)
        self.safe_intercept = bool(safe_intercept)
        self.protected_paths = set(protected_paths or ())
        self.protect_repo_tests = bool(protect_repo_tests)
        self.allow_requests_lib = bool(allow_requests_lib)
        self.turns, self.calls, self.completion_tokens = [], 0, 0
        self.last_request_messages = None
        self.exhausted = None
        self.started = time.time()
        self.lock = asyncio.Lock()


class CaptureProxy:
    def __init__(self, upstream, sampling, safe_intercept=False):
        self.upstream = upstream.rstrip("/")
        self.sampling = sampling  # temperature, top_p, enable_thinking, max_output_tokens_per_call
        self.safe_intercept = bool(safe_intercept)
        self.trials = {}
        self.session = None

    # ---------- control plane (in-process) ----------
    def register(self, trial_id, model, seed, budget, aux_mode="no_tools",
                 safe_intercept=None, protected_paths=None,
                 protect_repo_tests=True, allow_requests_lib=False):
        use_safe = self.safe_intercept if safe_intercept is None else bool(safe_intercept)
        self.trials[trial_id] = Trial(
            trial_id, model, seed, budget, aux_mode=aux_mode,
            safe_intercept=use_safe, protected_paths=protected_paths,
            protect_repo_tests=protect_repo_tests, allow_requests_lib=allow_requests_lib,
        )

    def pop(self, trial_id):
        return self.trials.pop(trial_id)

    # ---------- data plane ----------
    async def models(self, request):
        trial = self.trials.get(request.match_info["trial"])
        if trial is None:
            raise web.HTTPNotFound()
        return web.json_response({"object": "list", "data": [{"id": "policy", "object": "model"}]})

    async def chat(self, request):
        trial = self.trials.get(request.match_info["trial"])
        if trial is None:
            raise web.HTTPNotFound(text="unknown trial")
        body = await request.json()
        stream = bool(body.get("stream"))
        budget = trial.budget

        async with trial.lock:
            remaining = budget["max_output_tokens_per_trial"] - trial.completion_tokens
            if trial.calls >= budget["max_model_calls"] or remaining <= 0:
                trial.exhausted = trial.exhausted or (
                    "calls" if trial.calls >= budget["max_model_calls"] else "tokens"
                )
                return web.json_response(
                    {"error": {"message": f"trial budget exhausted ({trial.exhausted})",
                               "type": "budget_exhausted"}},
                    status=429,
                )
            call_index = trial.calls
            trial.calls += 1

        aux = (not body.get("tools")) if trial.aux_mode == "no_tools" else False
        upstream = {
            "model": trial.model,
            "messages": body["messages"],
            "temperature": self.sampling["temperature"],
            "top_p": self.sampling["top_p"],
            "max_tokens": min(int(body.get("max_tokens") or body.get("max_completion_tokens") or 1 << 30),
                              self.sampling["max_output_tokens_per_call"], remaining),
            "logprobs": True,
            "return_token_ids": True,
            "seed": (trial.seed * 1_000_003 + call_index) % (1 << 31),
            "chat_template_kwargs": {"enable_thinking": bool(self.sampling.get("enable_thinking", False))},
            "stream": False,
        }
        for key in ("tools", "tool_choice", "parallel_tool_calls", "stop"):
            if body.get(key) is not None:
                upstream[key] = body[key]
        t0 = time.time()
        async with self.session.post(self.upstream + "/v1/chat/completions", json=upstream) as resp:
            text = await resp.text()
            if resp.status != 200:
                async with trial.lock:
                    trial.turns.append({"call_index": call_index, "aux": aux, "error": text[:2000], "status": resp.status})
                return web.Response(status=resp.status, text=text, content_type="application/json")
        data = json.loads(text)
        choice = data["choices"][0]
        completion_ids = choice.get("token_ids") or []
        logps = [item["logprob"] for item in ((choice.get("logprobs") or {}).get("content") or [])]

        # Preserve original emitted message in trajectory record; sanitize live outgoing message if safe_intercept=True
        raw_message = json.loads(json.dumps(choice["message"]))
        intercepted = []
        if trial.safe_intercept and not aux:
            intercepted = _inspect_and_sanitize_tool_calls(
                choice["message"], trial.protected_paths,
                protect_repo_tests=trial.protect_repo_tests,
                allow_requests_lib=trial.allow_requests_lib,
            )

        turn = {
            "call_index": call_index, "node_id": data["id"], "aux": aux, "model": data.get("model"),
            "prompt_token_ids": data.get("prompt_token_ids") or [],
            "completion_token_ids": completion_ids,
            "per_token_logps": logps,
            "finish_reason": choice.get("finish_reason"),
            "usage": data.get("usage"),
            "latency_s": round(time.time() - t0, 3),
            "message": raw_message,
            "request_message_count": len(body.get("messages") or []),
            "safe_intercepted": intercepted,
        }
        turn["capture_ok"] = bool(turn["prompt_token_ids"]) and len(completion_ids) == len(logps) and bool(completion_ids)
        async with trial.lock:
            trial.turns.append(turn)
            trial.turns.sort(key=lambda x: x["call_index"])
            trial.completion_tokens += len(completion_ids)
            if not aux:
                trial.last_request_messages = body.get("messages")
        if stream:
            try:
                return await self._sse(request, data, body)
            except (ConnectionResetError, BrokenPipeError, Exception):
                # Client process was killed on trial timeout while upstream was generating
                return web.Response(status=499)
        data.pop("prompt_token_ids", None)
        choice.pop("token_ids", None)
        choice.pop("logprobs", None)
        data["model"] = "policy"
        return web.json_response(data)

    async def _sse(self, request, data, body):
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
        await resp.prepare(request)
        msg = data["choices"][0]["message"]
        base = {"id": data["id"], "object": "chat.completion.chunk", "created": data.get("created", int(time.time())),
                "model": "policy"}

        async def emit(delta, finish=None, **extra):
            chunk = {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}], **extra}
            await resp.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")

        await emit({"role": "assistant", "content": ""})
        if msg.get("content"):
            await emit({"content": msg["content"]})
        for i, call in enumerate(msg.get("tool_calls") or []):
            await emit({"tool_calls": [{"index": i, "id": call.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                                        "type": "function",
                                        "function": {"name": call["function"]["name"],
                                                     "arguments": call["function"].get("arguments") or "{}"}}]})
        await emit({}, data["choices"][0].get("finish_reason") or "stop")
        if (body.get("stream_options") or {}).get("include_usage"):
            chunk = {**base, "choices": [], "usage": data.get("usage")}
            await resp.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
        await resp.write(b"data: [DONE]\n\n")
        await resp.write_eof()
        return resp

    async def start(self, host="127.0.0.1", port=8100):
        self.session = ClientSession(timeout=ClientTimeout(total=900))
        app = web.Application(client_max_size=64 << 20)
        app.router.add_get("/t/{trial}/v1/models", self.models)
        app.router.add_post("/t/{trial}/v1/chat/completions", self.chat)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner, host, port).start()
        self.base = f"http://{host}:{port}"
        return self

    async def close(self):
        await self.runner.cleanup()
        await self.session.close()


async def _selftest():
    """Offline check with a fake vLLM upstream: token capture, aux_mode, bloat prevention, SSE replay."""
    async def fake(request):
        body = await request.json()
        assert body["return_token_ids"] and body["logprobs"] and not body["stream"]
        return web.json_response({
            "id": "chatcmpl-x", "created": 1, "model": body["model"], "prompt_token_ids": [1, 2, 3],
            "choices": [{"index": 0, "finish_reason": "tool_calls", "token_ids": [7, 8],
                         "logprobs": {"content": [{"logprob": -0.1}, {"logprob": -0.2}]},
                         "message": {"role": "assistant", "content": None, "tool_calls": [
                             {"id": "c1", "type": "function", "function": {"name": "read", "arguments": "{}"}}]}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2}})
    app = web.Application()
    app.router.add_post("/v1/chat/completions", fake)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 8199).start()
    proxy = await CaptureProxy("http://127.0.0.1:8199", {"temperature": 0.8, "top_p": 1.0, "enable_thinking": False,
                                                         "max_output_tokens_per_call": 64}).start(port=8198)
    proxy.register("t1", "base", 1, {"max_model_calls": 1, "max_output_tokens_per_trial": 100}, aux_mode="no_tools")
    proxy.register("t2", "base", 2, {"max_model_calls": 2, "max_output_tokens_per_trial": 100}, aux_mode="none")
    async with ClientSession() as s:
        async with s.post(proxy.base + "/t/t1/v1/chat/completions", json={
                "model": "policy", "stream": True, "messages": [{"role": "user", "content": "hi"}],
                "tools": [{"type": "function", "function": {"name": "read"}}]}) as r:
            sse = await r.text()
        async with s.post(proxy.base + "/t/t1/v1/chat/completions", json={"messages": [], "tools": [1]}) as r:
            assert r.status == 429
        async with s.post(proxy.base + "/t/t2/v1/chat/completions", json={
                "model": "policy", "stream": False, "messages": [{"role": "user", "content": "hi"}]}) as r:
            assert r.status == 200
    trial = proxy.pop("t1")
    trial2 = proxy.pop("t2")
    assert '"name": "read"' in sse and sse.rstrip().endswith("[DONE]"), sse
    assert trial.turns[0]["completion_token_ids"] == [7, 8] and trial.turns[0]["capture_ok"]
    assert "request_messages" not in trial.turns[0] and trial.last_request_messages is not None
    assert trial.exhausted == "calls"
    assert trial2.turns[0]["aux"] is False
    await proxy.close()
    await runner.cleanup()
    print("proxy selftest OK")


if __name__ == "__main__":
    asyncio.run(_selftest())
