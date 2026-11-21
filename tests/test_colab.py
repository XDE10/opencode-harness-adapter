import copy
import json
from pathlib import Path
import shlex
import tempfile
import tomllib
import unittest

from colab.contracts import (DATA, MODEL, PILOT, PLAN, PLAN_PATH, digest, first_update_groups, load_trace,
                             reward, targets, trace_segments, validate_plan, validate_trial, verify_three)
from colab.evaluation import compare, verify_reload
from colab.harbor_pack import prepare
from colab.trl_reward import tool_efficiency
from colab.workflow import serve_config, smoke_plan


def write(path, value):
    path.write_text(json.dumps(value))


def evidence(trial_id, task="boundary", score=0):
    return {"source": "openenv_engine", "model_id": MODEL["id"], "model_revision": MODEL["revision"],
            "protocol_sha256": digest(PLAN_PATH), "policy": "base", "opencode_version": "2.2.7",
            "tool_parser": "hermes", "verifier": "harbor_separate_offline", "correctness": score,
            "trial_id": trial_id, "task_id": task, "metrics": {"tool_calls": 2, "model_calls": 3,
            "output_tokens": 7, "peak_vram_bytes": 42_000_000_000, "elapsed_seconds": 15}}


class ColabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.turns = [
            {"node_id": "first", "prompt_token_ids": [1, 2], "completion_token_ids": [3, 4],
             "per_token_logps": [-0.1, -0.2], "loss_mask": [0, 0, 1, 0]},
            {"node_id": "with-tool", "prompt_token_ids": [1, 2, 3, 4, 5, 6], "completion_token_ids": [7],
             "per_token_logps": [-0.3], "loss_mask": [0, 0, 0, 0, 0, 0, 1]},
            {"node_id": "rewritten", "prompt_token_ids": [8, 9], "completion_token_ids": [10],
             "per_token_logps": [-0.4], "loss_mask": [0, 0, 1]},
        ]

    def trace(self, trial, turns=None):
        path = self.root / (trial["trial_id"] + ".json")
        write(path, {"schema_version": 1, "turns": self.turns if turns is None else turns})
        return {**trial, "trace_path": path.name, "trace_sha256": digest(path)}

    def test_model_lock_serving_and_harbor_for_three_frozen_tasks(self):
        validate_plan()
        command = shlex.split(serve_config("/offline/model"))
        self.assertEqual(command[command.index("--tool-call-parser") + 1], "hermes")
        self.assertIn('{"enable_thinking":false}', command)
        self.assertNotIn("qwen3_xml", command)
        pack = self.root / "harbor"
        prepare(pack)
        self.assertEqual({p.name for p in (pack / "tasks").iterdir()}, set(PILOT))
        task = pack / "tasks" / "boundary"
        with (task / "task.toml").open("rb") as f:
            config = tomllib.load(f)
        self.assertEqual(config["verifier"]["environment_mode"], "separate")
        self.assertEqual(config["environment"]["network_mode"], "no-network")
        self.assertEqual(config["artifacts"], ["/work/solution.py"])
        self.assertEqual({f.name for f in (task / "environment").iterdir()}, {"solution.py", "Dockerfile"})

    def test_smoke_plan_reports_only_bounded_pilot_and_missing_launcher(self):
        info = smoke_plan(Path("/models/pinned"), Path("/tmp/pilot.json"))
        self.assertEqual(info["tasks_in_order"], PILOT)
        self.assertFalse(info["real_capture_launcher_ready"])
        self.assertIsNone(info["commands"]["real_capture"])
        self.assertIn("run-g4-first-trial.sh", info["commands"]["first_g4"])
        self.assertIn("--allow-existing-g4", info["commands"]["first_g4"])
        self.assertIn("--verify-upstream", info["commands"]["validate_real_evidence"])
        self.assertEqual(info["budgets"]["all_trials_max_calls"], 36)
        self.assertEqual(info["budgets"]["all_trials_max_output_tokens"], 6144)
        self.assertEqual(info["gpu_time_seconds"]["phase_total"], 1620)
        self.assertGreater(info["gpu_time_seconds"]["absolute_stop"], info["gpu_time_seconds"]["phase_total"])

    def test_next_token_targets_do_not_score_prompt_tools_or_masked_output(self):
        turns = load_trace(self.trace(evidence("mask")), self.root)
        self.assertEqual([targets(t) for t in turns], [[(1, 3, -0.1)], [(5, 7, -0.3)], [(1, 10, -0.4)]])
        self.assertEqual([(row["node_id"], row["segment"]) for row in trace_segments(turns)],
                         [("first", 0), ("with-tool", 0), ("rewritten", 1)])

    def test_bad_masks_duplicate_nodes_missing_logprobs_and_mock_refused(self):
        for field, value in (("loss_mask", [1, 0, 1, 0]), ("per_token_logps", []), ("node_id", "with-tool")):
            bad = copy.deepcopy(self.turns)
            bad[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                load_trace(self.trace(evidence("bad"), bad), self.root)
        with self.assertRaisesRegex(ValueError, "genuine"):
            validate_trial({**evidence("mock"), "source": "scripted_mock"}, policy="base")

    def test_three_task_gate_and_group_reward_spread(self):
        path = self.root / "pilot.json"
        attempts = [self.trace(evidence(task, task)) for task in PILOT]
        write(path, {"trials": attempts})
        self.assertEqual(set(verify_three(path)), set(PILOT))
        attempts[0]["metrics"]["tool_calls"] = 0
        write(path, {"trials": attempts})
        with self.assertRaisesRegex(ValueError, "did not call a tool"):
            verify_three(path)
        group = [self.trace(evidence(f"trial-{i}", score=i % 2)) for i in range(4)]
        write(path, {"groups": [group]})
        advantages = [row[2] for row in first_update_groups(path)]
        self.assertLess(min(advantages), 0)
        self.assertGreater(max(advantages), 0)
        self.assertAlmostEqual(sum(advantages), 0)
        for trial in group:
            trial["correctness"] = 1
        write(path, {"groups": [group]})
        with self.assertRaisesRegex(ValueError, "correctness spread"):
            first_update_groups(path)

    def test_upstream_tool_efficiency_preserves_the_locked_binary_reward(self):
        self.assertEqual(tool_efficiency(0, 15), 1)
        self.assertEqual(tool_efficiency(5, 10), 0.5)
        self.assertEqual(tool_efficiency(16, 15), 0)
        self.assertIsNone(tool_efficiency(None, 15))
        self.assertIsNone(tool_efficiency(0, 0))
        attempt = {"metrics": {"tool_calls": 0}}
        self.assertEqual(reward({**attempt, "correctness": 0}), 0)
        self.assertEqual(reward({**attempt, "correctness": 1}), 1.1)
        self.assertEqual(reward({"correctness": 1, "metrics": {"tool_calls": 15}}), 1)

    def test_reload_identity_guards_fresh_alias(self):
        binary = self.root / "adapter_model.safetensors"
        binary.write_bytes(b"synthetic checkpoint for identity test only")
        sha = digest(binary)
        alias = "oca-lora-" + sha[:16]
        write(self.root / "update.json", {"adapter_sha256": sha, "expected_served_alias": alias,
            "optimizer_steps": 1, "lora_delta_l2": 0.01, "base_frozen": True,
            "model_id": MODEL["id"], "model_revision": MODEL["revision"]})
        receipt = self.root / "receipt.json"
        info = {"loaded_adapter_sha256": sha, "base_revision": MODEL["revision"],
                "advertised_model_ids": [MODEL["id"], alias], "canary_response_model": alias}
        write(receipt, info)
        self.assertEqual(verify_reload(self.root, receipt), sha)
        write(receipt, {**info, "canary_response_model": MODEL["id"]})
        with self.assertRaisesRegex(ValueError, "not advertised and selected"):
            verify_reload(self.root, receipt)

    def test_holdout_pairs_report_both_arms_and_stop_on_task_drift(self):
        base_path, lora_path = self.root / "pre.json", self.root / "post.json"
        sha = "a" * 64
        rows = [dict(evidence(f"{repo['repo']}-{i}", f"task-{i}", int(i < repo["count"] // 2)), repository=repo["repo"],
                     repo_revision=repo["revision"], task_sha256="b" * 64, seed=i)
                for repo in DATA["heldout"] for i in range(repo["count"])]
        post = [dict(row, policy="lora", trial_id=row["trial_id"] + "-post", adapter_sha256=sha, correctness=1)
                for row in rows]
        write(base_path, {"trials": rows})
        write(lora_path, {"trials": post})
        info = compare(base_path, lora_path, sha)
        self.assertEqual((info["paired_tasks"], info["base"]["pass_at_1"], info["lora"]["pass_at_1"]), (24, .5, 1))
        post[-1]["task_sha256"] = "c" * 64
        write(lora_path, {"trials": post})
        with self.assertRaisesRegex(ValueError, "task or seed changed"):
            compare(base_path, lora_path, sha)
