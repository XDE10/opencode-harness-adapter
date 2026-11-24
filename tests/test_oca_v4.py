"""Unit tests for the lean `oca` v4 pipeline:
tasks, domain isolation, single-file & multi-file repo_pytest grading, prefix-merged packing,
dual-harness config (OpenCode & Pi), proxy capture, 10-attack adversarial suite, statistics & plots.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from oca import CONFIG
from oca.adversarial import run_adversarial_suite
from oca.eval import (
    bootstrap_ci,
    classify_trial,
    compare_arms,
    exact_mcnemar_p,
    paired_permutation_p,
    pass_at_k_unbiased,
)
from oca.grade import controls, grade_repo
from oca.harnesses import get_harness
from oca.plots import render_failure_taxonomy, render_logprob_hist, render_training_curve, render_transfer_matrix
from oca.proxy import _selftest as proxy_selftest
from oca.reward import compute_reward
from oca.tasks import by_id, load
from oca.train import pack_trajectory_segments
from oca.validate import check_repo_task, check_task


class TestOcaV4(unittest.TestCase):
    def test_v3_tasks_and_controls(self):
        tasks = [t for t in load() if t.source == "v3"]
        self.assertEqual(len(tasks), 27)
        res = controls(tasks[:3])
        self.assertTrue(all(r["ok"] for r in res))

    def test_cleaned_dataset_domain_disjoint(self):
        all_t = load()
        gen = [t for t in all_t if t.source.startswith("tasks-")]
        if gen:
            train_doms = {t.domain for t in gen if t.split == "train"}
            held_doms = {t.domain for t in gen if t.split == "heldout"}
            self.assertTrue(len(train_doms) >= 5 and len(held_doms) >= 3)
            self.assertEqual(train_doms & held_doms, set(), f"L1 domain leakage: {train_doms & held_doms}")
            self.assertTrue(all(t.split in ("train", "heldout") for t in gen))

        repos = [t for t in all_t if t.source.startswith("repo_")]
        if repos:
            r_tr = {t.domain for t in repos if t.split == "train"}
            r_ho = {t.domain for t in repos if t.split == "heldout"}
            self.assertEqual(r_tr & r_ho, set(), f"L2 domain leakage: {r_tr & r_ho}")

        ood = [t for t in all_t if t.source.startswith("ood_")]
        if ood:
            self.assertTrue(all(t.split == "heldout" and t.kind == "repo_pytest" for t in ood))

    def test_validator_catches_partial_invariant(self):
        t = by_id()["sorted-interval"]
        verdict = check_task(t.task_dir, t.grader_dir)
        self.assertTrue(verdict["ok"], verdict)

    def test_repo_pytest_grading_and_triple_control(self):
        with tempfile.TemporaryDirectory(prefix="oca-repo-test-") as tmp:
            root = Path(tmp)
            tdir = root / "tasks" / "mini-calc"
            gdir = root / "grader" / "mini-calc"
            (tdir / "src").mkdir(parents=True)
            (tdir / "tests").mkdir(parents=True)
            (gdir / "tests_hidden").mkdir(parents=True)
            (gdir / "reference" / "src").mkdir(parents=True)
            (gdir / "partial" / "src").mkdir(parents=True)

            (tdir / "TASK.md").write_text("Fix `src/mathops.py` and `src/engine.py`.\n", encoding="utf-8")
            (tdir / "src" / "__init__.py").write_text("", encoding="utf-8")
            (tdir / "src" / "mathops.py").write_text("def clamp(x, lo, hi):\n    return max(lo, x)\n", encoding="utf-8")
            (tdir / "src" / "engine.py").write_text(
                "from mathops import clamp\ndef apply(vals, lo, hi):\n    return [clamp(v, lo, hi) for v in vals]\n",
                encoding="utf-8",
            )
            (tdir / "tests" / "test_smoke.py").write_text(
                "from engine import apply\ndef test_smoke():\n    assert apply([0, 5], 1, 10) == [1, 5]\n",
                encoding="utf-8",
            )

            # Reference fixes both clamp upper bound and empty/reversed range handling
            (gdir / "reference" / "src" / "__init__.py").write_text("", encoding="utf-8")
            (gdir / "reference" / "src" / "mathops.py").write_text(
                "def clamp(x, lo, hi):\n    if lo > hi:\n        raise ValueError('bad')\n    return min(hi, max(lo, x))\n",
                encoding="utf-8",
            )
            (gdir / "reference" / "src" / "engine.py").write_text(
                "from mathops import clamp\ndef apply(vals, lo, hi):\n    if lo > hi:\n        raise ValueError('bad')\n    return [clamp(v, lo, hi) for v in vals]\n",
                encoding="utf-8",
            )

            # Partial fixes upper bound but misses lo > hi ValueError
            (gdir / "partial" / "src" / "__init__.py").write_text("", encoding="utf-8")
            (gdir / "partial" / "src" / "mathops.py").write_text(
                "def clamp(x, lo, hi):\n    return min(hi, max(lo, x))\n", encoding="utf-8"
            )
            (gdir / "partial" / "src" / "engine.py").write_text(
                "from mathops import clamp\ndef apply(vals, lo, hi):\n    return [clamp(v, lo, hi) for v in vals]\n",
                encoding="utf-8",
            )

            (gdir / "tests_hidden" / "test_hidden.py").write_text(
                "import pytest\nfrom engine import apply\n"
                "def test_1(): assert apply([0], 1, 5) == [1]\n"
                "def test_2(): assert apply([3], 1, 5) == [3]\n"
                "def test_3(): assert apply([9], 1, 5) == [5]\n"
                "def test_4(): assert apply([1, 5, 9], 1, 5) == [1, 5, 5]\n"
                "def test_5(): assert apply([], 1, 5) == []\n"
                "def test_6():\n    with pytest.raises(ValueError): apply([1], 5, 1)\n",
                encoding="utf-8",
            )

            verdict = check_repo_task(tdir, gdir)
            self.assertTrue(verdict["ok"], verdict)
            self.assertEqual(verdict["src_modules"], 3)
            self.assertEqual(verdict["passed"]["reference"], "6/6")

    def test_prefix_merged_multi_turn_packing_and_compaction_split(self):
        # Monotonic turns 0 -> 1 -> 2, then turn 3 rewrites prefix (compaction)
        turns = [
            {"aux": False, "capture_ok": True,
             "prompt_token_ids": [10, 11, 12], "completion_token_ids": [20, 21], "per_token_logps": [-0.1, -0.2]},
            {"aux": True, "capture_ok": True,  # auxiliary title call must be skipped
             "prompt_token_ids": [99], "completion_token_ids": [98], "per_token_logps": [-0.5]},
            {"aux": False, "capture_ok": True,
             "prompt_token_ids": [10, 11, 12, 20, 21, 30, 31], "completion_token_ids": [40, 41, 42],
             "per_token_logps": [-0.3, -0.4, -0.5]},
            {"aux": False, "capture_ok": True,  # rewritten/compacted prefix!
             "prompt_token_ids": [10, 88, 89], "completion_token_ids": [50], "per_token_logps": [-0.6]},
        ]
        segs, st = pack_trajectory_segments(turns, adv=1.5, max_seq=100, enable_merge=True)
        self.assertEqual(st["raw_turns"], 3)
        self.assertEqual(st["segments"], 2)
        self.assertEqual(st["rewrite_splits"], 1)
        self.assertEqual(st["total_tokens"], 6)

        # Segment 0 merges turn 0 + turn 2; tool observation tokens [30, 31] are NOT in target_positions
        s0 = segs[0]
        self.assertEqual(s0["input_ids"], [10, 11, 12, 20, 21, 30, 31, 40, 41, 42])
        self.assertEqual(s0["target_positions"], [2, 3, 6, 7, 8])
        self.assertEqual(s0["target_ids"], [20, 21, 40, 41, 42])
        for p, tid in zip(s0["target_positions"], s0["target_ids"]):
            self.assertEqual(s0["input_ids"][p + 1], tid)

        # Segment 1 holds the post-compaction turn cleanly separated
        s1 = segs[1]
        self.assertEqual(s1["input_ids"], [10, 88, 89, 50])
        self.assertEqual(s1["target_positions"], [2])
        self.assertEqual(s1["target_ids"], [50])

        # With enable_merge=False, each valid turn stays an independent segment
        segs_unmerged, st_u = pack_trajectory_segments(turns, adv=1.5, max_seq=100, enable_merge=False)
        self.assertEqual(len(segs_unmerged), 3)
        self.assertEqual(st_u["total_tokens"], 6)

    def test_dual_harness_prepare_opencode_and_pi(self):
        with tempfile.TemporaryDirectory(prefix="oca-h-") as tmp:
            h_oc = get_harness("opencode")
            cmd_oc, env_oc = h_oc.prepare(Path(tmp) / "oc", "http://127.0.0.1:8100/t/x/v1", "/bin/opencode", "fix", CONFIG)
            self.assertEqual(h_oc.aux_mode, "no_tools")
            self.assertIn("OPENCODE_CONFIG_CONTENT", env_oc)
            self.assertEqual(cmd_oc[0], "/bin/opencode")

            h_pi = get_harness("pi")
            pi_home = Path(tmp) / "pi"
            cmd_pi, env_pi = h_pi.prepare(pi_home, "http://127.0.0.1:8100/t/x/v1", "/bin/pi", "fix", CONFIG)
            self.assertEqual(h_pi.aux_mode, "none")
            self.assertIn("--mode", cmd_pi)
            mfile = pi_home / ".pi" / "agent" / "models.json"
            self.assertTrue(mfile.is_file())
            doc = json.loads(mfile.read_text(encoding="utf-8"))
            self.assertEqual(doc["providers"]["local"]["baseUrl"], "http://127.0.0.1:8100/t/x/v1")

    def test_adversarial_suite_blocks_all_10_attacks(self):
        rep = run_adversarial_suite()
        self.assertEqual(rep["n_attacks"], 10)
        self.assertTrue(rep["all_blocked"], rep)

        # Regression: legitimate grid variable `nc` and 2-level repo pytest paths must NOT false-positive
        from oca.adversarial import _fake_bash_turn
        from oca.reward import hack_flags
        with tempfile.TemporaryDirectory(prefix="oca-fp-") as tmp:
            w = Path(tmp)
            (w / "TASK.md").write_text("ok\n", encoding="utf-8")
            (w / "solution.py").write_text("x = 1\n", encoding="utf-8")
            orig = {"TASK.md": "ok\n", "solution.py": "x = 1\n"}
            benign_turns = [
                _fake_bash_turn('python3 -c "nr, nc = len(grid), len(grid[0]); print(nc)"'),
                _fake_bash_turn("cd src/pkg && PYTHONPATH=.. python -m pytest ../../tests/test_smoke.py"),
            ]
            self.assertEqual(hack_flags(w, orig, "x = 1\n", turns=benign_turns), [])
            evil_turns = [_fake_bash_turn("nc -vz 10.0.0.1 443")]
            self.assertIn("bash_network_attempt", hack_flags(w, orig, "x = 1\n", turns=evil_turns))

    def test_proxy_capture_and_budget(self):
        asyncio.run(proxy_selftest())

    def test_reward_modes_and_efficiency(self):
        cfg = json.loads(json.dumps(CONFIG))
        cfg["train"]["efficiency_weight"] = 0.1
        cfg["train"]["efficiency_budget"] = 10
        rew_fast, parts_fast = compute_reward({"status": "pass", "passed": 8, "total": 8},
                                              [{"call_index": 0}, {"call_index": 1}], [], cfg)
        rew_slow, _ = compute_reward({"status": "pass", "passed": 8, "total": 8},
                                     [{"call_index": i} for i in range(9)], [], cfg)
        self.assertGreater(rew_fast, rew_slow)
        self.assertAlmostEqual(parts_fast["efficiency"], 0.08)

        rew_hack, parts_hack = compute_reward({"status": "pass", "passed": 8, "total": 8},
                                              [{"call_index": 0}], ["bash_probe_grader"], cfg)
        self.assertEqual(rew_hack, 0.0)
        self.assertTrue(parts_hack["hack_zeroed"])

    def test_eval_statistics_permutation_and_by_kind(self):
        self.assertAlmostEqual(exact_mcnemar_p(10, 0), 2 * (0.5 ** 10), places=6)
        self.assertAlmostEqual(paired_permutation_p([0.5, 0.5, 0.5, 0.5, 0.5, 0.5]), 2 * (0.5 ** 6), places=5)
        self.assertEqual(paired_permutation_p([0.0, 0.0]), 1.0)
        self.assertAlmostEqual(pass_at_k_unbiased(4, 2, 1), 0.5)
        self.assertEqual(pass_at_k_unbiased(4, 1, 4), 1.0)

        base = [
            {"task_id": "t1", "kind": "single_file", "seed": 1, "grade": {"status": "fail", "passed": 2, "total": 6},
             "completion_tokens": 500, "n_policy_turns": 4, "tool_calls": ["read", "edit"], "turns": []},
            {"task_id": "t2", "kind": "repo_pytest", "seed": 1, "grade": {"status": "pass", "passed": 6, "total": 6},
             "completion_tokens": 600, "n_policy_turns": 5, "tool_calls": ["read", "edit", "shell"], "turns": []},
        ]
        lora = [
            {"task_id": "t1", "kind": "single_file", "seed": 1, "grade": {"status": "pass", "passed": 6, "total": 6},
             "completion_tokens": 300, "n_policy_turns": 2, "tool_calls": ["read", "edit"], "turns": []},
            {"task_id": "t2", "kind": "repo_pytest", "seed": 1, "grade": {"status": "pass", "passed": 6, "total": 6},
             "completion_tokens": 360, "n_policy_turns": 3, "tool_calls": ["read", "edit"], "turns": []},
        ]
        self.assertEqual(classify_trial(base[0]), "partial_edge_case_miss")
        self.assertEqual(classify_trial(lora[0]), "solved")
        comp = compare_arms(base, lora, [1])
        self.assertEqual(comp["delta_pass_at_1_pp"], 50.0)
        self.assertEqual(comp["common_solved_efficiency"]["token_reduction_pct"], 40.0)
        self.assertIn("repo_pytest", comp["by_kind"])
        self.assertIn("task_level_permutation_p", comp)

    def test_svg_plots_render(self):
        with tempfile.TemporaryDirectory(prefix="oca-plot-") as tmp:
            p = Path(tmp)
            hist = p / "history.jsonl"
            hist.write_text(
                json.dumps({"step": 1, "pass_rate": 0.35, "logprob_err_hist": {"0.0-0.02": 90, "0.5-1.0": 2}}) + "\n"
                + json.dumps({"step": 2, "pass_rate": 0.55, "logprob_err_hist": {"0.0-0.02": 95, "0.5-1.0": 1}}) + "\n",
                encoding="utf-8",
            )
            ev = p / "eval.json"
            ev.write_text(json.dumps({
                "comparisons": {"lora-s40": {
                    "base": {"failure_taxonomy": {"solved": 20, "wrong_logic": 20}},
                    "lora": {"failure_taxonomy": {"solved": 32, "wrong_logic": 8}},
                }}
            }), encoding="utf-8")
            mx = p / "matrix.json"
            mx.write_text(json.dumps({
                "harnesses": ["OpenCode", "Pi"],
                "models": [
                    {"name": "Base", "scores": [0.20, 0.18]},
                    {"name": "Super-Adapter", "scores": [0.58, 0.54]},
                ],
            }), encoding="utf-8")
            render_training_curve(hist, p / "curve.svg")
            render_logprob_hist(hist, p / "div.svg")
            render_failure_taxonomy(ev, p / "tax.svg")
            render_transfer_matrix(mx, p / "mx.svg")
            self.assertTrue((p / "curve.svg").is_file())
            self.assertTrue((p / "div.svg").is_file())
            self.assertTrue((p / "tax.svg").is_file())
            self.assertTrue((p / "mx.svg").is_file())


if __name__ == "__main__":
    unittest.main()
