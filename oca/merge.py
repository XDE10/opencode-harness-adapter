"""Merge multiple harness-specific LoRA adapters (e.g. OpenCode + Pi) into a single Super-Adapter.

Supports `linear`, `ties`, and `dare_ties` combination via PEFT `add_weighted_adapter`, emitting a
standard PEFT LoRA checkpoint directory loadable directly by vLLM `/v1/load_lora_adapter`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def merge_super_adapter(
    base_model: Path,
    adapters: list[tuple[str, Path, float]],
    out_dir: Path,
    method: str = "ties",
    density: float = 0.5,
) -> Path:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    if len(adapters) < 2:
        raise ValueError("Need at least two adapters to merge into a Super-Adapter")

    base = AutoModelForCausalLM.from_pretrained(
        str(base_model), local_files_only=True, torch_dtype=torch.bfloat16, device_map="cpu"
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

    meta = {
        "method": method, "density": density,
        "sources": [{"name": n, "path": str(p), "weight": w} for n, p, w in adapters],
    }
    (out_dir / "merge_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"[merge] Saved Super-Adapter ({method}, density={density}) -> {out_dir}")
    return out_dir


def merge_super_adapter_qr_svd(
    adapters: list[tuple[str, Path, float]],
    out_dir: Path,
) -> Path:
    """Exact ΔW-space linear merge + truncated rank-r SVD via rank-2r QR factorization (~1s on CPU, no base model)."""
    import time
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

        c11 = float(((B1.T @ B1) * (A1 @ A1.T)).sum().item()) * (s1 ** 2)
        c22 = float(((B2.T @ B2) * (A2 @ A2.T)).sum().item()) * (s2 ** 2)
        c12 = float(((B1.T @ B2) * (A2 @ A1.T)).sum().item()) * (s1 * s2)
        n1, n2 = max(0.0, c11) ** 0.5, max(0.0, c22) ** 0.5
        n1s.append(n1); n2s.append(n2)
        cos_dw.append(c12 / (n1 * n2) if (n1 > 1e-8 and n2 > 1e-8) else 0.0)

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
    out_cfg = dict(cfg1)
    out_cfg["r"] = r_out
    out_cfg["lora_alpha"] = int(alpha_out)
    (out_dir / "adapter_config.json").write_text(json.dumps(out_cfg, indent=2) + "\n", encoding="utf-8")
    meta = {
        "method": "exact_qr_svd_linear",
        "weights": [w1, w2],
        "n_modules": len(prefixes),
        "mean_norm_a1": round(sum(n1s) / len(n1s), 4),
        "mean_norm_a2": round(sum(n2s) / len(n2s), 4),
        "mean_dw_cosine": round(sum(cos_dw) / len(cos_dw), 4),
        "mean_svd_energy_retained": round(sum(energy_ret) / len(energy_ret), 4),
        "elapsed_s": round(time.time() - t0, 2),
        "sources": [{"name": n, "path": str(p), "weight": w} for n, p, w in adapters],
    }
    (out_dir / "merge_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"[merge] Saved QR-SVD Super-Adapter ({meta['elapsed_s']}s, cos={meta['mean_dw_cosine']}) -> {out_dir}")
    return out_dir


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-model", type=Path, default=Path("/content/models/qwen35-9b"))
    ap.add_argument("--adapter", action="append", required=True, help="name=path[:weight], e.g. opencode=/path:0.5")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--method", choices=("qr_svd", "linear", "ties", "dare_ties"), default="qr_svd")
    ap.add_argument("--density", type=float, default=0.5)
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
    if args.method == "qr_svd":
        merge_super_adapter_qr_svd(parsed, args.out_dir)
    else:
        merge_super_adapter(args.base_model, parsed, args.out_dir, method=args.method, density=args.density)


if __name__ == "__main__":
    main()
