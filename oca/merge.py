"""Merge multiple harness-specific LoRA adapters (e.g. OpenCode + Pi) into a single Super-Adapter
and run exact weight-space + activation-space mechanistic alignment diagnostics.

Supported merge methods:
- `qr_svd`: Exact ΔW-space linear merge + truncated rank-r SVD via rank-2r QR factorization (~1s CPU).
- `concat_2r`: Lossless rank-(r1+r2) LoRA concatenation (100% energy retained, matches HF Super-Adapter).
- `linear`, `ties`, `dare_ties`: PEFT `add_weighted_adapter` merges.

Mechanistic diagnostics:
- Exact Frobenius ΔW cosine: tr((B1^T B2)(A2 A1^T)) == ((B1.T @ B2) * (A1 @ A2.T)).sum()
- Activation-space cosine: cos(ΔW1 x, ΔW2 x) over real rollout hidden states x (separates
  high-dimensional random LoRA initialization orthogonality from true functional alignment).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import time


DEFAULT_BASE_MODEL_ID = "Qwen/Qwen3.5-9B"


def _sanitize_adapter_config(cfg: dict, base_model_id: str | None = None) -> dict:
    out = dict(cfg)
    raw = str(out.get("base_model_name_or_path") or "")
    if base_model_id:
        out["base_model_name_or_path"] = base_model_id
    elif raw.startswith("/") or ":\\" in raw or raw.startswith("C:") or raw.startswith("D:"):
        out["base_model_name_or_path"] = DEFAULT_BASE_MODEL_ID
    return out


def exact_frobenius_cosine(A1, B1, s1: float, A2, B2, s2: float) -> tuple[float, float, float]:
    """Compute exact (||ΔW1||_F, ||ΔW2||_F, cos(ΔW1, ΔW2)) without materializing d_out x d_in.

    Proof:
      ΔW1 = s1 * B1 @ A1, ΔW2 = s2 * B2 @ A2
      <ΔW1, ΔW2>_F = tr(ΔW1^T ΔW2) = s1*s2 * tr((B1^T B2)(A2 A1^T))
                   = s1*s2 * sum_{i,j} (B1^T B2)_{i,j} * (A2 A1^T)_{j,i}
                   = s1*s2 * sum((B1^T B2) * (A1 A2^T))
    """
    c11 = float(((B1.T @ B1) * (A1 @ A1.T)).sum().item()) * (s1 ** 2)
    c22 = float(((B2.T @ B2) * (A2 @ A2.T)).sum().item()) * (s2 ** 2)
    c12 = float(((B1.T @ B2) * (A1 @ A2.T)).sum().item()) * (s1 * s2)
    n1, n2 = max(0.0, c11) ** 0.5, max(0.0, c22) ** 0.5
    cos = c12 / (n1 * n2) if (n1 > 1e-8 and n2 > 1e-8) else 0.0
    return n1, n2, cos


def merge_super_adapter(
    base_model: Path,
    adapters: list[tuple[str, Path, float]],
    out_dir: Path,
    method: str = "ties",
    density: float = 0.5,
    base_model_id: str | None = None,
) -> Path:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    if len(adapters) < 2:
        raise ValueError("Need at least two adapters to merge into a Super-Adapter")

    base = AutoModelForCausalLM.from_pretrained(
        str(base_model), local_files_only=True, dtype=torch.bfloat16, device_map="cpu"
    )
    first_name, first_path, _ = adapters[0]
    model = PeftModel.from_pretrained(base, str(first_path), adapter_name=first_name)
    for name, path, _ in adapters[1:]:
        model.load_adapter(str(path), adapter_name=name)

    names = [a[0] for a in adapters]
    weights = [a[2] for a in adapters]
    kwargs = {"combination_type": method}
    if method in ("ties", "dare_ties", "dare_linear"):
        kwargs["density"] = density

    merged_name = "super_adapter"
    model.add_weighted_adapter(names, weights, merged_name, **kwargs)
    model.set_adapter(merged_name)

    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir, selected_adapters=[merged_name], safe_serialization=True)

    # PEFT saves named adapter under out_dir/super_adapter/ -> flatten to out_dir for vLLM load_lora_adapter
    nested = out_dir / merged_name
    if nested.is_dir():
        for f in nested.iterdir():
            target = out_dir / f.name
            if target.exists():
                target.unlink()
            f.rename(target)
        nested.rmdir()

    cfg_path = out_dir / "adapter_config.json"
    if cfg_path.is_file():
        cfg_clean = _sanitize_adapter_config(json.loads(cfg_path.read_text(encoding="utf-8")), base_model_id)
        cfg_path.write_text(json.dumps(cfg_clean, indent=2) + "\n", encoding="utf-8")

    meta = {
        "method": method, "density": density,
        "sources": [{"name": n, "path": str(p), "weight": w} for n, p, w in adapters],
    }
    (out_dir / "merge_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"[merge] Saved Super-Adapter ({method}, density={density}) -> {out_dir}")
    return out_dir


def merge_super_adapter_concat_2r(
    adapters: list[tuple[str, Path, float]],
    out_dir: Path,
    base_model_id: str | None = None,
) -> Path:
    """Lossless ΔW-space linear merge by concatenating ranks (r_out = sum(r_i), 100% energy retained).

    Matches Hugging Face's lossless Super-Adapter construction (`B_cat = [w1*s1/s_out*B1, w2*s2/s_out*B2]`,
    `A_cat = [A1; A2]`), so `s_out * B_cat @ A_cat == w1 * ΔW1 + w2 * ΔW2` identically with zero SVD truncation.
    Requires vLLM `--max-lora-rank >= r_out` (e.g. 64 for two r=32 adapters).
    """
    import torch
    from safetensors.torch import load_file, save_file

    if len(adapters) < 2:
        raise ValueError("concat_2r merge expects at least two LoRA adapters")
    t0 = time.time()
    cfgs = [json.loads((p / "adapter_config.json").read_text(encoding="utf-8")) for _, p, _ in adapters]
    sds = [load_file(p / "adapter_model.safetensors") for _, p, _ in adapters]
    ranks = [int(c["r"]) for c in cfgs]
    scales = [float(c["lora_alpha"]) / int(c["r"]) for c in cfgs]
    r_out = sum(ranks)
    alpha_out = float(r_out * 2)
    s_out = alpha_out / r_out

    prefixes = sorted({k.rsplit(".lora_", 1)[0] for k in sds[0] if ".lora_A." in k})
    for sd in sds[1:]:
        p_other = sorted({k.rsplit(".lora_", 1)[0] for k in sd if ".lora_A." in k})
        if p_other != prefixes:
            raise ValueError("Adapters have mismatched target module sets")

    out_sd = {}
    cos_dw, n1s, n2s = [], [], []
    for pref in prefixes:
        dt = sds[0][f"{pref}.lora_A.weight"].dtype
        b_parts, a_parts = [], []
        for idx, (_, _, w) in enumerate(adapters):
            Ai = sds[idx][f"{pref}.lora_A.weight"].float()
            Bi = sds[idx][f"{pref}.lora_B.weight"].float()
            b_parts.append((w * scales[idx] / s_out) * Bi)
            a_parts.append(Ai)
        if len(adapters) == 2:
            n1, n2, c = exact_frobenius_cosine(a_parts[0], sds[0][f"{pref}.lora_B.weight"].float(), scales[0],
                                               a_parts[1], sds[1][f"{pref}.lora_B.weight"].float(), scales[1])
            n1s.append(n1); n2s.append(n2); cos_dw.append(c)
        out_sd[f"{pref}.lora_B.weight"] = torch.cat(b_parts, dim=1).to(dtype=dt).contiguous()
        out_sd[f"{pref}.lora_A.weight"] = torch.cat(a_parts, dim=0).to(dtype=dt).contiguous()

    out_dir.mkdir(parents=True, exist_ok=True)
    save_file(out_sd, out_dir / "adapter_model.safetensors")
    out_cfg = _sanitize_adapter_config(cfgs[0], base_model_id)
    out_cfg["r"] = r_out
    out_cfg["lora_alpha"] = int(alpha_out)
    (out_dir / "adapter_config.json").write_text(json.dumps(out_cfg, indent=2) + "\n", encoding="utf-8")

    meta = {
        "method": "lossless_concat_2r",
        "r_out": r_out,
        "weights": [w for _, _, w in adapters],
        "n_modules": len(prefixes),
        "mean_svd_energy_retained": 1.0,
        "elapsed_s": round(time.time() - t0, 2),
        "sources": [{"name": n, "path": str(p), "weight": w} for n, p, w in adapters],
    }
    if cos_dw:
        meta.update({
            "mean_norm_a1": round(sum(n1s) / len(n1s), 4),
            "mean_norm_a2": round(sum(n2s) / len(n2s), 4),
            "mean_dw_cosine": round(sum(cos_dw) / len(cos_dw), 6),
            "min_dw_cosine": round(min(cos_dw), 6),
            "max_dw_cosine": round(max(cos_dw), 6),
        })
    (out_dir / "merge_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"[merge] Saved Lossless Concat-{r_out} Super-Adapter ({meta['elapsed_s']}s) -> {out_dir}")
    return out_dir


def merge_super_adapter_qr_svd(
    adapters: list[tuple[str, Path, float]],
    out_dir: Path,
    base_model_id: str | None = None,
) -> Path:
    """Exact ΔW-space linear merge + truncated rank-r SVD via rank-2r QR factorization (~1s on CPU, no base model)."""
    import torch
    from safetensors.torch import load_file, save_file

    if len(adapters) != 2:
        raise ValueError("qr_svd merge expects exactly two LoRA adapters")
    t0 = time.time()
    (_, p1, w1), (_, p2, w2) = adapters
    cfg1 = json.loads((p1 / "adapter_config.json").read_text(encoding="utf-8"))
    cfg2 = json.loads((p2 / "adapter_config.json").read_text(encoding="utf-8"))
    r1, a1 = int(cfg1["r"]), float(cfg1["lora_alpha"])
    r2, a2 = int(cfg2["r"]), float(cfg2["lora_alpha"])
    r_out = max(r1, r2)
    alpha_out = float(r_out * 2)
    s1, s2, s_out = a1 / r1, a2 / r2, alpha_out / r_out

    sd1 = load_file(p1 / "adapter_model.safetensors")
    sd2 = load_file(p2 / "adapter_model.safetensors")
    prefixes = sorted({k.rsplit(".lora_", 1)[0] for k in sd1 if ".lora_A." in k})

    out_sd = {}
    cos_dw, energy_ret, n1s, n2s = [], [], [], []
    for pref in prefixes:
        A1_orig = sd1[f"{pref}.lora_A.weight"]
        dt = A1_orig.dtype
        A1, B1 = A1_orig.float(), sd1[f"{pref}.lora_B.weight"].float()
        A2, B2 = sd2[f"{pref}.lora_A.weight"].float(), sd2[f"{pref}.lora_B.weight"].float()

        n1, n2, c = exact_frobenius_cosine(A1, B1, s1, A2, B2, s2)
        n1s.append(n1); n2s.append(n2); cos_dw.append(c)

        B_cat = torch.cat([(w1 * s1 / s_out) * B1, (w2 * s2 / s_out) * B2], dim=1)
        A_cat = torch.cat([A1, A2], dim=0)
        Q_b, R_b = torch.linalg.qr(B_cat, mode="reduced")
        Q_a, R_a = torch.linalg.qr(A_cat.T, mode="reduced")
        U_c, S, Vh_c = torch.linalg.svd(R_b @ R_a.T, full_matrices=False)
        energy_ret.append(float((S[:r_out] ** 2).sum().item()) / max(float((S ** 2).sum().item()), 1e-12))
        s_sqrt = torch.sqrt(S[:r_out].clamp(min=0.0))
        out_sd[f"{pref}.lora_B.weight"] = ((Q_b @ U_c[:, :r_out]) * s_sqrt.unsqueeze(0)).to(dtype=dt).contiguous()
        out_sd[f"{pref}.lora_A.weight"] = (s_sqrt.unsqueeze(1) * (Vh_c[:r_out, :] @ Q_a.T)).to(dtype=dt).contiguous()

    out_dir.mkdir(parents=True, exist_ok=True)
    save_file(out_sd, out_dir / "adapter_model.safetensors")
    out_cfg = _sanitize_adapter_config(cfg1, base_model_id)
    out_cfg["r"] = r_out
    out_cfg["lora_alpha"] = int(alpha_out)
    (out_dir / "adapter_config.json").write_text(json.dumps(out_cfg, indent=2) + "\n", encoding="utf-8")
    meta = {
        "method": "exact_qr_svd_linear",
        "r_out": r_out,
        "weights": [w1, w2],
        "n_modules": len(prefixes),
        "mean_norm_a1": round(sum(n1s) / len(n1s), 4),
        "mean_norm_a2": round(sum(n2s) / len(n2s), 4),
        "mean_dw_cosine": round(sum(cos_dw) / len(cos_dw), 6),
        "min_dw_cosine": round(min(cos_dw), 6),
        "max_dw_cosine": round(max(cos_dw), 6),
        "mean_svd_energy_retained": round(sum(energy_ret) / len(energy_ret), 4),
        "elapsed_s": round(time.time() - t0, 2),
        "sources": [{"name": n, "path": str(p), "weight": w} for n, p, w in adapters],
    }
    (out_dir / "merge_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"[merge] Saved QR-SVD Super-Adapter ({meta['elapsed_s']}s, cos={meta['mean_dw_cosine']}) -> {out_dir}")
    return out_dir


def analyze_activation_alignment(
    base_model: Path,
    adapter1: Path,
    adapter2: Path,
    probe_token_seqs: list[list[int]],
    out_json: Path | None = None,
    max_tokens_per_seq: int = 256,
) -> dict:
    """Measure weight-space cosine vs functional activation-space cosine cos(ΔW1 x, ΔW2 x) on real states x.

    Separates ambient high-dimensional random LoRA initialization orthogonality (where <ΔW1, ΔW2>_F ≈ 0
    even for two runs on the SAME harness) from true functional alignment on real token representations x.
    """
    import torch
    from safetensors.torch import load_file
    from transformers import AutoModelForCausalLM

    cfg1 = json.loads((adapter1 / "adapter_config.json").read_text(encoding="utf-8"))
    cfg2 = json.loads((adapter2 / "adapter_config.json").read_text(encoding="utf-8"))
    s1 = float(cfg1["lora_alpha"]) / int(cfg1["r"])
    s2 = float(cfg2["lora_alpha"]) / int(cfg2["r"])
    sd1 = load_file(adapter1 / "adapter_model.safetensors")
    sd2 = load_file(adapter2 / "adapter_model.safetensors")
    prefixes = sorted({k.rsplit(".lora_", 1)[0] for k in sd1 if ".lora_A." in k})

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModelForCausalLM.from_pretrained(
        str(base_model), local_files_only=True, dtype=torch.bfloat16, device_map={"": device}
    )
    model.eval()

    # Map PEFT prefix (`base_model.model.<path>`) to live base module
    mod_by_name = dict(model.named_modules())
    hook_map: dict[str, tuple] = {}
    act_stats: dict[str, dict[str, float]] = {}
    for pref in prefixes:
        mod_name = pref[len("base_model.model."):] if pref.startswith("base_model.model.") else pref
        if mod_name not in mod_by_name:
            continue
        A1 = sd1[f"{pref}.lora_A.weight"].to(device=device, dtype=torch.float32)
        B1 = sd1[f"{pref}.lora_B.weight"].to(device=device, dtype=torch.float32)
        A2 = sd2[f"{pref}.lora_A.weight"].to(device=device, dtype=torch.float32)
        B2 = sd2[f"{pref}.lora_B.weight"].to(device=device, dtype=torch.float32)
        _, _, w_cos = exact_frobenius_cosine(A1, B1, s1, A2, B2, s2)
        hook_map[mod_name] = (A1, B1, A2, B2, w_cos)
        act_stats[mod_name] = {"dot": 0.0, "n1_sq": 0.0, "n2_sq": 0.0, "w_cos": w_cos}

    handles = []

    def _make_hook(mname: str):
        A1, B1, A2, B2, _ = hook_map[mname]

        def _hook(_mod, inp, _out):
            x = inp[0].detach().float().reshape(-1, inp[0].shape[-1])
            y1 = (x @ A1.T) @ B1.T * s1
            y2 = (x @ A2.T) @ B2.T * s2
            st = act_stats[mname]
            st["dot"] += float((y1 * y2).sum().item())
            st["n1_sq"] += float((y1 * y1).sum().item())
            st["n2_sq"] += float((y2 * y2).sum().item())

        return _hook

    for mname in hook_map:
        handles.append(mod_by_name[mname].register_forward_hook(_make_hook(mname)))

    with torch.no_grad():
        for seq in probe_token_seqs:
            if not seq:
                continue
            ids = torch.tensor([seq[:max_tokens_per_seq]], dtype=torch.long, device=device)
            model(input_ids=ids, use_cache=False)

    for h in handles:
        h.remove()

    per_mod = []
    for mname, st in sorted(act_stats.items()):
        denom = (max(0.0, st["n1_sq"]) * max(0.0, st["n2_sq"])) ** 0.5
        a_cos = st["dot"] / denom if denom > 1e-12 else 0.0
        per_mod.append({"module": mname, "weight_cos": round(st["w_cos"], 6), "activation_cos": round(a_cos, 6)})

    w_vals = [r["weight_cos"] for r in per_mod]
    a_vals = [r["activation_cos"] for r in per_mod]
    report = {
        "n_modules": len(per_mod),
        "n_probe_seqs": len(probe_token_seqs),
        "weight_cosine_mean": round(statistics.mean(w_vals), 6) if w_vals else 0.0,
        "weight_cosine_range": [min(w_vals), max(w_vals)] if w_vals else [0.0, 0.0],
        "activation_cosine_mean": round(statistics.mean(a_vals), 6) if a_vals else 0.0,
        "activation_cosine_range": [min(a_vals), max(a_vals)] if a_vals else [0.0, 0.0],
        "top_aligned_modules": sorted(per_mod, key=lambda r: r["activation_cos"], reverse=True)[:10],
        "bottom_aligned_modules": sorted(per_mod, key=lambda r: r["activation_cos"])[:5],
    }
    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    from oca.paths import default_models_dir
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-model", type=Path, default=default_models_dir() / "qwen35-9b")
    ap.add_argument("--base-model-id", default=DEFAULT_BASE_MODEL_ID)
    ap.add_argument("--adapter", action="append", required=True, help="name=path[:weight], e.g. opencode=/path:0.5")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--method", choices=("qr_svd", "concat_2r", "linear", "ties", "dare_ties"), default="qr_svd")
    ap.add_argument("--density", type=float, default=0.5)
    ap.add_argument("--analyze-activations-from", type=Path, default=None,
                    help="Optional eval trial JSON dir to compute activation-space cosine between two adapters")
    args = ap.parse_args()

    parsed = []
    for spec in args.adapter:
        name, rest = spec.split("=", 1)
        if ":" in rest and not Path(rest).exists():
            p_str, w_str = rest.rsplit(":", 1)
            weight = float(w_str)
        else:
            p_str, weight = rest, 0.5
        parsed.append((name, Path(p_str), weight))

    if args.analyze_activations_from is not None:
        if len(parsed) != 2:
            raise ValueError("--analyze-activations-from requires exactly two --adapter specs")
        seqs = []
        for fp in sorted(args.analyze_activations_from.glob("*.json"))[:24]:
            rec = json.loads(fp.read_text(encoding="utf-8"))
            for t in rec.get("turns") or []:
                if not t.get("aux") and t.get("prompt_token_ids") and t.get("completion_token_ids"):
                    seqs.append((t["prompt_token_ids"] + t["completion_token_ids"])[-256:])
                    break
        rep = analyze_activation_alignment(
            args.base_model, parsed[0][1], parsed[1][1], seqs,
            out_json=args.out_dir / "activation_alignment.json",
        )
        print(json.dumps({k: v for k, v in rep.items() if not k.endswith("_modules")}, indent=2))
        return

    if args.method == "qr_svd":
        merge_super_adapter_qr_svd(parsed, args.out_dir, base_model_id=args.base_model_id)
    elif args.method == "concat_2r":
        merge_super_adapter_concat_2r(parsed, args.out_dir, base_model_id=args.base_model_id)
    else:
        merge_super_adapter(args.base_model, parsed, args.out_dir, method=args.method,
                            density=args.density, base_model_id=args.base_model_id)


if __name__ == "__main__":
    main()
