"""RL Infra step-level latency, straggler tail-bubble, throughput & VRAM profiler (+ zero-dep SVG chart)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics

from .plots import _svg_wrap


def profile_history(history_jsonl: Path) -> dict:
    rows = [json.loads(ln) for ln in history_jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not rows:
        return {"error": "empty history", "n_steps": 0}

    roll_s = [float((r.get("timing_s") or {}).get("rollout", 0.0)) for r in rows]
    slp_s = [float((r.get("timing_s") or {}).get("sleep", 0.0)) for r in rows]
    trn_s = [float((r.get("timing_s") or {}).get("train", 0.0)) for r in rows]
    swp_s = [float((r.get("timing_s") or {}).get("wake_and_hotswap", 0.0)) for r in rows]
    tot_s = [float((r.get("timing_s") or {}).get("total", 0.0)) for r in rows]
    toks = [int(r.get("trained_tokens", 0)) for r in rows]
    comps = [float(r.get("prefix_compression_ratio", 1.0)) for r in rows]
    canc = [int(r.get("stragglers_cancelled", 0)) for r in rows]
    p50s = [float((r.get("rollout_latency_s") or {}).get("p50", 0.0)) for r in rows if r.get("rollout_latency_s")]
    p95s = [float((r.get("rollout_latency_s") or {}).get("p95", 0.0)) for r in rows if r.get("rollout_latency_s")]
    vrams = [int((r.get("vram_mib") or {}).get("train_peak_reserved", 0)) for r in rows if (r.get("vram_mib") or {}).get("train_peak_reserved")]

    tot_sum = max(1e-6, sum(tot_s))
    return {
        "history": str(history_jsonl),
        "n_steps": len(rows),
        "total_wall_hours": round(tot_sum / 3600.0, 2),
        "mean_step_s": round(statistics.mean(tot_s), 2),
        "breakdown_mean_s": {
            "rollout": round(statistics.mean(roll_s), 2),
            "sleep": round(statistics.mean(slp_s), 2),
            "train": round(statistics.mean(trn_s), 2),
            "wake_hotswap": round(statistics.mean(swp_s), 2),
        },
        "breakdown_pct": {
            "rollout_pct": round(100.0 * sum(roll_s) / tot_sum, 1),
            "train_pct": round(100.0 * sum(trn_s) / tot_sum, 1),
            "colocation_overhead_pct": round(100.0 * (sum(slp_s) + sum(swp_s)) / tot_sum, 2),
        },
        "train_tokens_per_sec": round(sum(toks) / max(1.0, sum(trn_s)), 1),
        "mean_prefix_compression_x": round(statistics.mean(comps), 2),
        "total_stragglers_cancelled": sum(canc),
        "rollout_p50_mean_s": round(statistics.mean(p50s), 2) if p50s else None,
        "rollout_p95_mean_s": round(statistics.mean(p95s), 2) if p95s else None,
        "peak_train_vram_gib": round(max(vrams) / 1024.0, 2) if vrams else None,
    }


def render_infra_profile_svg(profiles: list[tuple[str, dict]], out_svg: Path):
    """Render stacked horizontal step-time breakdown bar chart comparing runs (e.g. v4 sync vs v5 early-cutoff)."""
    if not profiles:
        return
    W = 780
    H = 95 + len(profiles) * 56 + 45
    bar_x, bar_w = 210, 500
    max_s = max(max(1.0, p["mean_step_s"]) for _, p in profiles)

    els = [
        f'<text x="{W//2}" y="28" text-anchor="middle" font-size="15" font-weight="600" fill="#111827">'
        f'RL Infra Step Timeline Breakdown (Mean Seconds / Step)</text>'
    ]
    colors = [
        ("rollout", "#3b82f6", "Rollout (vLLM + Harness)"),
        ("train", "#16a34a", "Train (Chunked LM-Head + Backward)"),
        ("wake_hotswap", "#f59e0b", "Sleep / Wake + LoRA Hot-Swap"),
    ]
    for idx, (label, prof) in enumerate(profiles):
        y = 60 + idx * 56
        bm = prof["breakdown_mean_s"]
        parts = [
            ("rollout", bm["rollout"]),
            ("train", bm["train"]),
            ("wake_hotswap", bm["sleep"] + bm["wake_hotswap"]),
        ]
        els.append(f'<text x="{bar_x-12}" y="{y+22}" text-anchor="end" font-size="12" font-weight="600" fill="#1f2937">{label}</text>')
        cx = float(bar_x)
        for key, val in parts:
            col = dict((k, c) for k, c, _ in colors)[key]
            w = (val / max_s) * bar_w
            if w > 0.5:
                els.append(f'<rect x="{cx:.1f}" y="{y}" width="{w:.1f}" height="32" fill="{col}" rx="2"/>')
            if w >= 42:
                els.append(f'<text x="{cx+w/2:.1f}" y="{y+20}" text-anchor="middle" font-size="10" font-weight="600" fill="#ffffff">{val:.0f}s</text>')
            cx += w
        els.append(f'<text x="{cx+8:.1f}" y="{y+20}" font-size="11" font-weight="600" fill="#374151">{prof["mean_step_s"]:.0f}s</text>')

    ly = H - 22
    for i, (_, col, desc) in enumerate(colors):
        lx = 60 + i * 245
        els.append(f'<rect x="{lx}" y="{ly-10}" width="12" height="12" fill="{col}" rx="2"/>')
        els.append(f'<text x="{lx+18}" y="{ly}" font-size="11" fill="#374151">{desc}</text>')

    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(_svg_wrap(W, H, "\n".join(els)), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="append", required=True, help="label=path/to/history.jsonl (repeatable)")
    ap.add_argument("--out-svg", type=Path, default=None)
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args()

    profs = []
    for spec in args.run:
        label, p_str = spec.split("=", 1)
        profs.append((label, profile_history(Path(p_str))))
    print(json.dumps({k: v for k, v in profs}, indent=2))
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps({k: v for k, v in profs}, indent=2) + "\n", encoding="utf-8")
    if args.out_svg:
        render_infra_profile_svg(profs, args.out_svg)


if __name__ == "__main__":
    main()
