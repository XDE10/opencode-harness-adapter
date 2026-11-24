"""Pi coding agent (`@earendil-works/pi-coding-agent`) harness adapter.

Minimal 4-tool agent (`read,write,edit,bash`) running headless via `pi --mode json -p <prompt>`,
routed cleanly to `CaptureProxy` through per-trial `HOME/.pi/agent/models.json`.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil


def pi_models_config(base_url: str, cfg: dict) -> dict:
    r = cfg["rollout"]
    return {
        "providers": {
            "local": {
                "baseUrl": base_url,
                "api": "openai-completions",
                "apiKey": "unused",
                "models": [
                    {
                        "id": "policy",
                        "name": "Local Policy",
                        "contextWindow": r["max_context_tokens"],
                        "maxTokens": r["max_output_tokens_per_call"],
                    }
                ],
            }
        }
    }


class PiHarness:
    name = "pi"
    aux_mode = "none"  # Every Pi model call is part of the agent policy trajectory

    def resolve_bin(self, cfg: dict, override: str | None = None) -> str:
        return override or os.environ.get("PI_BIN") or cfg.get("pi", {}).get("bin", "pi")

    async def warmup(self, binary: str, cfg: dict):
        return  # Pi requires no runtime npm provider install

    def prepare(self, home: Path, base_url: str, binary: str, prompt: str, cfg: dict) -> tuple[list[str], dict[str, str]]:
        agent_dir = home / ".pi" / "agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "models.json").write_text(
            json.dumps(pi_models_config(base_url, cfg), indent=2) + "\n", encoding="utf-8"
        )
        tools = cfg.get("pi", {}).get("tools", "read,write,edit,bash")
        path_parts = [str(Path(binary).parent)]
        node_bin = shutil.which("node")
        if node_bin:
            node_dir = str(Path(node_bin).parent)
            if node_dir not in path_parts:
                path_parts.append(node_dir)
        path_parts.extend(["/usr/local/bin", "/usr/bin", "/bin"])
        env = {
            "HOME": str(home),
            "PATH": ":".join(path_parts),
            "NO_COLOR": "1",
            "LANG": "C.UTF-8",
        }
        cmd = [
            binary, "--mode", "json", "--provider", "local", "--model", "policy",
            "--tools", tools, "-p", prompt,
        ]
        return cmd, env
