import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from agent import pilot_endpoint
from preflight import validate_models
from protocol import PROTOCOL, ROOT, verify_fixtures
from report import save_json, write_report
from run import base_record


class PreflightTests(unittest.TestCase):
    def validate(self, entries, **extra):
        return validate_models(json.dumps({"data": entries, **extra}).encode(), "declared", "rev1")

    def test_matching_identity_distinguishes_revision_attestation(self):
        self.assertEqual(self.validate([{"id": "declared"}])["revision_source"], "operator_declared")
        reported = self.validate([{"id": "declared", "revision": "rev1"}])
        self.assertEqual(reported["revision_source"], "server_reported_match")
        self.assertFalse(reported["weight_identity_verified"])

    def test_rejects_bad_model_identity(self):
        for entries, message in [
            ([{"id": "other"}], "exactly one"),
            ([{"id": "declared"}, {"id": "declared"}], "exactly one"),
            ([{"id": "declared", "revision": "rev2"}], "revision differs"),
        ]:
            with self.subTest(entries=entries), self.assertRaisesRegex(ValueError, message):
                self.validate(entries)

    def test_rejects_mock_even_when_model_id_matches(self):
        with self.assertRaisesRegex(ValueError, "scripted mock"):
            self.validate([{"id": "declared", "revision": "rev1"}],
                          harness_adapter_source="scripted_mock")

    def test_requires_isolated_container_before_probe(self):
        docker = Mock()
        docker.invoke.return_value = (None, 0, "id true bridge sha256:image\n", "")
        with self.assertRaisesRegex(RuntimeError, "--network none"):
            pilot_endpoint(docker, "name", "declared", 8000, "rev1")
        self.assertEqual(docker.invoke.call_count, 1)
        self.assertFalse(docker.sandbox.called)

    def test_model_listing_bound(self):
        with self.assertRaisesRegex(ValueError, "128 KiB"):
            validate_models(b" " * (128 * 1024 + 1), "declared", "rev1")


class ProtocolAndReportTests(unittest.TestCase):
    def test_fixture_changes_fail_before_a_run(self):
        verify_fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for fixture in PROTOCOL["fixture_sha256"]:
                dest = root / fixture
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes((ROOT / fixture).read_bytes())
            path = "tasks/boundary/solution.py"
            (root / path).write_text("# drift\n")
            with self.assertRaisesRegex(RuntimeError, path):
                verify_fixtures(root)

    def test_report_keeps_mock_counts_and_unscored_attempts_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            histories = [
                ("scripted_mock", "pass", {"status": "pass"}),
                ("operator_endpoint", "test_timeout", {"status": "test_timeout"}),
            ]
            records = []
            for source, status, grade in histories:
                folder = root / source
                folder.mkdir()
                record = base_record("boundary", "check", 0, provenance=source)
                record.update(status=status, grade=grade, wall_seconds=1, completion_requests=4)
                relative = f"{source}/record.json"
                save_json(root / relative, record)
                records.append(relative)
            write_report(root, records, mode="cpu_acceptance")
            output = json.loads((root / "trajectory-report.json").read_text())
            mock, timeout = output["attempts"]
            self.assertEqual(mock["mock_http_completion_requests"], 4)
            self.assertEqual(mock["correctness_reward"], 1)
            self.assertIsNone(timeout["mock_http_completion_requests"])
            self.assertIsNone(timeout["correctness_reward"])
            for attempt in (mock, timeout):
                self.assertIsNone(attempt["model_calls"])
                self.assertFalse(attempt["training_trajectory"]["usable_for_grpo"])
