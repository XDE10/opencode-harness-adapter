import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from colab.contracts import FIXTURE_SOURCE, ROOT, digest, read_json, validate_trial
from colab.evaluation import MANIFESTS, compare_v3, comparison_plan_v3, exact_mcnemar, verify_reload
from fixtures.paired_v3 import make_fixtures, write_json


class V3ComparisonTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name) / "synthetic"
        make_fixtures(self.output)
        self.before = self.output / "base.json"
        self.after = self.output / "lora.json"
        self.checkpoint = self.output / "checkpoint"
        self.receipt = self.output / "reload.json"
        self.adapter_sha = verify_reload(self.checkpoint, self.receipt, fixture=True)

    def test_fixture_report_through_cli(self):
        args = [str(ROOT / "scripts/run-colab.sh"), "compare", str(self.checkpoint), str(self.receipt),
                str(self.before), str(self.after), "--manifest-version", "3"]
        denied = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(denied.returncode, 2)
        self.assertIn("provenance must match", denied.stderr)
        self.assertEqual(denied.stdout, "")
        result = subprocess.run(args + ["--fixture"], cwd=ROOT, capture_output=True, text=True, check=True, timeout=10)
        report = json.loads(result.stdout)
        self.assertTrue(report["synthetic"])
        self.assertEqual(report["source"], FIXTURE_SOURCE)
        self.assertFalse(report["usable_for_grpo"])
        self.assertEqual(report["input_sha256"], {"base": digest(self.before), "lora": digest(self.after)})
        self.assertEqual(report["paired_tasks"], 12)
        self.assertEqual([row["task_id"] for row in report["pairs"]],
                         [row["task_id"] for row in comparison_plan_v3()["tasks"]])
        self.assertEqual(report["outcomes"], {"both_pass": 4, "both_fail": 2, "lora_only": 5, "base_only": 1})
        self.assertEqual((report["base"]["passed"], report["lora"]["passed"]), (5, 9))
        self.assertAlmostEqual(report["pass_rate_delta_percentage_points"], 100 / 3)
        self.assertEqual(report["exact_test"]["discordant_pairs"], 6)
        self.assertEqual(report["exact_test"]["p_value"], 0.21875)
        self.assertEqual(report["pairs"][0]["lora_minus_base"], {"correctness": 0, "output_tokens": 20, "tool_calls": 1})
        for name, count, token_totals, median_delta, tool_totals in (
            ("all_pairs", 12, (2280, 2225), -5, (42, 37)),
            ("both_pass", 4, (440, 400), -15, (14, 10)),
        ):
            costs = report["costs"][name]
            self.assertEqual(costs["paired_tasks"], count)
            self.assertEqual(tuple(costs["output_tokens"][f"{arm}_total"] for arm in ("base", "lora")), token_totals)
            self.assertEqual(costs["output_tokens"]["median_paired_lora_minus_base"], median_delta)
            self.assertEqual(tuple(costs["tool_calls"][f"{arm}_total"] for arm in ("base", "lora")), tool_totals)

    def test_zero_discordance_and_empty_common_success(self):
        for path in (self.before, self.after):
            bundle = read_json(path)
            for row in bundle["trials"]:
                row.update(correctness=0, grade_status="fail")
            write_json(path, bundle)
        report = compare_v3(self.before, self.after, self.adapter_sha, fixture=True)
        self.assertEqual(report["pass_rate_delta_percentage_points"], 0)
        self.assertEqual(report["outcomes"]["both_fail"], 12)
        self.assertEqual(report["costs"]["both_pass"],
                         {"paired_tasks": 0, "output_tokens": None, "tool_calls": None, "elapsed_seconds": None})
        self.assertEqual(report["exact_test"]["p_value"], 1)
        self.assertEqual(exact_mcnemar(0, 12)["p_value"], 2 / 4096)
        self.assertEqual(exact_mcnemar(5, 1), exact_mcnemar(1, 5))

    def test_v3_rejects_identity_budget_infrastructure_and_provenance_drift(self):
        original = self.after.read_text(encoding="utf-8")
        for key, value, message in (
            ("task_id", "boundary", "outside the frozen v3 holdout"),
            ("repo_revision", "a" * 40, "repo_revision differs"),
            ("task_sha256", "a" * 64, "task_sha256 differs"),
            ("seed", -1, "seed differs"),
            ("adapter_sha256", "a" * 64, "incorrect adapter identity"),
            ("grade_status", "test_timeout", "grade status is missing or unscorable"),
            ("correctness", True, "independent rollout grade is missing or unscorable"),
            ("source", "openenv_engine", "requires synthetic fixture evidence"),
        ):
            bundle = json.loads(original)
            bundle["trials"][0][key] = value
            write_json(self.after, bundle)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, message):
                compare_v3(self.before, self.after, self.adapter_sha, fixture=True)
        for field, key, value, message in (
            ("rollout", "timeout_seconds", 181, "rollout budget or sampling differs"),
            ("rollout", "top_p", True, "rollout budget or sampling differs"),
            ("metrics", "output_tokens_per_call", [513, 0], "per-call engine token counts"),
            ("metrics", "output_tokens_per_call", [20, 20], "per-call engine token counts"),
            ("metrics", "model_calls", 13, "model-call budget exceeded"),
        ):
            bundle = json.loads(original)
            bundle["trials"][0][field][key] = value
            write_json(self.after, bundle)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, message):
                compare_v3(self.before, self.after, self.adapter_sha, fixture=True)

    def test_missing_and_duplicate_ids_and_bundle_lock_are_rejected(self):
        original = self.after.read_text(encoding="utf-8")
        for mode, message in (
            ("missing", "missing frozen v3 task IDs"),
            ("duplicate task", "duplicate task ID"),
            ("duplicate trial", "duplicate trial ID"),
            ("wrong manifest", "v3 manifest digest differs"),
        ):
            bundle = json.loads(original)
            rows = bundle["trials"]
            if mode == "missing":
                rows.pop()
            elif mode == "duplicate task":
                rows.append({**rows[0], "trial_id": "fresh-trial-id"})
            elif mode == "duplicate trial":
                rows[0]["trial_id"] = read_json(self.before)["trials"][0]["trial_id"]
            else:
                bundle["manifest_sha256"] = "a" * 64
            write_json(self.after, bundle)
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, message):
                compare_v3(self.before, self.after, self.adapter_sha, fixture=True)
        self.after.write_text(original.replace('"trials":', '"trials": [], "trials":', 1), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            compare_v3(self.before, self.after, self.adapter_sha, fixture=True)

    def test_fixture_cannot_enter_real_validators_and_frozen_manifest_cannot_drift(self):
        with self.assertRaisesRegex(ValueError, "expected bundle source openenv_engine"):
            compare_v3(self.before, self.after, self.adapter_sha)
        trial = read_json(self.before)["trials"][0]
        with self.assertRaisesRegex(ValueError, "need genuine OpenEnv engine capture"):
            validate_trial(trial, policy="base")
        path = self.output / "drifted-v3-manifest.json"
        path.write_bytes(MANIFESTS[3].read_bytes() + b"\n")
        with patch.dict(MANIFESTS, {3: path}), self.assertRaisesRegex(ValueError, "frozen v3 manifest changed"):
            comparison_plan_v3()
