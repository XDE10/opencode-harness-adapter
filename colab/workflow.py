"""CPU preparation and gated commands for the synchronous Colab experiment."""

import argparse
import json
from pathlib import Path
import shlex
import tempfile

from .contracts import (DATA, MODEL, PILOT, PLAN, ROOT, ROLLOUT, digest, first_update_groups,
                        require, validate_plan, verify_snapshot, verify_three)
from .evaluation import compare, compare_v3, comparison_plan_v3, verify_reload
from .harbor_pack import prepare
from .update import one_step


def serve_arguments(snapshot, checkpoint=None):
    require(Path(snapshot).is_absolute(), "use an absolute path to the local verified snapshot")
    model_id = MODEL["id"]
    args = ["vllm", "serve", str(snapshot), "--host", "127.0.0.1", "--port", "8000",
            "--served-model-name", model_id, "--dtype", "bfloat16", "--generation-config", "vllm",
            "--enable-auto-tool-choice", "--tool-call-parser", PLAN["runtime"]["vllm_tool_parser"],
            "--default-chat-template-kwargs", '{"enable_thinking":false}',
            "--return-tokens-as-token-ids", "--logprobs-mode", "processed_logprobs", "--enforce-eager",
            "--max-model-len", str(ROLLOUT["max_context_tokens"]), "--max-num-seqs", "1",
            "--gpu-memory-utilization", "0.70", "--seed", str(ROLLOUT["seed"])]
    if checkpoint is not None:
        require(checkpoint.is_absolute(), "use an absolute path to the local checkpoint")
        adapter_sha = digest(checkpoint / "adapter_model.safetensors")
        args.extend(["--enable-lora", "--max-lora-rank", str(PLAN["update"]["rank"]), "--lora-modules",
                     f"oca-lora-{adapter_sha[:16]}={checkpoint}"])
    return args


def serve_config(snapshot, checkpoint=None):
    return "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 " + shlex.join(serve_arguments(snapshot, checkpoint))


def smoke_plan(snapshot, evidence):
    require(snapshot.is_absolute() and evidence.is_absolute(), "use absolute snapshot and evidence paths")
    cap = 600 + len(PILOT) * (60 + ROLLOUT["timeout_seconds"]) + 300
    return {
        "status": "plan_only",
        "real_capture_launcher_ready": False,
        "blocked_on": "first G4 verification of actual vLLM token IDs, logprobs and OpenEnv masks",
        "model_id": MODEL["id"], "model_revision": MODEL["revision"],
        "tasks_in_order": PILOT, "attempts_per_task": 1, "concurrency": 1,
        "budgets": {
            "max_context_tokens": ROLLOUT["max_context_tokens"],
            "max_output_tokens_per_call": ROLLOUT["max_output_tokens_per_call"],
            "max_output_tokens_per_trial": ROLLOUT["max_output_tokens_per_trial"],
            "max_calls_per_trial": ROLLOUT["max_model_calls"],
            "trial_seconds": ROLLOUT["timeout_seconds"],
            "all_trials_max_output_tokens": len(PILOT) * ROLLOUT["max_output_tokens_per_trial"],
            "all_trials_max_calls": len(PILOT) * ROLLOUT["max_model_calls"],
            "device_peak_stop_bytes": PLAN["runtime"]["peak_stop_bytes"],
        },
        "gpu_time_seconds": {
            "estimate_kind": "planning envelope with dependencies, images and snapshot already local",
            "server_startup_cap": 600, "container_and_verifier_per_trial_cap": 60,
            "shutdown_and_audit_allowance": 300, "phase_total": cap, "absolute_stop": 1800,
        },
        "commands": {
            "cpu_preparation": "./scripts/run-colab.sh prepare",
            "verify_snapshot": shlex.join(["./scripts/run-colab.sh", "verify-snapshot", str(snapshot)]),
            "review_serving_arguments": shlex.join(["./scripts/run-colab.sh", "serve-config", str(snapshot)]),
            "serving_command_after_all_gates": serve_config(snapshot),
            "first_g4": shlex.join(["./scripts/run-g4-first-trial.sh", str(snapshot),
                                   str(evidence.with_name("first-g4")), "--allow-existing-g4"]),
            "real_capture": None,
            "validate_real_evidence": shlex.join(
                ["./scripts/run-colab.sh", "verify-three", str(evidence), "--verify-upstream"]),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare", help="export and smoke-check local Harbor bundles on CPU")
    config = commands.add_parser("serve-config", help="print serving command; start nothing")
    config.add_argument("snapshot", type=Path)
    config.add_argument("--checkpoint", type=Path)
    plan = commands.add_parser("smoke-plan", help="print the real-smoke commands and limits; start nothing")
    plan.add_argument("snapshot", type=Path)
    plan.add_argument("evidence", type=Path)
    commands.add_parser("verify-snapshot").add_argument("snapshot", type=Path)
    commands.add_parser("validate-schemas").add_argument("bundle", type=Path)
    verify_three_cmd = commands.add_parser("verify-three")
    verify_three_cmd.add_argument("evidence", type=Path)
    verify_three_cmd.add_argument("--verify-upstream", action="store_true", help="require actual OpenEnv TrainingTrace validation")
    commands.add_parser("verify-group").add_argument("evidence", type=Path)
    commands.add_parser("compare-plan-v3", help="print the frozen paired holdout identities, seed and budget")
    update = commands.add_parser("update-once")
    for name in ("three", "group", "snapshot", "output"):
        update.add_argument(name, type=Path)
    update.add_argument("--allow-existing-g4", action="store_true")
    for name in ("verify-reload", "compare"):
        command = commands.add_parser(name)
        command.add_argument("checkpoint", type=Path)
        command.add_argument("receipt", type=Path)
        if name == "compare":
            command.add_argument("before", type=Path)
            command.add_argument("after", type=Path)
            command.add_argument("--manifest-version", type=int, choices=(2, 3), default=2)
            command.add_argument("--fixture", action="store_true", help="process only labelled synthetic v3 evidence")
    args = parser.parse_args()
    if args.command == "compare" and args.fixture and args.manifest_version != 3:
        parser.error("--fixture requires --manifest-version 3")

    try:
        validate_plan()
        if args.command == "prepare":
            from .verifier_check import verify_pack
            artifacts = ROOT / "artifacts"
            artifacts.mkdir(exist_ok=True)
            output = Path(tempfile.mkdtemp(prefix="colab-prep-", dir=artifacts))
            prepare(output / "harbor")
            grades = verify_pack(output / "harbor")
            report = {"status": "cpu_preparation", "model": MODEL["id"], "revision": MODEL["revision"],
                      "harbor_verifier_controls": grades, "data_status": DATA["status"],
                      "capture_executed": False, "update_executed": False, "output": str(output)}
            (output / "acceptance.json").write_text(json.dumps(report, indent=2) + "\n")
        elif args.command == "serve-config":
            print(serve_config(args.snapshot, args.checkpoint))
            return 0
        elif args.command == "smoke-plan":
            report = smoke_plan(args.snapshot, args.evidence)
        elif args.command == "verify-snapshot":
            verify_snapshot(args.snapshot)
            report = {"model": MODEL["id"], "revision": MODEL["revision"], "verified_files": len(MODEL["files"])}
        elif args.command == "validate-schemas":
            from .upstream import validate_schemas
            report = validate_schemas(args.bundle)
        elif args.command == "verify-three":
            report = verify_three(args.evidence, verify_upstream=args.verify_upstream)
        elif args.command == "verify-group":
            report = {"admitted_rollouts": len(first_update_groups(args.evidence)), "optimizer_steps": 0}
        elif args.command == "compare-plan-v3":
            report = comparison_plan_v3()
        elif args.command == "update-once":
            if not args.allow_existing_g4:
                parser.error("update requires explicit --allow-existing-g4")
            report = one_step(args.three, args.group, args.snapshot, args.output)
        elif args.command == "compare":
            sha = verify_reload(args.checkpoint, args.receipt, fixture=args.fixture)
            report = (compare_v3(args.before, args.after, sha, fixture=args.fixture) if args.manifest_version == 3
                      else compare(args.before, args.after, sha))
        else:
            report = {"adapter_sha256": verify_reload(args.checkpoint, args.receipt)}
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, ImportError) as exc:
        parser.exit(2, f"Colab workflow stopped: {exc}\n")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
