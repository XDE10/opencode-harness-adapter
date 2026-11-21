"""Check reloaded LoRA identity and compare strictly paired holdout evidence."""

import hashlib
import json
import math
import statistics

from .contracts import (DATA, FIXTURE_SOURCE, HEX64, MODEL, PILOT, PLAN, PLAN_PATH, ROLLOUT, digest,
                        read_json, read_json_bytes, require, validate_trial)
from .first_batch import MANIFESTS, verify_batch

V3_MANIFEST_SHA256 = "007666b2a193a9ffeb7f077f4df46751dbd03046f38cedd5c8f87a39b3dd9e6d"
V3_PROTOCOL_SHA256 = "e52c3dd05336ca06830c8c7e0eb42706e7a69050ec26214bc622b0fb02da97cf"


def verify_reload(checkpoint, receipt, *, fixture=False):
    update = read_json(checkpoint / "update.json")
    recorded = read_json(receipt)
    require(all((record.get("source") == FIXTURE_SOURCE) == fixture for record in (update, recorded)),
            "checkpoint and reload receipt provenance must match comparison mode")
    actual = digest(checkpoint / "adapter_model.safetensors")
    alias = "oca-lora-" + actual[:16]
    require(update["adapter_sha256"] == actual and update["expected_served_alias"] == alias,
            "checkpoint differs from the successful update")
    require(update["optimizer_steps"] == 1 and update["lora_delta_l2"] > 0 and update["base_frozen"] is True,
            "checkpoint lacks evidence of a nonzero adapter-only update")
    require((update["model_id"], update["model_revision"]) == (MODEL["id"], MODEL["revision"]),
            "checkpoint base differs from the lock")
    require(recorded["loaded_adapter_sha256"] == actual and recorded["base_revision"] == MODEL["revision"],
            "trusted serving startup receipt does not match checkpoint")
    require(alias in recorded["advertised_model_ids"] and recorded["canary_response_model"] == alias,
            "new LoRA alias was not advertised and selected by the serving engine")
    return actual


def compare(before, after, adapter_sha):
    holdout = {item["repo"]: item for item in DATA["heldout"]}
    base, adapter = {}, {}
    seen = set()
    for path, arm, out in ((before, "base", base), (after, "lora", adapter)):
        for attempt in read_json(path)["trials"]:
            validate_trial(attempt, policy=arm)
            repo = attempt["repository"]
            require(repo in holdout and attempt["repo_revision"] == holdout[repo]["revision"],
                    "trial repository or revision is outside the frozen holdout plan")
            key = (repo, attempt["task_id"])
            require(key not in out and attempt["trial_id"] not in seen, "duplicate task or trial")
            require(key[1] and key[1] not in PILOT and HEX64.fullmatch(attempt["task_sha256"])
                    and type(attempt["seed"]) is int, "invalid frozen task identity or paired seed")
            require(attempt.get("adapter_sha256") == (adapter_sha if arm == "lora" else None),
                    "incorrect adapter identity for holdout arm")
            out[key] = attempt
            seen.add(attempt["trial_id"])
    require(base.keys() == adapter.keys() and all(
        sum(key[0] == repo for key in base) == item["count"] for repo, item in holdout.items()),
        "same complete holdout required under both policies")
    for key, item in base.items():
        other = adapter[key]
        require(item["task_sha256"] == other["task_sha256"] and item["seed"] == other["seed"],
                "task or seed changed between policy arms")

    paired_solved = [key for key in base if base[key]["correctness"] == adapter[key]["correctness"] == 1]
    wins = sum(base[key]["correctness"] < adapter[key]["correctness"] for key in base)
    losses = sum(base[key]["correctness"] > adapter[key]["correctness"] for key in base)

    def describe(arm):
        rows = list(arm.values())
        result = {"pass_at_1": sum(row["correctness"] for row in rows) / len(rows)}
        for name in ("output_tokens", "tool_calls", "elapsed_seconds"):
            result[f"median_{name}"] = statistics.median(row["metrics"][name] for row in rows)
            result[f"paired_solved_median_{name}"] = (
                statistics.median(arm[key]["metrics"][name] for key in paired_solved) if paired_solved else None)
        result["peak_vram_bytes"] = max(row["metrics"]["peak_vram_bytes"] for row in rows)
        return result
    return {"paired_tasks": len(base), "paired_solved": len(paired_solved), "wins": wins, "losses": losses,
            "base": describe(base), "lora": describe(adapter)}


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def comparison_plan_v3():
    require(digest(MANIFESTS[3]) == V3_MANIFEST_SHA256, "frozen v3 manifest changed")
    require(digest(PLAN_PATH) == V3_PROTOCOL_SHA256, "frozen v3 comparison protocol changed")
    manifest = verify_batch(version=3)
    return {
        "manifest_id": manifest["id"],
        "manifest_sha256": V3_MANIFEST_SHA256,
        "protocol_sha256": V3_PROTOCOL_SHA256,
        "model_id": MODEL["id"],
        "model_revision": MODEL["revision"],
        "opencode_version": PLAN["runtime"]["opencode"],
        "tool_parser": PLAN["runtime"]["vllm_tool_parser"],
        "rollout": dict(ROLLOUT),
        "tasks": [
            {"task_id": task["id"], "repository": task["repo"], "repo_revision": task["revision"],
             "task_sha256": hashlib.sha256(canonical_json(task["files"]).encode("ascii")).hexdigest(),
             "seed": ROLLOUT["seed"]}
            for task in manifest["tasks"] if task["split"] == "heldout"
        ],
    }


def unique_json_object(pairs):
    obj = dict(pairs)
    require(len(pairs) == len(obj), "duplicate JSON object key")
    return obj


def read_v3_arm(path, arm, plan, expected, adapter_sha, seen_trials, *, fixture):
    raw = read_json_bytes(path)
    document = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_json_object)
    require(isinstance(document, dict), f"{arm}: expected a trial bundle")
    source = FIXTURE_SOURCE if fixture else "openenv_engine"
    require(document.get("source") == source, f"{arm}: expected bundle source {source}")
    require(document.get("manifest_sha256") == plan["manifest_sha256"], f"{arm}: v3 manifest digest differs")
    require(isinstance(document.get("trials"), list), f"{arm}: trials must be a list")
    settings = canonical_json(plan["rollout"])
    attempts = {}
    for trial in document["trials"]:
        require(isinstance(trial, dict), f"{arm}: expected a trial object")
        task_id = trial.get("task_id")
        label = f"{arm}/{task_id} ({trial.get('trial_id')})"
        require(isinstance(task_id, str) and task_id in expected, f"{label}: task is outside the frozen v3 holdout")
        require(task_id not in attempts, f"{label}: duplicate task ID")
        for key, value in expected[task_id].items():
            require(trial.get(key) == value, f"{label}: {key} differs from the frozen pairing plan")
        require(canonical_json(trial.get("rollout")) == settings, f"{label}: rollout budget or sampling differs")
        try:
            metrics = validate_trial(trial, policy=arm, fixture=fixture)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f"{label}: invalid trial: {exc}") from exc
        require(trial["trial_id"] not in seen_trials, f"{label}: duplicate trial ID")
        require(trial.get("grade_status") == ("pass" if trial["correctness"] else "fail"),
                f"{label}: independent grade status is missing or unscorable")
        require(trial.get("adapter_sha256") == adapter_sha, f"{label}: incorrect adapter identity")
        outputs = metrics.get("output_tokens_per_call")
        require(isinstance(outputs, list) and len(outputs) == metrics["model_calls"] and
                all(type(count) is int and 0 <= count <= ROLLOUT["max_output_tokens_per_call"] for count in outputs)
                and sum(outputs) == metrics["output_tokens"],
                f"{label}: per-call engine token counts violate budget or totals")
        seen_trials.add(trial["trial_id"])
        attempts[task_id] = trial
    missing = sorted(expected.keys() - attempts.keys())
    require(not missing, f"{arm}: missing frozen v3 task IDs: {', '.join(missing)}")
    return attempts, hashlib.sha256(raw).hexdigest()


def exact_mcnemar(wins, losses):
    discordant = wins + losses
    tail = sum(math.comb(discordant, k) for k in range(min(wins, losses) + 1))
    return {"method": "exact_mcnemar_two_sided", "discordant_pairs": discordant,
            "p_value": min(1.0, 2 * tail / (2 ** discordant))}


def paired_costs(pairs):
    costs = {"paired_tasks": len(pairs)}
    for metric in ("output_tokens", "tool_calls", "elapsed_seconds"):
        if not pairs:
            costs[metric] = None
            continue
        base = [pair["base"]["metrics"][metric] for pair in pairs]
        lora = [pair["lora"]["metrics"][metric] for pair in pairs]
        costs[metric] = {
            "base_total": sum(base), "lora_total": sum(lora),
            "base_median": statistics.median(base), "lora_median": statistics.median(lora),
            "total_lora_minus_base": sum(lora) - sum(base),
            "median_paired_lora_minus_base": statistics.median(right - left for left, right in zip(base, lora)),
        }
    return costs


def compare_v3(before, after, adapter_sha, *, fixture=False):
    require(isinstance(adapter_sha, str) and HEX64.fullmatch(adapter_sha), "invalid verified adapter digest")
    plan = comparison_plan_v3()
    tasks = plan.pop("tasks")
    expected = {task["task_id"]: task for task in tasks}
    seen = set()
    base, before_sha = read_v3_arm(before, "base", plan, expected, None, seen, fixture=fixture)
    lora, after_sha = read_v3_arm(after, "lora", plan, expected, adapter_sha, seen, fixture=fixture)
    pairs = []
    for task_id, task in expected.items():
        pair = dict(task)
        for arm, trial in (("base", base[task_id]), ("lora", lora[task_id])):
            pair[arm] = {key: trial[key] for key in ("trial_id", "grade_status", "correctness", "metrics")}
        pair["lora_minus_base"] = {"correctness": pair["lora"]["correctness"] - pair["base"]["correctness"],
                                   **{key: lora[task_id]["metrics"][key] - base[task_id]["metrics"][key]
                                      for key in ("output_tokens", "tool_calls")}}
        pairs.append(pair)
    solved = [pair for pair in pairs if pair["base"]["correctness"] == pair["lora"]["correctness"] == 1]
    wins = sum(pair["lora_minus_base"]["correctness"] == 1 for pair in pairs)
    losses = sum(pair["lora_minus_base"]["correctness"] == -1 for pair in pairs)
    arms = {
        arm: {"passed": len(solved) + solo, "pass_at_1": (len(solved) + solo) / len(pairs),
              "peak_vram_bytes": max(pair[arm]["metrics"]["peak_vram_bytes"] for pair in pairs)}
        for arm, solo in (("base", losses), ("lora", wins))
    }
    return {
        **plan, "source": FIXTURE_SOURCE if fixture else "openenv_engine",
        "synthetic": fixture, "usable_for_grpo": False, "adapter_sha256": adapter_sha,
        "input_sha256": {"base": before_sha, "lora": after_sha},
        "paired_tasks": len(pairs), **arms,
        "pass_rate_delta_percentage_points": 100 * (wins - losses) / len(pairs),
        "outcomes": {"both_pass": len(solved), "both_fail": len(pairs) - len(solved) - wins - losses,
                     "lora_only": wins, "base_only": losses},
        "exact_test": exact_mcnemar(wins, losses),
        "limitations": [
            "One seed per task on 12 fixed candidates. Exact-test power is limited by the discordant pairs.",
            "Inference assumes independent pairs with exchangeable arm labels under the null.",
            "Results describe this fixed holdout. Common-success costs condition on both policies passing.",
        ],
        "costs": {"all_pairs": paired_costs(pairs), "both_pass": paired_costs(solved)},
        "pairs": pairs,
    }
