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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-model", type=Path, default=Path("/content/models/Qwen3-8B"))
    ap.add_argument("--adapter", action="append", required=True, help="name=path[:weight], e.g. opencode=/path:0.5")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--method", choices=("linear", "ties", "dare_ties"), default="ties")
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
    merge_super_adapter(args.base_model, parsed, args.out_dir, method=args.method, density=args.density)


if __name__ == "__main__":
    main()
