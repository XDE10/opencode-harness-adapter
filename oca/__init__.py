"""Lean single-GPU pipeline: OpenCode rollouts -> engine capture -> LoRA GRPO -> paired eval."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "protocol" / "oca-v4.json").read_text(encoding="utf-8"))
