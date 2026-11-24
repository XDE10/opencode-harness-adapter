"""OpenCode 2.2.7 CLI harness adapter (shared XDG cache warmup + JSONL event stream)."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import tempfile

_CACHE_LOCK = asyncio.Lock()
_CACHE_TEMPLATE = Path("/tmp/oca-opencode-cache-tpl")


def opencode_config(base_url: str, cfg: dict) -> dict:
    r = cfg["rollout"]
    return {
        "$schema": "https://opencode.ai/config.json",
        "permission": cfg["opencode"]["permission"],
        "autoupdate": False, "share": "disabled", "lsp": False,
        "model": "local/policy", "small_model": "local/policy",
        "provider": {"local": {
            "npm": "@ai-sdk/openai-compatible",
            "options": {"baseURL": base_url, "apiKey": "unused"},
            "models": {"policy": {"tool_call": True,
                                  "limit": {"context": r["max_context_tokens"],
                                            "output": r["max_output_tokens_per_call"]}}},
        }},
    }


class OpenCodeHarness:
    name = "opencode"
    aux_mode = "no_tools"  # OpenCode issues auxiliary title/summary requests without `tools`

    def resolve_bin(self, cfg: dict, override: str | None = None) -> str:
        return override or os.environ.get("OPENCODE_BIN") or cfg["opencode"]["bin"]

    async def warmup(self, binary: str, cfg: dict):
        """Populate @ai-sdk/openai-compatible into a template cache once so concurrent trials never hit npm."""
        marker = _CACHE_TEMPLATE / ".oca_ready"
        if marker.is_file():
            return
        async with _CACHE_LOCK:
            if marker.is_file():
                return
            from aiohttp import web

            async def _instant_stop(_req):
                return web.json_response({
                    "id": "warmup-1", "object": "chat.completion", "created": 1, "model": "policy",
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                })

            app = web.Application()
            app.router.add_post("/v1/chat/completions", _instant_stop)
            runner = web.AppRunner(app, access_log=None)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            port = site._server.sockets[0].getsockname()[1]

            _CACHE_TEMPLATE.mkdir(parents=True, exist_ok=True)
            whome = Path(tempfile.mkdtemp(prefix="oca-oc-warm-"))
            env = os.environ.copy()
            env.update({
                "HOME": str(whome),
                "XDG_CACHE_HOME": str(_CACHE_TEMPLATE),
                "PATH": f"{Path(binary).parent}:/usr/local/bin:/usr/bin:/bin",
                "OPENCODE_CONFIG_CONTENT": json.dumps(opencode_config(f"http://127.0.0.1:{port}/v1", cfg)),
                "OPENCODE_DISABLE_MODELS_FETCH": "1",
                "OPENCODE_DISABLE_AUTOUPDATE": "1",
                "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
            })
            proc = await asyncio.create_subprocess_exec(
                binary, "run", "--standalone", "--archived", "--auto", "--format", "json",
                "--model", "local/policy", "hi",
                cwd=whome, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=60)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
            await runner.cleanup()
            shutil.rmtree(whome, ignore_errors=True)
            marker.write_text("ok\n", encoding="utf-8")

    def prepare(self, home: Path, base_url: str, binary: str, prompt: str, cfg: dict) -> tuple[list[str], dict[str, str]]:
        if _CACHE_TEMPLATE.is_dir():
            shutil.copytree(_CACHE_TEMPLATE, home / ".cache", dirs_exist_ok=True)
        env = {
            "HOME": str(home),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_STATE_HOME": str(home / ".local" / "state"),
            "PATH": f"{Path(binary).parent}:/usr/local/bin:/usr/bin:/bin",
            "OPENCODE_CONFIG_CONTENT": json.dumps(opencode_config(base_url, cfg)),
            "OPENCODE_DISABLE_MODELS_FETCH": "1",
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
            "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
            "NO_COLOR": "1",
            "LANG": "C.UTF-8",
        }
        cmd = [
            binary, "run", "--standalone", "--archived", "--auto", "--format", "json",
            "--model", "local/policy", prompt,
        ]
        return cmd, env
