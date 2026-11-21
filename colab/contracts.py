"""Validate the single-card plan and data exported by the trusted rollout host."""

import hashlib
import json
import math
from pathlib import Path
import re
import statistics

from capture.trace import validate_turn

from .trl_reward import tool_efficiency

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "protocol" / "colab-g4-v1.json"
LEGACY_DATA_PATH = ROOT / "protocol" / "dataset-plan-v1.json"
DATA_PATH = ROOT / "protocol" / "dataset-plan-v2.json"
PLAN = json.loads(PLAN_PATH.read_text())
DATA = json.loads(DATA_PATH.read_text())
MODEL, ROLLOUT, UPDATE = (PLAN[key] for key in ("model", "rollout", "update"))
PILOT = ("boundary", "parsing", "serialization")
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
FIXTURE_SOURCE = "synthetic_fixture"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def read_json_bytes(path):
    require(path.is_file() and path.stat().st_size <= 32 * 1024 * 1024, f"invalid JSON file: {path.name}")
    return path.read_bytes()


def read_json(path):
    return json.loads(read_json_bytes(path).decode("utf-8"))


def validate_plan(data=DATA, *, version=2):
    if version == 2:
        require(data["id"] == "dataset-plan-v2" and data["base_plan_sha256"] == digest(LEGACY_DATA_PATH),
                "v2 split does not match its recorded base plan")
        previous = read_json(LEGACY_DATA_PATH)
        revisions = {row["repo"]: row["revision"] for row in data["heldout"]}
        require(data["train"] == previous["train"] and all(
            revisions.get(row["repo"]) == row["revision"] for row in previous["heldout"]),
            "v2 changed repository identities that were already pinned")
    train, holdout = ({entry["repo"] for entry in data[key]} for key in ("train", "heldout"))
    require((len(train), len(holdout)) == (6, 3 if version == 1 else 4) and not train & holdout,
            "repository split differs or overlaps")
    for key, slots in (("train", 12), ("heldout", 8 if version == 1 else 6)):
        require(len(data[key]) == len({entry["repo"] for entry in data[key]}), "duplicate repository")
        require(all(entry["count"] == slots and HEX40.fullmatch(entry["revision"]) for entry in data[key]),
                "unlocked repository or unexpected quota")
    require(tuple(data["pilot_excluded"]) == PILOT, "pilot exclusions changed")
    require(HEX40.fullmatch(MODEL["revision"]) and len(MODEL["files"]) == 10
            and all(HEX64.fullmatch(value) for value in MODEL["files"].values()), "incomplete model lock")


def verify_snapshot(path):
    for filename, expected in MODEL["files"].items():
        require(digest(path / filename) == expected, f"pinned snapshot checksum mismatch: {filename}")


def valid_number(value, low, high=math.inf):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def validate_trial(trial, *, policy, fixture=False):
    if fixture:
        require(trial.get("source") == FIXTURE_SOURCE, "fixture mode requires synthetic fixture evidence")
    else:
        require(trial.get("source") == "openenv_engine", "need genuine OpenEnv engine capture, not CLI or mock")
    require((trial.get("model_id"), trial.get("model_revision")) == (MODEL["id"], MODEL["revision"]),
            "trial model does not match the lock")
    require(trial.get("protocol_sha256") == digest(PLAN_PATH), "trial protocol does not match the lock")
    require(trial.get("policy") == policy, "incorrect rollout policy")
    require(trial.get("opencode_version") == PLAN["runtime"]["opencode"], "incorrect OpenCode version")
    require(trial.get("tool_parser") == PLAN["runtime"]["vllm_tool_parser"], "incorrect engine tool parser")
    reward = trial.get("correctness")
    verifier = FIXTURE_SOURCE if fixture else "harbor_separate_offline"
    require(trial.get("verifier") == verifier and
            type(reward) is int and reward in (0, 1), "independent rollout grade is missing or unscorable")
    require(isinstance(trial.get("trial_id"), str) and trial["trial_id"], "missing trial identity")
    metrics = trial["metrics"]
    for key in ("tool_calls", "model_calls", "output_tokens", "peak_vram_bytes"):
        require(type(metrics.get(key)) is int and metrics[key] >= 0, f"invalid measured metric: {key}")
    require(0 < metrics["model_calls"] <= ROLLOUT["max_model_calls"], "model-call budget exceeded")
    require(0 < metrics["output_tokens"] <= ROLLOUT["max_output_tokens_per_trial"], "output budget exceeded")
    require(0 < metrics["peak_vram_bytes"] < PLAN["runtime"]["peak_stop_bytes"], "peak VRAM unavailable or above stop threshold")
    require(valid_number(metrics.get("elapsed_seconds"), 0, ROLLOUT["timeout_seconds"])
            and metrics["elapsed_seconds"] > 0, "trial duration unavailable or above budget")
    return metrics


def load_trace(trial, directory, *, verify_upstream=False):
    relative = Path(trial["trace_path"])
    source = (directory / relative).resolve()
    require(not relative.is_absolute() and source.is_relative_to(directory.resolve()),
            "trace must be inside the evidence directory")
    trace = read_json(source)
    require(digest(source) == trial.get("trace_sha256"), "trace digest mismatch")
    if verify_upstream:
        from openenv.core.harness import TrainingTrace
        TrainingTrace.model_validate(trace)
    require(trace.get("schema_version") == 1 and isinstance(trace.get("turns"), list)
            and trace["turns"], "missing OpenEnv TrainingTrace v1")
    seen = set()
    sampled, eligible = 0, 0
    for turn in trace["turns"]:
        validate_turn(turn, vocabulary=MODEL["vocab_size"], context=ROLLOUT["max_context_tokens"],
                      output=ROLLOUT["max_output_tokens_per_call"])
        node = turn["node_id"]
        require(node not in seen, "duplicate node_id")
        seen.add(node)
        sampled += len(turn["completion_token_ids"])
        eligible += sum(turn["loss_mask"])
    require(eligible and sampled <= trial["metrics"]["output_tokens"] and
            len(seen) <= trial["metrics"]["model_calls"], "untrainable trace or inconsistent capture metrics")
    return trace["turns"]


def policy_trial(trial, directory, *, verify_upstream=False, policy="base"):
    validate_trial(trial, policy=policy)
    return trial, load_trace(trial, directory, verify_upstream=verify_upstream)


def trace_segments(turns):
    """Annotate sequential context resets; never join turns in the objective."""
    segments = []
    prefix, segment = [], -1
    for turn in turns:
        prompt = turn["prompt_token_ids"]
        if not segments or prompt[:len(prefix)] != prefix:
            segment += 1
        prefix = prompt + turn["completion_token_ids"]
        sequence = json.dumps(prefix, separators=(",", ":")).encode()
        segments.append({"node_id": turn["node_id"], "segment": segment,
                         "sequence_sha256": hashlib.sha256(sequence).hexdigest()})
    return segments


def targets(turn):
    """Positions are next-token logits indices, not input label indices."""
    begin = len(turn["prompt_token_ids"])
    return [(begin + i - 1, token, logp) for i, (token, logp) in enumerate(zip(
        turn["completion_token_ids"], turn["per_token_logps"])) if turn["loss_mask"][begin + i]]


def verify_three(path, *, verify_upstream=False):
    trials = read_json(path)["trials"]
    require(len(trials) == len(PILOT) and {trial["task_id"] for trial in trials} == set(PILOT),
            "expected a single independent attempt on each of the three fixed tasks")
    require(len({trial["trial_id"] for trial in trials}) == len(PILOT), "duplicate trial")
    results = {}
    for trial in trials:
        _, turns = policy_trial(trial, path.parent, verify_upstream=verify_upstream)
        require(trial["metrics"]["tool_calls"] > 0, "OpenCode did not call a tool")
        results[trial["task_id"]] = {"correctness": trial["correctness"], "trial_id": trial["trial_id"],
                                     "segments": trace_segments(turns), "metrics": trial["metrics"]}
    return results


def reward(trial):
    correctness = trial["correctness"]
    bonus = tool_efficiency(trial["metrics"]["tool_calls"], UPDATE["efficiency_budget"])
    require(bonus is not None, "tool efficiency requires a measured tool count and a positive budget")
    return correctness * (1 + UPDATE["efficiency_weight"] * bonus)


def first_update_groups(path, *, verify_upstream=False):
    groups = read_json(path)["groups"]
    require(1 <= len(groups) <= UPDATE["max_groups_for_first_step"], "unexpected number of pilot groups")
    seen = set()
    tasks = set()
    admitted = []
    for trials in groups:
        require(len(trials) == UPDATE["group_size"], "incorrect GRPO group size")
        require(trials[0]["task_id"] in PILOT and len({trial["task_id"] for trial in trials}) == 1,
                "GRPO advantages require rollouts from the same pilot task")
        task = trials[0]["task_id"]
        require(task not in tasks, "multiple first-step groups for one pilot task")
        tasks.add(task)
        require({trial["correctness"] for trial in trials} == {0, 1}, "zero/missing correctness spread: do not update")
        validated = [policy_trial(trial, path.parent, verify_upstream=verify_upstream) for trial in trials]
        values = [reward(trial) for trial, _ in validated]
        mean, spread = statistics.mean(values), statistics.pstdev(values)
        for (trial, turns), score in zip(validated, values):
            require(trial["trial_id"] not in seen, "duplicate trial across groups")
            seen.add(trial["trial_id"])
            admitted.append((trial["trial_id"], turns, (score - mean) / (spread + 1e-4)))
    return admitted
