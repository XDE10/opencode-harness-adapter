"""Pure-Python SVG chart generator (zero matplotlib dependency) + LoRA merge/GGUF helper (A4 + A5)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _svg_wrap(width: int, height: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" style="font-family:Inter,Segoe UI,Arial,sans-serif;background:#ffffff">\n'
        f'{body}\n</svg>\n'
    )


def render_training_curve(history_jsonl: Path, out_svg: Path, compare_jsonl: Path | None = None,
                          labels: tuple[str, str] = ("TIS GRPO (Ours)", "Naive Clip / Baseline")):
    rows = [json.loads(ln) for ln in history_jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
    comp_rows = ([json.loads(ln) for ln in compare_jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
                 if compare_jsonl and compare_jsonl.is_file() else [])
    if not rows:
        return
    W, H, pad_l, pad_r, pad_t, pad_b = 760, 380, 65, 30, 45, 55
    pw, ph = W - pad_l - pad_r, H - pad_t - pad_b
    max_step = max(r["step"] for r in [*rows, *comp_rows])

    def xy(step, val):
        x = pad_l + (step - 1) / max(1, max_step - 1) * pw
        y = pad_t + (1.0 - max(0.0, min(1.0, val))) * ph
        return round(x, 1), round(y, 1)

    els = [f'<text x="{W//2}" y="26" text-anchor="middle" font-size="15" font-weight="600" fill="#111827">'
           f'On-Policy Harness RL Training Pass Rate (Rollout Batch)</text>']
    for pct in (0.0, 0.25, 0.5, 0.75, 1.0):
        _, y = xy(1, pct)
        els.append(f'<line x1="{pad_l}" y1="{y}" x2="{W-pad_r}" y2="{y}" stroke="#e5e7eb" stroke-width="1"/>')
        els.append(f'<text x="{pad_l-8}" y="{y+4}" text-anchor="end" font-size="11" fill="#6b7280">{int(pct*100)}%</text>')

    for s in range(1, max_step + 1, max(1, max_step // 8)):
        x, _ = xy(s, 0)
        els.append(f'<text x="{x}" y="{H-pad_b+18}" text-anchor="middle" font-size="11" fill="#6b7280">Step {s}</text>')

    def draw_series(data, color, label, lx):
        pts = [xy(r["step"], r["pass_rate"]) for r in data]
        poly = " ".join(f"{x},{y}" for x, y in pts)
        els.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{poly}"/>')
        for x, y in pts:
            els.append(f'<circle cx="{x}" cy="{y}" r="3" fill="{color}"/>')
        els.append(f'<rect x="{lx}" y="{H-20}" width="14" height="4" fill="{color}"/>')
        els.append(f'<text x="{lx+20}" y="{H-14}" font-size="12" fill="#374151">{label}</text>')

    draw_series(rows, "#2563eb", labels[0], pad_l)
    if comp_rows:
        draw_series(comp_rows, "#dc2626", labels[1], pad_l + 240)
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(_svg_wrap(W, H, "\n".join(els)), encoding="utf-8")


def render_logprob_hist(history_jsonl: Path, out_svg: Path):
    rows = [json.loads(ln) for ln in history_jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not rows:
        return
    agg: dict[str, int] = {}
    for r in rows:
        for k, v in (r.get("logprob_err_hist") or {}).items():
            agg[k] = agg.get(k, 0) + int(v)
    if not agg:
        return
    W, H, pad_l, pad_r, pad_t, pad_b = 760, 360, 75, 30, 45, 65
    pw, ph = W - pad_l - pad_r, H - pad_t - pad_b
    keys = list(agg.keys())
    vals = [agg[k] for k in keys]
    tot = max(1, sum(vals))
    fracs = [v / tot for v in vals]
    max_f = max(0.05, max(fracs) * 1.15)

    els = [f'<text x="{W//2}" y="26" text-anchor="middle" font-size="15" font-weight="600" fill="#111827">'
           f'vLLM vs Trainer BF16 Per-Token Logprob Divergence |Δ log π| (nats)</text>']
    bw = pw / len(keys) * 0.68
    gap = pw / len(keys)
    for i, (k, f, cnt) in enumerate(zip(keys, fracs, vals)):
        x = pad_l + i * gap + (gap - bw) / 2
        bh = (f / max_f) * ph
        y = pad_t + ph - bh
        is_danger = k in ("0.5-1.0", "1.0-5.0", ">=5.0")
        color = "#dc2626" if is_danger else "#3b82f6"
        els.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{color}" rx="3"/>')
        els.append(f'<text x="{x+bw/2:.1f}" y="{y-6:.1f}" text-anchor="middle" font-size="10" fill="#374151">'
                   f'{f*100:.2f}% ({cnt})</text>')
        els.append(f'<text x="{x+bw/2:.1f}" y="{H-pad_b+18}" text-anchor="middle" font-size="11" fill="#374151">{k}</text>')
    els.append(f'<text x="{W//2}" y="{H-12}" text-anchor="middle" font-size="11" fill="#dc2626">'
               f'Red bars (&gt;0.5 nats) trigger fatal NO-GO abort in legacy gate; handled smoothly by TIS</text>')
    out_svg.write_text(_svg_wrap(W, H, "\n".join(els)), encoding="utf-8")


def render_failure_taxonomy(eval_report_json: Path, out_svg: Path, lora_key: str | None = None):
    rep = json.loads(eval_report_json.read_text(encoding="utf-8"))
    comps = rep.get("comparisons") or {}
    if not comps:
        return
    lora_key = lora_key or next(iter(comps))
    b_tax = comps[lora_key]["base"]["failure_taxonomy"]
    l_tax = comps[lora_key]["lora"]["failure_taxonomy"]
    cats = [
        ("solved", "#16a34a", "Solved (100% cases)"),
        ("partial_edge_case_miss", "#60a5fa", "Partial Fix (Edge Case Miss)"),
        ("wrong_logic", "#f59e0b", "Wrong Logic"),
        ("runtime_or_syntax_error", "#f97316", "Runtime / Exception Error"),
        ("budget_or_timeout", "#ef4444", "Budget / Timeout Exhausted"),
        ("no_edit_premature_stop", "#8b5cf6", "Premature Stop (No Edit)"),
        ("tool_format_error", "#ec4899", "Malformed Tool Call"),
        ("reward_hack_blocked", "#111827", "Reward Hack Blocked"),
    ]
    W, H = 760, 280
    els = [f'<text x="{W//2}" y="28" text-anchor="middle" font-size="15" font-weight="600" fill="#111827">'
           f'Held-out Outcome &amp; Failure-Mode Shift: Base Qwen3.5-9B vs {lora_key}</text>']
    bar_x, bar_w = 150, 560
    for row_idx, (arm_label, tax) in enumerate((("Base Qwen3.5-9B", b_tax), (f"Adapted ({lora_key})", l_tax))):
        y = 65 + row_idx * 65
        tot = max(1, sum(tax.values()))
        els.append(f'<text x="{bar_x-12}" y="{y+24}" text-anchor="end" font-size="13" font-weight="600" fill="#1f2937">'
                   f'{arm_label}</text>')
        cx = float(bar_x)
        for key, color, _ in cats:
            cnt = tax.get(key, 0)
            if cnt <= 0:
                continue
            w = (cnt / tot) * bar_w
            els.append(f'<rect x="{cx:.1f}" y="{y}" width="{w:.1f}" height="36" fill="{color}"/>')
            if w >= 36:
                els.append(f'<text x="{cx+w/2:.1f}" y="{y+23}" text-anchor="middle" font-size="11" '
                           f'font-weight="600" fill="#ffffff">{cnt / tot * 100:.0f}%</text>')
            cx += w

    lx, ly = 60, 205
    for i, (key, color, label) in enumerate(cats):
        if b_tax.get(key, 0) == 0 and l_tax.get(key, 0) == 0:
            continue
        col_x = lx + (i % 3) * 235
        row_y = ly + (i // 3) * 24
        els.append(f'<rect x="{col_x}" y="{row_y-10}" width="12" height="12" fill="{color}" rx="2"/>')
        els.append(f'<text x="{col_x+18}" y="{row_y}" font-size="11" fill="#374151">{label}</text>')
    out_svg.write_text(_svg_wrap(W, H, "\n".join(els)), encoding="utf-8")


def render_transfer_matrix(matrix_json: Path, out_svg: Path):
    """Render 2x2 + Super-Adapter cross-harness transfer heatmap SVG.

    Expected JSON:
      {"harnesses": ["OpenCode", "Pi"],
       "models": [{"name": "Base", "scores": [0.22, 0.19]}, ...]}
    """
    doc = json.loads(matrix_json.read_text(encoding="utf-8"))
    harnesses = doc["harnesses"]
    models = doc["models"]
    W = 220 + len(harnesses) * 145 + 145
    H = 95 + len(models) * 48 + 30
    els = [
        f'<text x="{W//2}" y="28" text-anchor="middle" font-size="15" font-weight="600" fill="#111827">'
        f'Cross-Harness Transfer &amp; Super-Adapter Matrix (Held-out pass@1)</text>'
    ]
    cols = [*harnesses, "Mean"]
    for j, col in enumerate(cols):
        cx = 220 + j * 145 + 65
        els.append(f'<text x="{cx}" y="68" text-anchor="middle" font-size="13" font-weight="600" fill="#374151">{col}</text>')

    def cell_color(v: float) -> tuple[str, str]:
        # High-contrast scale tailored to multi-tier coding pass@1 (35%-55%+)
        cl = max(0.0, min(1.0, v))
        if cl >= 0.47:
            return "#16a34a", "#ffffff"
        if cl >= 0.42:
            return "#2563eb", "#ffffff"
        if cl >= 0.39:
            return "#60a5fa", "#ffffff"
        return "#e5e7eb", "#111827"

    for i, m in enumerate(models):
        y = 82 + i * 48
        els.append(f'<text x="206" y="{y+26}" text-anchor="end" font-size="13" font-weight="600" fill="#1f2937">{m["name"]}</text>')
        vals = [*m["scores"], sum(m["scores"]) / max(1, len(m["scores"]))]
        for j, v in enumerate(vals):
            x = 220 + j * 145
            bg, fg = cell_color(v)
            els.append(f'<rect x="{x}" y="{y}" width="130" height="38" rx="6" fill="{bg}"/>')
            els.append(f'<text x="{x+65}" y="{y+24}" text-anchor="middle" font-size="13" font-weight="600" fill="{fg}">{v*100:.1f}%</text>')

    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(_svg_wrap(W, H, "\n".join(els)), encoding="utf-8")


def merge_and_export(base_model_path: Path, lora_ckpt: Path, merged_out: Path):
    """Merge PEFT LoRA into base BF16 weights for standalone serving or llama.cpp GGUF conversion (A5)."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(base_model_path), local_files_only=True)
    base = AutoModelForCausalLM.from_pretrained(str(base_model_path), local_files_only=True,
                                                torch_dtype=torch.bfloat16, device_map="cpu")
    peft_m = PeftModel.from_pretrained(base, str(lora_ckpt))
    merged = peft_m.merge_and_unload()
    merged_out.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(merged_out, safe_serialization=True)
    tok.save_pretrained(merged_out)
    print(f"Merged model written to {merged_out}")


def main():
    from oca.paths import default_models_dir
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history", type=Path)
    ap.add_argument("--compare-history", type=Path)
    ap.add_argument("--eval-report", type=Path)
    ap.add_argument("--transfer-matrix", type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path("docs/figures"))
    ap.add_argument("--merge-lora", type=Path, default=None)
    ap.add_argument("--base-model", type=Path, default=default_models_dir() / "qwen35-9b")
    ap.add_argument("--merged-out", type=Path, default=default_models_dir() / "qwen35-9b-merged")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.history and args.history.is_file():
        render_training_curve(args.history, args.out_dir / "training_curve.svg", args.compare_history)
        render_logprob_hist(args.history, args.out_dir / "logprob_divergence.svg")
    if args.eval_report and args.eval_report.is_file():
        render_failure_taxonomy(args.eval_report, args.out_dir / "failure_taxonomy.svg")
    if args.transfer_matrix and args.transfer_matrix.is_file():
        render_transfer_matrix(args.transfer_matrix, args.out_dir / "transfer_matrix.svg")
    if args.merge_lora:
        merge_and_export(args.base_model, args.merge_lora, args.merged_out)


if __name__ == "__main__":
    main()
