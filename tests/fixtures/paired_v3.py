"""Generate labelled CPU fixtures for the v3 comparison command."""

import argparse
import json
from pathlib import Path

from colab.contracts import FIXTURE_SOURCE, digest
from colab.evaluation import comparison_plan_v3


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def make_fixtures(output):
    plan = comparison_plan_v3()
    output.mkdir()
    checkpoint = output / "checkpoint"
    checkpoint.mkdir()
    weights = checkpoint / "adapter_model.safetensors"
    weights.write_bytes(b"Synthetic comparator fixture. This file contains no tensor data.\n")
    sha = digest(weights)
    alias = "oca-lora-" + sha[:16]
    receipt = output / "reload.json"
    write_json(checkpoint / "update.json", {
        "source": FIXTURE_SOURCE, "adapter_sha256": sha, "expected_served_alias": alias,
        "optimizer_steps": 1, "lora_delta_l2": 0.01, "base_frozen": True,
        "model_id": plan["model_id"], "model_revision": plan["model_revision"],
    })
    write_json(receipt, {
        "source": FIXTURE_SOURCE, "loaded_adapter_sha256": sha, "base_revision": plan["model_revision"],
        "advertised_model_ids": [plan["model_id"], alias], "canary_response_model": alias,
    })
    bundles = {arm: {"source": FIXTURE_SOURCE, "manifest_sha256": plan["manifest_sha256"], "trials": []}
               for arm in ("base", "lora")}
    pass_pairs = [(1, 1)] * 4 + [(0, 1)] * 5 + [(1, 0)] + [(0, 0)] * 2
    token_deltas = (20, -20, -30, -10, -15, 0, 10, 40, -50, 5, 25, -30)
    lora_tools = (3, 2, 3, 2, 2, 3, 4, 4, 1, 4, 5, 4)
    for index, task in enumerate(plan["tasks"]):
        base_tokens = 80 + 20 * index
        for arm, score, tokens, tools in (
            ("base", pass_pairs[index][0], base_tokens, 2 + index % 4),
            ("lora", pass_pairs[index][1], base_tokens + token_deltas[index], lora_tools[index]),
        ):
            bundles[arm]["trials"].append({
                **task, "source": FIXTURE_SOURCE, "policy": arm,
                "trial_id": f"synthetic-{arm}-{task['task_id']}",
                "verifier": FIXTURE_SOURCE, "correctness": score, "grade_status": "pass" if score else "fail",
                "adapter_sha256": sha if arm == "lora" else None,
                **{key: plan[key] for key in ("model_id", "model_revision", "protocol_sha256",
                                              "opencode_version", "tool_parser", "rollout")},
                "metrics": {"output_tokens": tokens, "model_calls": 2,
                            "output_tokens_per_call": [tokens // 2, tokens - tokens // 2],
                            "tool_calls": tools, "elapsed_seconds": index + (10 if arm == "base" else 9),
                            "peak_vram_bytes": (42 if arm == "base" else 43) * 10 ** 9},
            })
    bundles["lora"]["trials"].reverse()
    for arm, data in bundles.items():
        write_json(output / f"{arm}.json", data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_output_dir", type=Path)
    args = parser.parse_args()
    make_fixtures(args.new_output_dir)
