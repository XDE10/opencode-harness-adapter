"""Multi-seed paired evaluation, task-level cluster bootstrap CI, paired permutation test, and failure taxonomy."""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path
import random
import statistics

from . import CONFIG
from .proxy import CaptureProxy
from .rollout import run_batch
from .tasks import load
from .train import ensure_vllm_running, hot_load_lora, lock_grader_permissions


def classify_trial(rec: dict) -> str:
    """Classify a rollout into mutually exclusive outcome / failure-mode categories."""
    if rec.get("error"):
        return "infra_error"
    if rec.get("hack_flags"):
        return "reward_hack_blocked"
    grade = rec.get("grade") or {}
    if grade.get("status") == "pass":
        return "solved"
    for turn in rec.get("turns") or []:
        if turn.get("aux"):
            continue
        msg = turn.get("message") or {}
        content = msg.get("content") or ""
        if ("<tool_call>" in content or "</tool_call>" in content) and not msg.get("tool_calls"):
            return "tool_format_error"
    if rec.get("timed_out") or rec.get("budget_exhausted"):
        return "budget_or_timeout"
    tool_calls = rec.get("tool_calls") or []
    if not any(tc in ("edit", "write", "shell", "bash") for tc in tool_calls):
        return "no_edit_premature_stop"
    if grade.get("status") in ("test_error", "test_timeout"):
        return "runtime_or_syntax_error"
    passed = grade.get("passed") or 0
    if passed > 0:
        return "partial_edge_case_miss"
    return "wrong_logic"


def exact_mcnemar_p(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    k_max = min(wins, losses)
    probs = [math.comb(n, k) * (0.5 ** n) for k in range(k_max + 1)]
    return min(1.0, 2.0 * math.fsum(probs))


def paired_permutation_p(task_deltas: list[float], n_perm: int = 10000, seed: int = 0) -> float:
    """Two-sided task-level paired sign-flip permutation test (respects within-task multi-seed clustering)."""
    nz = [d for d in task_deltas if abs(d) > 1e-12]
    if not nz:
        return 1.0
    obs = abs(sum(nz))
    # Exact enumeration when <= 14 discordant tasks, Monte Carlo otherwise
    if len(nz) <= 14:
        total = 1 << len(nz)
        extreme = 0
        for mask in range(total):
            s = sum(d if (mask >> i) & 1 else -d for i, d in enumerate(nz))
            if abs(s) >= obs - 1e-12:
                extreme += 1
        return round(extreme / total, 6)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(n_perm):
        s = sum(d if rng.random() < 0.5 else -d for d in nz)
        if abs(s) >= obs - 1e-12:
            extreme += 1
    return round((extreme + 1) / (n_perm + 1), 6)


def bootstrap_ci(task_scores: list[float], n_boot: int = 5000, seed: int = 0) -> tuple[float, float]:
    if not task_scores:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(task_scores)
    means = sorted(
        sum(task_scores[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(n_boot)
    )
    return (round(means[int(0.025 * n_boot)], 4), round(means[int(0.975 * n_boot)], 4))


def pass_at_k_unbiased(n: int, c: int, k: int) -> float:
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def holm_bonferroni_adjust(p_values: dict[str, float]) -> dict[str, float]:
    """Step-down Holm-Bonferroni family-wise error rate (FWER) adjustment across arms."""
    if not p_values:
        return {}
    m = len(p_values)
    ordered = sorted(p_values.items(), key=lambda kv: kv[1])
    adjusted: dict[str, float] = {}
    running_max = 0.0
    for rank, (name, p) in enumerate(ordered):
        adj = min(1.0, max(running_max, float(p) * (m - rank)))
        running_max = adj
        adjusted[name] = round(adj, 6)
    return adjusted


def summarize_arm(records: list[dict], seeds: list[int]) -> dict:
    by_task: dict[str, list[dict]] = {}
    for r in records:
        by_task.setdefault(r["task_id"], []).append(r)

    task_means = []
    pass_at_all = []
    k_max = len(seeds)
    for tid, trecs in sorted(by_task.items()):
        c = sum(1 for r in trecs if (r.get("grade") or {}).get("status") == "pass" and not r.get("hack_flags"))
        n = len(trecs)
        task_means.append(c / n)
        if n >= k_max:
            pass_at_all.append(pass_at_k_unbiased(n, c, k_max))

    taxonomy: dict[str, int] = {}
    for r in records:
        cat = classify_trial(r)
        taxonomy[cat] = taxonomy.get(cat, 0) + 1

    ci_lo, ci_hi = bootstrap_ci(task_means)
    return {
        "n_tasks": len(by_task),
        "n_seeds": k_max,
        "n_trials": len(records),
        "pass_at_1": round(statistics.mean(task_means), 4) if task_means else 0.0,
        "pass_at_1_ci95": [ci_lo, ci_hi],
        f"pass_at_{k_max}": round(statistics.mean(pass_at_all), 4) if pass_at_all else None,
        "mean_completion_tokens": round(statistics.mean(r.get("completion_tokens", 0) for r in records), 1) if records else 0.0,
        "median_completion_tokens": round(statistics.median(r.get("completion_tokens", 0) for r in records), 1) if records else 0.0,
        "mean_turns": round(statistics.mean(r.get("n_policy_turns", 0) for r in records), 2) if records else 0.0,
        "mean_tool_calls": round(statistics.mean(len(r.get("tool_calls") or []) for r in records), 2) if records else 0.0,
        "mean_wall_s": round(statistics.mean(r.get("wall_s", 0.0) for r in records), 2) if records else 0.0,
        "failure_taxonomy": taxonomy,
    }


def compare_arms(base_recs: list[dict], lora_recs: list[dict], seeds: list[int]) -> dict:
    b_map = {(r["task_id"], r["seed"]): r for r in base_recs}
    l_map = {(r["task_id"], r["seed"]): r for r in lora_recs}
    keys = sorted(set(b_map) & set(l_map))

    wins = losses = both_pass = both_fail = 0
    both_solved_toks_b, both_solved_toks_l = [], []
    both_solved_tools_b, both_solved_tools_l = [], []
    both_solved_turns_b, both_solved_turns_l = [], []

    by_task_delta: dict[str, list[float]] = {}
    by_kind_keys: dict[str, list[tuple]] = {}
    for k in keys:
        br, lr = b_map[k], l_map[k]
        kind = br.get("kind") or lr.get("kind") or "single_file"
        by_kind_keys.setdefault(kind, []).append(k)
        bp = int((br.get("grade") or {}).get("status") == "pass" and not br.get("hack_flags"))
        lp = int((lr.get("grade") or {}).get("status") == "pass" and not lr.get("hack_flags"))
        by_task_delta.setdefault(k[0], []).append(lp - bp)
        if lp == 1 and bp == 0:
            wins += 1
        elif lp == 0 and bp == 1:
            losses += 1
        elif lp == 1 and bp == 1:
            both_pass += 1
            both_solved_toks_b.append(br.get("completion_tokens", 0))
            both_solved_toks_l.append(lr.get("completion_tokens", 0))
            both_solved_tools_b.append(len(br.get("tool_calls") or []))
            both_solved_tools_l.append(len(lr.get("tool_calls") or []))
            both_solved_turns_b.append(br.get("n_policy_turns", 0))
            both_solved_turns_l.append(lr.get("n_policy_turns", 0))
        else:
            both_fail += 1

    task_deltas = [statistics.mean(v) for v in by_task_delta.values()]
    delta_mean = statistics.mean(task_deltas) if task_deltas else 0.0
    delta_ci = bootstrap_ci(task_deltas, seed=7)
    perm_p = paired_permutation_p(task_deltas)

    common_eff = None
    if both_pass > 0:
        mb, ml = statistics.mean(both_solved_toks_b), statistics.mean(both_solved_toks_l)
        tb, tl = statistics.mean(both_solved_tools_b), statistics.mean(both_solved_tools_l)
        common_eff = {
            "n_common_solved_pairs": both_pass,
            "base_mean_tokens": round(mb, 1),
            "lora_mean_tokens": round(ml, 1),
            "token_reduction_pct": round(100.0 * (mb - ml) / mb, 2) if mb > 0 else 0.0,
            "base_mean_tool_calls": round(tb, 2),
            "lora_mean_tool_calls": round(tl, 2),
            "tool_call_reduction_pct": round(100.0 * (tb - tl) / tb, 2) if tb > 0 else 0.0,
            "base_mean_turns": round(statistics.mean(both_solved_turns_b), 2),
            "lora_mean_turns": round(statistics.mean(both_solved_turns_l), 2),
        }

    by_kind = {}
    if len(by_kind_keys) > 1:
        for kd, kd_keys in sorted(by_kind_keys.items()):
            b_sub = summarize_arm([b_map[k] for k in kd_keys], seeds)
            l_sub = summarize_arm([l_map[k] for k in kd_keys], seeds)
            by_kind[kd] = {
                "n_tasks": b_sub["n_tasks"],
                "base_pass_at_1": b_sub["pass_at_1"],
                "lora_pass_at_1": l_sub["pass_at_1"],
                "delta_pp": round(100.0 * (l_sub["pass_at_1"] - b_sub["pass_at_1"]), 2),
            }

    return {
        "paired_trials": len(keys),
        "paired_tasks": len(by_task_delta),
        "base": summarize_arm([b_map[k] for k in keys], seeds),
        "lora": summarize_arm([l_map[k] for k in keys], seeds),
        "delta_pass_at_1_pp": round(100.0 * delta_mean, 2),
        "delta_pass_at_1_ci95_pp": [round(100.0 * delta_ci[0], 2), round(100.0 * delta_ci[1], 2)],
        "task_level_permutation_p": perm_p,
        "outcomes": {"lora_only_wins": wins, "base_only_losses": losses,
                     "both_pass": both_pass, "both_fail": both_fail},
        "trial_level_mcnemar_p_exploratory": round(exact_mcnemar_p(wins, losses), 6),
        "common_solved_efficiency": common_eff,
        "by_kind": by_kind,
    }


async def eval_arm(vllm_url: str, proxy_port: int, arm_name: str, served_model: str,
                   tasks: list, seeds: list[int], out_dir: Path, concurrency: int,
                   cfg: dict, harness_name: str = "opencode") -> list[dict]:
    arm_dir = out_dir / arm_name
    arm_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    cached = {}
    for t in tasks:
        for s in seeds:
            tid = f"ev-{arm_name}-{t.id}-s{s}"
            f = arm_dir / f"{tid}.json"
            if f.is_file():
                rec_c = json.loads(f.read_text(encoding="utf-8"))
                if not rec_c.get("error"):
                    cached[tid] = rec_c
                    continue
            jobs.append((t, served_model, s, tid))

    print(f"[eval:{harness_name}:{arm_name}] {len(tasks)} tasks x {len(seeds)} seeds = {len(tasks)*len(seeds)} "
          f"({len(cached)} cached, {len(jobs)} to run)", flush=True)
    if jobs:
        proxy = await CaptureProxy(
            vllm_url, cfg["rollout"], safe_intercept=bool(cfg["rollout"].get("safe_intercept", False))
        ).start(port=proxy_port)
        done = 0

        def on_done(rec):
            nonlocal done
            done += 1
            if done % 10 == 0 or done == len(jobs):
                st = (rec.get("grade") or {}).get("status", "err")
                print(f"  [eval:{arm_name} {done}/{len(jobs)}] last={rec['task_id']} -> {st}", flush=True)

        fresh = await run_batch(
            proxy, jobs, arm_dir, concurrency=concurrency, cfg=cfg,
            on_done=on_done, harness_name=harness_name,
        )
        await proxy.close()
        for r in fresh:
            cached[r["trial_id"]] = r

    return [cached[f"ev-{arm_name}-{t.id}-s{s}"] for t in tasks for s in seeds]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=None, help="Optional protocol JSON (e.g. protocol/oca-v5.json)")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--harness", choices=("opencode", "pi", "mini_swe"), default="opencode")
    ap.add_argument("--split", default="heldout")
    ap.add_argument("--kind", choices=("", "single_file", "repo_pytest", "swe_verified"), default="")
    ap.add_argument("--source-filter", default="", help="Optional: 'v3', 'generated', 'repo', 'ood', or 'swe_verified'")
    ap.add_argument("--seeds", type=int, nargs="+", default=[101, 102, 103, 104])
    ap.add_argument("--thinking", action="store_true", help="Enable Qwen3 thinking mode (for Base Thinking-ON upper bound)")
    ap.add_argument("--max-output-per-call", type=int, default=0)
    ap.add_argument("--skip-base", action="store_true")
    ap.add_argument("--base-dir", type=Path, default=None)
    ap.add_argument("--lora", action="append", default=[], help="name=checkpoint_path (repeatable)")
    ap.add_argument("--vllm-url", default="http://127.0.0.1:8000")
    ap.add_argument("--proxy-port", type=int, default=8105)
    ap.add_argument("--concurrency", type=int, default=32)
    args = ap.parse_args()

    cfg = json.loads(args.config.read_text(encoding="utf-8")) if args.config else json.loads(json.dumps(CONFIG))
    if args.thinking:
        cfg["rollout"]["enable_thinking"] = True
        cfg["rollout"]["max_output_tokens_per_call"] = max(4096, args.max_output_per_call)
        cfg["rollout"]["max_output_tokens_per_trial"] = 16384
    elif args.max_output_per_call > 0:
        cfg["rollout"]["max_output_tokens_per_call"] = args.max_output_per_call

    lock_grader_permissions()
    ensure_vllm_running(args.vllm_url, cfg, args.out_dir / "vllm.log")

    tasks = sorted(load(split=args.split, kind=args.kind or None), key=lambda t: t.id)
    if args.source_filter == "v3":
        tasks = [t for t in tasks if t.source == "v3"]
    elif args.source_filter == "generated":
        tasks = [t for t in tasks if t.source.startswith("tasks-")]
    elif args.source_filter == "repo":
        tasks = [t for t in tasks if t.source.startswith("repo_")]
    elif args.source_filter == "ood":
        tasks = [t for t in tasks if t.source.startswith("ood_")]
    elif args.source_filter == "swe_verified":
        tasks = [t for t in tasks if t.source.startswith("swe_verified")]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    base_root = args.base_dir or args.out_dir
    base_arm = "base_thinking" if args.thinking else "base"
    if not args.skip_base:
        base_recs = asyncio.run(eval_arm(
            args.vllm_url, args.proxy_port, base_arm, cfg["model"]["served_name"],
            tasks, args.seeds, base_root, args.concurrency, cfg, harness_name=args.harness,
        ))
    else:
        base_recs = [
            json.loads((base_root / base_arm / f"ev-{base_arm}-{t.id}-s{s}.json").read_text(encoding="utf-8"))
            for t in tasks for s in args.seeds
        ]

    expected_trials = len(tasks) * len(args.seeds)
    base_missing = expected_trials - sum(1 for r in base_recs if not r.get("error"))
    if base_missing > 0:
        print(f"[eval WARNING] base arm has {base_missing}/{expected_trials} errored/missing trials!", flush=True)

    report = {
        "harness": args.harness, "split": args.split, "thinking": args.thinking,
        "n_tasks": len(tasks), "seeds": args.seeds, "expected_trials": expected_trials,
        "base_missing_or_errored": base_missing,
        "base_summary": summarize_arm(base_recs, args.seeds), "comparisons": {},
    }

    prev_alias = None
    for spec in args.lora:
        name, cpath = spec.split("=", 1)
        alias = f"eval-{name}"
        hot_load_lora(args.vllm_url, alias, Path(cpath), prev_alias)
        prev_alias = alias
        lora_recs = asyncio.run(eval_arm(
            args.vllm_url, args.proxy_port, name, alias, tasks, args.seeds,
            args.out_dir, args.concurrency, cfg, harness_name=args.harness,
        ))
        arm_missing = expected_trials - sum(1 for r in lora_recs if not r.get("error"))
        if arm_missing > 0:
            print(f"[eval WARNING] arm '{name}' has {arm_missing}/{expected_trials} errored/missing trials!", flush=True)
        comp = compare_arms(base_recs, lora_recs, args.seeds)
        comp["missing_or_errored_trials"] = arm_missing
        report["comparisons"][name] = comp
        print(f"\n=== COMPARISON ({args.harness}) vs {name} ===", flush=True)
        print(json.dumps({k: v for k, v in comp.items() if k not in ("base", "lora")}, indent=2), flush=True)

    # Apply Holm-Bonferroni FWER adjustment across all evaluated arms
    raw_ps = {k: v["task_level_permutation_p"] for k, v in report["comparisons"].items()}
    adj_ps = holm_bonferroni_adjust(raw_ps)
    for k, adj_p in adj_ps.items():
        report["comparisons"][k]["holm_bonferroni_p_adj"] = adj_p

    out_file = args.out_dir / "eval_report.json"
    out_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved full evaluation report to {out_file}", flush=True)


if __name__ == "__main__":
    main()
