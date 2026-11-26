"""End-to-end single-session Colab CLI orchestrator (`phase0_1`, `screen`, `train_oc`, `train_pi`, `merge`, `eval_all`).

Runs from local Windows (via WSL `colab` CLI) or directly on Linux/WSL:
- Never touches any session other than `--session` (multi-session isolation).
- Reuses an already-running `--session` if present; otherwise creates it with retry on 503 capacity spikes.
- Automatically packs & uploads `artifacts/oca_repo.tar.gz`, dispatches `oca.colab.run_job`, downloads
  reports/history back to local `artifacts/`, and optionally stops ONLY `--session` on completion.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from .. import ROOT
from .pack_repo import pack_repo


def _to_wsl_path(p: Path) -> str:
    s = str(p.resolve())
    if os.name == "nt" and len(s) >= 2 and s[1] == ":":
        return f"/mnt/{s[0].lower()}{s[2:].replace(chr(92), '/')}"
    return s


def _colab(args: list[str], timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess:
    colab_bin = os.environ.get("COLAB_BIN", "colab")
    if os.name == "nt":
        # Invoke via WSL bash with proxy env loaded
        quoted = " ".join(subprocess.list2cmdline([a]) if " " in a else a for a in args)
        script = f'[ -f ~/.proxy_env.sh ] && source ~/.proxy_env.sh || true\nexec "{colab_bin}" {quoted}\n'
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8", newline="\n") as tf:
            tf.write(script)
            tmp_win = Path(tf.name)
        try:
            cmd = ["wsl", "-d", "Ubuntu", "--", "bash", _to_wsl_path(tmp_win)]
            proc = subprocess.run(cmd, text=True, timeout=timeout)
        finally:
            tmp_win.unlink(missing_ok=True)
    else:
        proc = subprocess.run([colab_bin, *args], text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"colab {' '.join(args)} failed with exit code {proc.returncode}")
    return proc


def _session_exists(session: str) -> bool:
    colab_bin = os.environ.get("COLAB_BIN", "colab")
    if os.name == "nt":
        cmd = ["wsl", "-d", "Ubuntu", "--", "bash", "-lc",
               f'[ -f ~/.proxy_env.sh ] && source ~/.proxy_env.sh || true; "{colab_bin}" sessions']
    else:
        cmd = [colab_bin, "sessions"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return session in (p.stdout or "")


def ensure_session(session: str, gpu: str, retries: int = 5, retry_wait: int = 30, skip_probe: bool = False):
    if _session_exists(session):
        print(f"[launch] Reusing active session '{session}'", flush=True)
        return
    for i in range(1, retries + 1):
        print(f"[launch] Creating session '{session}' (--gpu {gpu}), attempt {i}/{retries}...", flush=True)
        p = _colab(["new", "--gpu", gpu, "-s", session], timeout=120, check=False)
        if p.returncode == 0:
            break
        if i < retries:
            time.sleep(retry_wait)
    else:
        raise RuntimeError(f"Could not allocate --gpu {gpu} for session '{session}' after {retries} attempts")

    if not skip_probe:
        probe_path = _to_wsl_path(ROOT / "oca" / "colab" / "probe_env.py")
        print(f"[launch] Provisioning VM via probe_env.py...", flush=True)
        _colab(["exec", "-s", session, "--timeout", "900", "-f", probe_path], timeout=2400)


def build_job_spec(
    phase: str, steps: int, concurrency: int, loss_mode: str, eff_w: float | None,
    harness: str = "pi", adv_mode: str = "dr_grpo", credit_mode: str = "outcome",
    use_deltanet: bool = False, tag_override: str = "",
) -> tuple[dict, list[tuple[str, str]]]:
    """Return (job_spec_dict, [(remote_path, local_rel_path), ...])."""
    if phase == "phase0_1":
        spec = {
            "module": "oca.colab.phase0_1_diag",
            "args": ["--out-dir", "/content/runs/phase0_1_diag", "--concurrency", str(concurrency)],
            "log_file": "/content/runs/phase0_1_diag/job.log",
        }
        dl = [
            ("/content/probe/report.json", "artifacts/phase0_1/probe_report.json"),
            ("/content/runs/phase0_1_diag/phase0_1_report.json", "artifacts/phase0_1/phase0_1_report.json"),
            ("/content/runs/phase0_1_diag/p1_train_resume_smoke/history.jsonl", "artifacts/phase0_1/p1_history.jsonl"),
        ]
        return spec, dl

    if phase == "build_swe":
        spec = {
            "module": "oca.benchmarks.swe_verified",
            "args": ["--out-dir", "/content/repo/data/swe_verified_v1", "--max-total", "60",
                     "--freeze-protocol", "/content/runs/swe_verified_60.json"],
            "log_file": "/content/runs/build_swe.log",
        }
        dl = [("/content/runs/swe_verified_60.json", "protocol/swe_verified_60.json")]
        return spec, dl

    if phase == "build_smith":
        spec = {
            "module": "oca.benchmarks.swe_smith_train",
            "args": ["--out-dir", "/content/repo/data/swe_smith_v1", "--max-total", "160", "--max-per-repo", "20"],
            "log_file": "/content/runs/build_smith.log",
        }
        dl = [("/content/repo/data/swe_smith_v1/summary.json", "artifacts/v5/swe_smith_summary.json")]
        return spec, dl

    if phase == "screen":
        spec = {
            "module": "oca.train",
            "args": ["--config", "/content/repo/protocol/oca-v5.json",
                     "--mode", "screen", "--harness", harness, "--out-dir", f"/content/runs/screen_v5_{harness}",
                     "--k", "4", "--concurrency", str(concurrency)],
            "log_file": f"/content/runs/screen_v5_{harness}/job.log",
        }
        dl = [(f"/content/runs/screen_v5_{harness}/screen_summary.json", f"artifacts/v5/screen_{harness}_summary.json")]
        return spec, dl

    if phase in ("train_oc", "train_pi", "train_v5"):
        use_h = "opencode" if phase == "train_oc" else ("pi" if phase == "train_pi" else harness)
        tag = tag_override or f"v5_{use_h}_{loss_mode}_{adv_mode}_{credit_mode}"
        out = f"/content/runs/{tag}"
        args = [
            "--config", "/content/repo/protocol/oca-v5.json",
            "--mode", "train", "--harness", use_h, "--out-dir", out,
            "--steps", str(steps), "--loss-mode", loss_mode,
            "--adv-mode", adv_mode, "--credit-mode", credit_mode,
            "--concurrency", str(concurrency),
        ]
        if eff_w is not None:
            args += ["--efficiency-weight", str(eff_w)]
        if use_deltanet:
            args.append("--use-deltanet-lora")
        spec = {"module": "oca.train", "args": args, "log_file": f"{out}/job.log"}
        dl = [(f"{out}/history.jsonl", f"artifacts/v5/{tag}/history.jsonl")]
        return spec, dl

    if phase == "merge":
        oc_ckpt = f"/content/runs/v5_opencode_{loss_mode}_{adv_mode}_{credit_mode}/checkpoints/step_{steps:03d}"
        pi_ckpt = f"/content/runs/v5_pi_{loss_mode}_{adv_mode}_{credit_mode}/checkpoints/step_{steps:03d}"
        out = "/content/runs/v5_super_adapter_svd"
        spec = {
            "module": "oca.merge",
            "args": [
                "--method", "qr_svd",
                "--adapter", f"opencode={oc_ckpt}:0.5",
                "--adapter", f"pi={pi_ckpt}:0.5",
                "--out-dir", out,
            ],
            "log_file": f"{out}/merge.log",
        }
        dl = [(f"{out}/merge_meta.json", "artifacts/v5/super_adapter_svd/merge_meta.json")]
        return spec, dl

    if phase in ("eval_all", "eval_swe"):
        split = "swe_verified" if phase == "eval_swe" else "heldout"
        seeds = ["101", "102"] if phase == "eval_swe" else ["101", "102", "103", "104"]
        out = f"/content/runs/v5_eval_{split}_{harness}"
        spec = {
            "module": "oca.eval",
            "args": [
                "--config", "/content/repo/protocol/oca-v5.json",
                "--harness", harness, "--split", split, "--out-dir", out,
                "--seeds", *seeds, "--concurrency", str(concurrency),
            ],
            "log_file": f"{out}/eval.log",
        }
        dl = [(f"{out}/eval_report.json", f"artifacts/v5/eval_{split}_{harness}_report.json")]
        return spec, dl

    raise ValueError(f"Unknown phase: {phase}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session", "-s", default="oca-g4", help="Dedicated Colab session name")
    ap.add_argument("--gpu", default="G4", choices=("G4", "A100", "H100", "L4"))
    ap.add_argument("--phase", required=True,
                    choices=("phase0_1", "build_swe", "build_smith", "screen",
                             "train_oc", "train_pi", "train_v5", "merge", "eval_all", "eval_swe"))
    ap.add_argument("--harness", default="pi", choices=("opencode", "pi"))
    ap.add_argument("--steps", type=int, default=50)
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--loss-mode", default="tis_clip")
    ap.add_argument("--adv-mode", default="dr_grpo")
    ap.add_argument("--credit-mode", default="outcome")
    ap.add_argument("--use-deltanet-lora", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--efficiency-weight", type=float, default=None)
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--skip-probe", action="store_true")
    ap.add_argument("--stop-on-done", action="store_true", help="Release ONLY --session after downloading results")
    args = ap.parse_args()

    tar_path = ROOT / "artifacts" / "oca_repo.tar.gz"
    n_files, sz = pack_repo(tar_path)
    print(f"[launch] Packed {n_files} files -> {tar_path} ({sz/1024:.1f} KiB)", flush=True)

    ensure_session(args.session, args.gpu, retries=args.retries, skip_probe=args.skip_probe)

    print(f"[launch] Uploading repo tarball to {args.session}...", flush=True)
    _colab(["upload", "-s", args.session, _to_wsl_path(tar_path), "/content/oca_repo.tar.gz"], timeout=180)

    spec, downloads = build_job_spec(
        args.phase, args.steps, args.concurrency, args.loss_mode, args.efficiency_weight,
        harness=args.harness, adv_mode=args.adv_mode, credit_mode=args.credit_mode,
        use_deltanet=args.use_deltanet_lora, tag_override=args.tag,
    )
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as jf:
        json.dump(spec, jf, indent=2)
        spec_path = Path(jf.name)
    try:
        _colab(["upload", "-s", args.session, _to_wsl_path(spec_path), "/content/job_spec.json"], timeout=60)
    finally:
        spec_path.unlink(missing_ok=True)

    print(f"[launch] Running phase '{args.phase}' on {args.session}...", flush=True)
    run_job_path = _to_wsl_path(ROOT / "oca" / "colab" / "run_job.py")
    _colab(["exec", "-s", args.session, "--timeout", "1800", "-f", run_job_path], timeout=28800)

    for remote, local_rel in downloads:
        dst = ROOT / local_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        print(f"[launch] Downloading {remote} -> {dst}", flush=True)
        _colab(["download", "-s", args.session, remote, _to_wsl_path(dst)], timeout=120, check=False)

    if args.stop_on_done:
        print(f"[launch] Stopping ONLY session '{args.session}'...", flush=True)
        _colab(["stop", "-s", args.session], timeout=60, check=False)


if __name__ == "__main__":
    main()
