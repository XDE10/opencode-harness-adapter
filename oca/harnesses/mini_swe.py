"""Mini-SWE-Agent (`mini-swe-agent` CLI) pure-local no-Docker OOD 3rd harness adapter.

Used as a strictly held-out unseen 3rd harness (bash-only markdown action protocol, zero context
compaction, #1 on HF Harness Leaderboard) to test true cross-harness generalization of
`OpenCode-LoRA`, `Pi-LoRA`, `Super-Adapter (QR-SVD / Concat-2r)`, and `Joint-Multi-Harness-LoRA`.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil


from oca.paths import resolve_tool_bin


def mini_swe_config_yaml(base_url: str, cfg: dict) -> str:
    r = cfg["rollout"]
    max_calls = int(r.get("max_model_calls", 24))
    max_toks = int(r.get("max_output_tokens_per_call", 2048))
    temp = float(r.get("temperature", 0.8))
    # Pure YAML string (no external PyYAML dependency required)
    return "\n".join([
        "agent:",
        f"  step_limit: {max_calls}",
        "  cost_limit: 0.0",
        "model:",
        '  model_name: "openai/policy"',
        '  cost_tracking: "ignore_errors"',
        "  model_kwargs:",
        '    custom_llm_provider: "openai"',
        f"    api_base: {json.dumps(base_url)}",
        '    api_key: "unused"',
        f"    temperature: {temp}",
        f"    max_tokens: {max_toks}",
        "environment:",
        '  environment_class: "local"',
        "",
    ])


class MiniSweAgentHarness:
    name = "mini_swe"
    aux_mode = "none"

    def resolve_bin(self, cfg: dict, override: str | None = None) -> str:
        return resolve_tool_bin("mini", "mini_swe", cfg, "MINI_SWE_BIN", override)

    async def warmup(self, binary: str, cfg: dict):
        return  # Pure-Python CLI, no runtime package install needed

    def prepare(self, home: Path, base_url: str, binary: str, prompt: str, cfg: dict) -> tuple[list[str], dict[str, str]]:
        cfg_dir = home / ".config" / "mini-swe-agent"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = cfg_dir / "local_oca.yaml"
        cfg_file.write_text(mini_swe_config_yaml(base_url, cfg), encoding="utf-8")

        path_parts = [str(Path(binary).parent), "/usr/local/bin", "/usr/bin", "/bin"]
        env = {
            "HOME": str(home),
            "PATH": ":".join(dict.fromkeys(path_parts)),
            "NO_COLOR": "1",
            "LANG": "C.UTF-8",
            "OPENAI_API_KEY": "unused",
            "OPENAI_API_BASE": base_url,
            "MSWEA_MINI_CONFIG_PATH": str(cfg_file),
            # mini-swe-agent v2 runs an interactive first-run setup wizard (needs a TTY, otherwise "Aborted")
            "MSWEA_CONFIGURED": "true",
            "MSWEA_COST_TRACKING": "ignore_errors",
            "LITELLM_LOG": "ERROR",
        }
        # `-c` REPLACES the default config, so layer our overrides on top of the builtin `mini.yaml`
        # (system/instance templates, observation/format-error templates) via recursive merge.
        cmd = [binary, "-t", prompt, "-y", "--exit-immediately", "-c", "mini.yaml", "-c", str(cfg_file)]
        return cmd, env
