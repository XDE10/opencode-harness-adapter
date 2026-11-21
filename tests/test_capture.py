import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from capture.engine_budget import EngineBudget, validate_engine_logps
from capture.relay import MODEL, StreamInterrupted, encode_event, read_stream
from capture.seal import FILES, SOURCE, save, seal, verify
from colab.first_batch import MANIFESTS, verify_batch
from colab.contracts import ROOT


class CaptureTests(unittest.TestCase):
    def test_engine_wire_rejects_shifted_or_unlabeled_logprobs(self):
        choice = {"token_ids": [42, 43], "logprobs": {"content": [
            {"token": "token_id:42", "logprob": -0.1},
            {"token": "token_id:43", "logprob": -0.2},
        ]}}
        payload = {"model": "locked", "prompt_token_ids": [40, 41], "choices": [choice]}
        validate_engine_logps(payload, "locked")
        with self.assertRaisesRegex(ValueError, "identity"):
            validate_engine_logps(payload, "different")
        for bad in ("token_id:43", "unlabeled text"):
            choice["logprobs"]["content"][0]["token"] = bad
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "logprobs"):
                validate_engine_logps(payload, "locked")

    def test_engine_budget_clamps_by_request_and_remaining_tokens(self):
        budget = EngineBudget(max_calls=12, per_call=512, per_trial=2048)
        body = {"stream": False, "max_completion_tokens": 500, "max_tokens": 700}
        self.assertEqual(budget.admit(body), {"stream": False, "max_tokens": 500})
        budget.settle({"choices": [{"token_ids": [42] * 500}], "usage": {"completion_tokens": 500}})
        for cap in (512, 512, 512, 12):
            self.assertEqual(budget.admit({"stream": False})["max_tokens"], cap)
            budget.settle({"choices": [{"token_ids": [42] * cap}], "usage": {"completion_tokens": cap}})
        with self.assertRaisesRegex(ValueError, "budget exhausted"):
            budget.admit({"stream": False})
        self.assertEqual(budget.output_tokens, 2048)

    def test_engine_budget_does_not_allow_in_flight_or_extra_requests(self):
        budget = EngineBudget(max_calls=1, per_call=512, per_trial=2048)
        budget.admit({"stream": False})
        with self.assertRaisesRegex(ValueError, "in flight"):
            budget.admit({"stream": False})
        budget.settle({"choices": [{"token_ids": [42]}], "usage": {"completion_tokens": 1}})
        with self.assertRaisesRegex(ValueError, "budget exhausted"):
            budget.admit({"stream": False})
        self.assertEqual(budget.sent_limits, [512])

    def test_invalid_engine_usage_locks_trial(self):
        for response in ({}, {"choices": [{"token_ids": [42]}], "usage": {"completion_tokens": 2}},
                         {"choices": [{"token_ids": [42, 43]}], "usage": {"completion_tokens": 2}}):
            with self.subTest(response=response):
                budget = EngineBudget(max_calls=12, per_call=1, per_trial=2)
                budget.admit({"stream": False})
                with self.assertRaisesRegex(ValueError, "token accounting failed"):
                    budget.settle(response)
                with self.assertRaisesRegex(ValueError, "trial is stopped"):
                    budget.admit({"stream": False})
                self.assertEqual(budget.sent_limits, [1])

    def test_v2_keeps_v1_and_uses_distinct_repositories(self):
        original = verify_batch(version=1)["tasks"]
        current = verify_batch()["tasks"]
        self.assertEqual(len({task["repo"] for task in current}), 10)
        self.assertEqual([sum(task["split"] == split for task in current)
                          for split in ("train", "heldout")], [6, 4])
        by_id = {task["id"]: task for task in current}
        self.assertEqual([by_id[task["id"]] for task in original], original)

    def test_v3_keeps_v2_and_disjoins_twelve_repositories_per_split(self):
        previous = verify_batch(version=2)["tasks"]
        current = verify_batch(version=3)["tasks"]
        by_id = {task["id"]: task for task in current}
        self.assertEqual([by_id[task["id"]] for task in previous], previous)
        train, heldout = ({task["repo"] for task in current if task["split"] == split}
                          for split in ("train", "heldout"))
        self.assertEqual((len(train), len(heldout)), (12, 12))
        self.assertFalse(train & heldout)
        self.assertTrue({task["id"] for task in current}.isdisjoint(("boundary", "parsing", "serialization")))

    def test_v3_rejects_shared_repo_and_unbound_snapshot_revisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "first-batch-v3.json"
            for changed_key, bad_value, error in (
                ("repo", "oca-fixtures/ledger-table", "at most one task per repository"),
                ("revision", "0" * 64, "revision differs from its snapshot"),
            ):
                manifest = verify_batch(version=3)
                heldout = next(task for task in manifest["tasks"] if task["id"] == "capped-wait-series")
                heldout[changed_key] = bad_value
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.subTest(changed_key=changed_key), patch.dict(MANIFESTS, {3: path}):
                    with self.assertRaisesRegex(ValueError, error):
                        verify_batch(version=3)

    def test_finished_frame_without_terminal_marker_still_needs_retry(self):
        frame = encode_event({"id": "one", "model": MODEL, "choices": [{"finish_reason": "stop"}]})
        with self.assertRaisesRegex(StreamInterrupted, "before"):
            read_stream(io.BytesIO(frame))
        with self.assertRaisesRegex(ValueError, "missing finish frame or engine capture"):
            read_stream(io.BytesIO(frame + encode_event("[DONE]")))

    def test_seal_detects_tampering_and_keeps_synthetic_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in FILES:
                (folder / name).write_text("some fixture evidence")
            save(folder / "trace.json", {"source": SOURCE, "usable_for_grpo": False})
            seal(folder)
            self.assertFalse(verify(folder)["trainable"])
            (folder / "final.patch").write_text("changed")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                verify(folder)
            save(folder / "trace.json", {"source": "openenv_engine", "usable_for_grpo": True})
            seal(folder)
            with self.assertRaisesRegex(ValueError, "unexpected trace provenance"):
                verify(folder)

    def test_batch_lock_rejects_fixture_drift(self):
        manifest = verify_batch()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for task in manifest["tasks"]:
                for file in task["files"]:
                    dest = root / file
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / file, dest)
            one = next(iter(manifest["tasks"][0]["files"]))
            (root / one).write_text("new candidate")
            with self.assertRaisesRegex(ValueError, "frozen task changed"):
                verify_batch(root)
