# AGENTS.md — AI Coding Agent Guide for `opencode-harness-adapter`

This file helps external AI coding agents (Claude Code, Codex, Kiro CLI, OpenCode, Cursor, Antigravity, etc.) quickly understand, install, verify, deploy, train, evaluate, and safely modify this repository.

## 1. Project Purpose

`opencode-harness-adapter` is a **single-GPU colocated Agentic RL** framework (`Qwen/Qwen3.5-9B`, 248-module LoRA `r=32`, non-thinking mode) for adapting open-weight models to operate **unmodified terminal coding harnesses** (`opencode` 2.2.7, `pi` 0.73.1, and zero-shot OOD `mini-swe-agent` v2) without requiring multi-GPU clusters or Docker during RL rollouts.

- **Pretrained V5 LoRA weights**: `XDE10/Qwen3.5-9B-Harness-Adapters-v5` on HuggingFace (recommended balanced default: `adapters/soup_v5_pi_qr_svd`).
- **Frozen V5 protocol**: `protocol/oca-v5.json`, `protocol/screen_v5_multifile.json` (54-task train pool), `protocol/swe_verified_60.json` (60-task pure-Python SWE-bench_Verified manifest).

## 2. One-Click Commands (Zero Hardcoding)

All scripts work out of the box and respect environment variables defined in `oca/paths.py`.

| Goal | Command | Requirements |
| --- | --- | --- |
| **Install (CPU / Dev)** | `pip install -e .` | Python >= 3.11 (Linux / macOS / Windows) |
| **Verify (CI Gate)** | `bash scripts/verify.sh` | CPU only (~5s, runs 28 unit tests + 10 anti-hack exploits) |
| **Provision GPU Node** | `bash scripts/setup_gpu.sh` | Linux + 80–96 GB GPU + Node.js >= 20 (installs `.[gpu]`, CLIs, model, recommended HF adapter) |
| **Paired Evaluation** | `bash scripts/run_eval.sh` | Linux GPU (auto-downloads `soup_v5_pi_qr_svd` if missing; supports `HARNESS=pi\|opencode\|mini_swe`, `SPLIT=heldout\|swe_verified`) |
| **50-Step RL Training** | `bash scripts/run_train.sh` | Linux GPU (supports `HARNESS=pi\|opencode`, `STEPS=50`, `LORA_SEED=2026`, `LOSS_MODE=tis_clip\|gspo\|cispo`) |
| **CPU LoRA Merge** | `python -u -m oca.merge --method qr_svd --adapter a=<path>:0.5 --adapter b=<path>:0.5 --out-dir <out>` | CPU only (~1s) |

## 3. Environment Variables (`oca/paths.py`)

Never hardcode `/content/...` or user-specific paths in code or configs. Use `oca.paths`:

- `OCA_HOME` (default `~/.cache/oca`): root cache for models, CLI tools, SWE venvs/mirrors, and HF adapters.
- `OCA_MODEL_PATH`: local base model directory override (falls back to `$OCA_HOME/models/qwen35-9b`, then HuggingFace ID `Qwen/Qwen3.5-9B` with auto-download).
- `OCA_TOOLS_DIR` (default `$OCA_HOME/tools`): install prefix for `opencode` and `pi` CLIs.
- `OCA_SWE_VENVS` / `OCA_SWE_MIRRORS`: shared venv and bare git mirror caches for SWE-bench / SWE-smith.
- `OCA_WORKDIR_ROOT`: fast scratch root for isolated trial workspaces (auto-uses `/dev/shm/oca_work` on Linux if >= 16 GiB free, else system temp).
- `OCA_RUNS_DIR` (default `./runs`): default output directory for runs.
- `OPENCODE_BIN` / `PI_BIN` / `MINI_SWE_BIN`: explicit binary path overrides (otherwise resolved from `PATH` or `$OCA_TOOLS_DIR`).

## 4. Architecture & Key Source Files

- `oca/paths.py`: Portable path, model, and CLI binary resolution.
- `oca/proxy.py`: `CaptureProxy` sitting between CLI harness and vLLM; captures engine-native `prompt_token_ids`, `completion_token_ids`, `processed_logprobs`, replays SSE to the CLI, enforces per-trial output/call budgets, and performs in-the-loop `SafeProxy` command interception.
- `oca/rollout.py`: Isolated trial execution (`bwrap` mount/PID/IPC sandbox + unprivileged `agent` UID + CRLF->LF copy guard + `_collect_unified_diff` excluding `TASK.md` and `*.egg-info`/`build`/`dist`).
- `oca/grade.py`: Hidden verifier (`nobody` subprocess, `0700` hidden test dirs, `clean_tests` restore, `rlimits`).
- `oca/reward.py`: Correctness + light joint turn/token efficiency bonus (`eff_w=0.05`) + zero-tolerance hard zeroing on `SEVERE_FLAGS` (including `safe_proxy_intercepted`).
- `oca/train.py`: Single-GPU colocated RL/RFT trainer (vLLM `/sleep?level=1` -> PyTorch backward -> `/wake_up` -> `/v1/load_lora_adapter`), `pack_trajectory_segments` prefix-merged multi-turn packing, `2048`-token exact chunked LM-head backward with minibatch-global token denominator, `Dr.GRPO`, Dual-Ratio `TIS-Clip`, `GSPO`, `CISPO`, and `collect_groups_early_cutoff`.
- `oca/eval.py`: Multi-seed paired evaluation, cluster bootstrap CI, task-level permutation test, Holm-Bonferroni correction, failure taxonomy, and standard `predictions_*.jsonl` export for official SWE-bench Docker grading.
- `oca/merge.py`: Exact CPU `qr_svd`, lossless `concat_2r`, and `ties` LoRA merging plus 248-module weight & activation covariance analysis.
- `oca/harnesses/`: Pluggable adapters (`opencode.py`, `pi.py`, `mini_swe.py`).
- `oca/benchmarks/`: Zero-Docker `swe_verified.py` (60-task pure-Python subset) and `swe_smith_train.py` (zero repo/task overlap with SWE-bench_Verified).

## 5. Non-Negotiable Code Invariants

When modifying code, preserve these verified invariants:

1. **Zero Data Leakage**: Training tasks (`protocol/screen_v5_multifile.json` and `swe_smith_train.py`) must maintain 0 task-ID, 0 domain, and 0 repo overlap with `heldout` and `SWE-bench_Verified` (enforced by unit tests).
2. **Engine-Native Logprob Alignment**: Never re-tokenize multi-turn text to approximate behavior `old_logp`; always consume `CaptureProxy`'s exact `prompt_token_ids` / `completion_token_ids` / `per_token_logps`.
3. **Unbiased Dr.GRPO + Correctness Gating**: Keep `filter_same_correctness=True` and do not divide advantages by group std in `dr_grpo` mode (prevents all-pass groups from amplifying tiny efficiency differences into huge gradients).
4. **Chunked LM-Head Exactness**: Keep the minibatch-global denominator (`denom = float(mb_tokens)`) across LM-head chunks so chunked backward matches unchunked gradients to machine precision.
5. **Anti-Hack Integrity**: Any `SEVERE_FLAGS` hit (`reads_grader`, `modified_task_md`, `modified_visible_tests`, `safe_proxy_intercepted`, etc.) must hard-zero episode reward and emit an empty `model_patch` in `predictions_*.jsonl`.
6. **Clean Diff Export**: `_collect_unified_diff` must exclude `TASK.md`, `.git`, `__pycache__`, `build`, `dist`, `*.egg-info`, and `*.dist-info` so `git apply` succeeds cleanly inside official SWE-bench Docker containers.

## 6. Verification Checklist Before Committing

1. Run `bash scripts/verify.sh` — all unit tests (`tests/test_oca_v4.py`, `tests/test_oca_v5.py`) and all 10 adversarial exploits (`oca.adversarial`) must pass.
2. Check `git status` — ensure no secrets, local logs, `runs/`, `artifacts/`, or temporary files are staged.
3. Keep all scripts portable (no hardcoded absolute machine paths; use `oca.paths` or env vars).
