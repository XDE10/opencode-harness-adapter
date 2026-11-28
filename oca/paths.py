"""Portable path & binary resolution (zero hardcoded `/content/...` assumptions).

All default directories can be customized via environment variables:
  - `OCA_HOME`: root cache directory (default: `~/.cache/oca`; auto-uses `/content` if `/content/models/qwen35-9b` exists)
  - `OCA_MODEL_PATH`: local base-model directory override (falls back to HF Hub ID `Qwen/Qwen3.5-9B`)
  - `OCA_TOOLS_DIR`: directory containing CLI harness installs (`opencode/bin/opencode`, `pi/bin/pi`)
  - `OCA_SWE_VENVS`: shared pure-Python venv cache for SWE-bench / SWE-smith
  - `OCA_SWE_MIRRORS`: local bare git mirror cache for SWE-bench / SWE-smith
  - `OCA_WORKDIR_ROOT`: fast scratch root for per-trial sandboxes (auto-prefers `/dev/shm/oca_work` when >= 16 GiB free)
  - `OCA_RUNS_DIR`: default output directory for training/evaluation runs (`./runs`)
  - `OPENCODE_BIN` / `PI_BIN` / `MINI_SWE_BIN`: explicit harness CLI binary overrides
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def oca_home() -> Path:
    env = os.environ.get("OCA_HOME", "").strip()
    if env:
        return Path(env).expanduser()
    # Seamless backward compatibility when running on Colab with pre-populated /content
    if os.name != "nt" and Path("/content/models/qwen35-9b").is_dir():
        return Path("/content")
    return Path.home() / ".cache" / "oca"


def default_models_dir() -> Path:
    return oca_home() / "models"


def default_tools_dir() -> Path:
    env = os.environ.get("OCA_TOOLS_DIR", "").strip()
    return Path(env).expanduser() if env else (oca_home() / "tools")


def default_swe_venvs_dir() -> Path:
    env = os.environ.get("OCA_SWE_VENVS", "").strip()
    return Path(env).expanduser() if env else (oca_home() / "swe_venvs")


def default_swe_mirrors_dir() -> Path:
    env = os.environ.get("OCA_SWE_MIRRORS", "").strip()
    return Path(env).expanduser() if env else (oca_home() / "swe_mirrors")


def default_runs_dir() -> Path:
    env = os.environ.get("OCA_RUNS_DIR", "").strip()
    return Path(env).expanduser() if env else (ROOT / "runs")


def resolve_model_path(cfg: dict | None = None) -> str:
    """Resolve base model directory or HuggingFace Hub model ID with zero hardcoding."""
    env = os.environ.get("OCA_MODEL_PATH", "").strip()
    if env:
        return env
    m = (cfg or {}).get("model", {})
    cfg_local = str(m.get("local_path") or "").strip()
    if cfg_local and Path(cfg_local).is_dir():
        return cfg_local
    cached = default_models_dir() / "qwen35-9b"
    if cached.is_dir():
        return str(cached)
    return str(m.get("id") or "Qwen/Qwen3.5-9B")


def is_local_model_dir(model_ref: str | Path) -> bool:
    return Path(model_ref).is_dir()


def resolve_tool_bin(
    exe_name: str,
    cfg_key: str,
    cfg: dict | None = None,
    env_var: str | None = None,
    override: str | None = None,
) -> str:
    """Resolve a CLI harness binary: explicit override -> env var -> config -> PATH -> OCA_TOOLS_DIR."""
    if override:
        return override
    if env_var:
        env_val = os.environ.get(env_var, "").strip()
        if env_val:
            return env_val
    cfg_bin = str((cfg or {}).get(cfg_key, {}).get("bin") or "").strip()
    if cfg_bin and (Path(cfg_bin).is_file() or shutil.which(cfg_bin)):
        return cfg_bin
    in_path = shutil.which(exe_name)
    if in_path:
        return in_path
    local_candidate = default_tools_dir() / cfg_key / "bin" / exe_name
    if local_candidate.is_file():
        return str(local_candidate)
    return cfg_bin or exe_name


def resolve_workdir_root(cfg: dict | None = None) -> str | None:
    """Resolve fast per-trial sandbox root; auto-uses `/dev/shm/oca_work` only when >= 16 GiB free."""
    env = os.environ.get("OCA_WORKDIR_ROOT", "").strip()
    if env:
        os.makedirs(env, exist_ok=True)
        return env
    cfg_wd = str((cfg or {}).get("rollout", {}).get("workdir_root") or "").strip()
    candidate = cfg_wd or ("/dev/shm/oca_work" if os.name != "nt" else "")
    if candidate and os.name != "nt" and candidate.startswith("/dev/shm") and os.path.isdir("/dev/shm"):
        try:
            st_fs = os.statvfs("/dev/shm")
            if (st_fs.f_bavail * st_fs.f_frsize) > (16 << 30):
                os.makedirs(candidate, exist_ok=True)
                os.chmod(candidate, 0o755)
                return candidate
        except OSError:
            return None
    elif candidate:
        try:
            os.makedirs(candidate, exist_ok=True)
            return candidate
        except OSError:
            return None
    return None


def default_cache_dir(subdir: str) -> Path:
    return Path(tempfile.gettempdir()) / subdir
