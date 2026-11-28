"""Single-GPU colocated Agentic RL for unmodified CLI coding harnesses (OpenCode, Pi, mini-swe-agent)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "protocol" / "oca-v5.json").read_text(encoding="utf-8"))
