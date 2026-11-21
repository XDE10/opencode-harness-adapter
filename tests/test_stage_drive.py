from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from colab import stage_drive as stage


class DriveStageTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.cache, self.writer, self.reader = (self.root / name for name in ("cache", "writer", "reader"))
        for path in (self.cache, self.writer, self.reader):
            path.mkdir()
        self.version = "fixture-v1"
        self.version_dir = Path(stage.PREFIX) / self.version
        self.files = {"snapshot/weights.bin": b"alpha", "tools/dependency.whl": b"beta"}
        self.rows = []
        for name, data in self.files.items():
            local = self.cache / name
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)
            self.rows.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        self.ready = stage.marker_bytes("a" * 64, "fixture", self.rows)
        self.operations = []
        self.replace_path = Path.replace
        self.check_hash = stage.check_hash

    def mirrored_replace(self, part, final):
        result = self.replace_path(part, final)
        relative = final.relative_to(self.writer)
        other = self.reader / relative
        other.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(final, other)
        self.operations.append(("write", relative.name))
        return result

    def recorded_hash(self, path, row, deadline):
        self.check_hash(path, row, deadline)
        if path.is_relative_to(self.reader):
            self.operations.append(("readback", path.name))

    def publish(self, *, free=10**9, on_file=lambda _name: None, check=lambda: None):
        return stage.publish_cache(self.cache, self.writer, self.reader, self.version, self.rows,
                                   self.ready, free, check, time.monotonic() + 5,
                                   readback_seconds=0.02, on_file=on_file)

    def assert_gate(self, gate, function, *args, **kwargs):
        with self.assertRaises(stage.Rejected) as exc:
            function(*args, **kwargs)
        self.assertEqual(exc.exception.gate, gate)

    def test_resume_keeps_verified_file_and_ready_is_last(self):
        def interrupt(_):
            raise InterruptedError("fixture interruption")

        with patch.object(Path, "replace", lambda part, final: self.mirrored_replace(part, final)), \
                patch.object(stage, "check_hash", self.recorded_hash):
            with self.assertRaises(InterruptedError):
                self.publish(on_file=interrupt)
            first = self.writer / self.version_dir / self.rows[0]["path"]
            inode = first.stat().st_ino
            self.assertFalse((self.reader / self.version_dir / stage.MARKER).exists())
            self.assertFalse(any(self.writer.rglob("*.part")))
            (self.cache / self.rows[0]["path"]).unlink()
            self.assertEqual(self.publish()["reused"], 1)
            self.assertEqual(first.stat().st_ino, inode)
            self.assertEqual((self.reader / self.version_dir / stage.MARKER).read_bytes(), self.ready)
            self.assertEqual(self.operations, [
                ("write", "weights.bin"), ("readback", "weights.bin"), ("readback", "weights.bin"),
                ("write", "dependency.whl"), ("readback", "dependency.whl"), ("write", "READY"),
                ("readback", "READY"),
            ])
            self.operations.clear()
            result = self.publish(free=0)
            self.assertEqual((result["reused"], result["uploaded"]), (2, 0))
            self.assertTrue(all(operation == "readback" for operation, _ in self.operations))

    def test_wrong_local_hash_and_free_space_leave_drive_empty(self):
        self.assert_gate("space", self.publish, free=1)
        self.assertEqual(list(self.writer.iterdir()), [])
        (self.cache / self.rows[1]["path"]).write_bytes(b"fake")
        self.assert_gate("integrity", self.publish)
        self.assertEqual(list(self.writer.iterdir()), [])

    def test_wrong_provider_checksum_and_stale_view_never_write_ready(self):
        def corrupt(part, final):
            result = self.mirrored_replace(part, final)
            remote = self.reader / final.relative_to(self.writer)
            remote.write_bytes(b"!" * remote.stat().st_size)
            return result

        with patch.object(Path, "replace", corrupt):
            self.assert_gate("integrity", self.publish)
        self.assertFalse((self.writer / self.version_dir / stage.MARKER).exists())
        for path in self.reader.rglob("*.bin"):
            path.unlink()
        self.assert_gate("drive_readback", self.publish)

    def test_existing_wrong_ready_is_protected(self):
        marker = self.reader / self.version_dir / stage.MARKER
        marker.parent.mkdir(parents=True)
        marker.write_text("wrong lock")
        self.assert_gate("ready", self.publish)
        self.assertEqual(list(self.writer.iterdir()), [])

    def test_wrong_account_mount_and_root_attestation(self):
        writer = stage.Mount(str(self.writer), "100", "0:100", "fuse.rclone", "z:", False)
        reader = stage.Mount(str(self.reader), "101", "0:101", "fuse.rclone", "z:", True)
        proof = {"schema_version": 1, "owner_id": "verified-z", "private": True,
                 "drive_root_id": "z-root", "read_drive_root_id": "z-root", "uncached_readback": True,
                 "available_bytes": 999, "write_mount": asdict(writer), "read_mount": asdict(reader)}
        self.assertEqual(stage.validate_owner(proof, "verified-z", writer, reader), 999)
        self.assert_gate("owner", stage.validate_owner, proof, "wrong", writer, reader)
        self.assert_gate("owner", stage.validate_owner,
                         {**proof, "read_drive_root_id": "other-drive"}, "verified-z", writer, reader)
        self.assert_gate("mount", stage.validate_owner, proof, "verified-z", writer, replace(reader, mount_id="102"))
        mountinfo = f"100 40 0:100 / {self.writer} rw - fuse.rclone z: rw\n"
        self.assertEqual(stage.read_mount(self.writer, mountinfo), writer)
        self.assert_gate("mount", stage.read_mount, self.writer / "missing", mountinfo)
        self.assert_gate("mount", stage.read_mount, self.writer, mountinfo.replace("fuse.rclone", "ext4"))
        receipt = self.root / "scheduler.json"
        receipt.write_text(json.dumps(proof))
        argv = ["stage_drive", "--write-mount", str(self.writer), "--read-mount", str(self.reader),
                "--owner-proof", str(receipt), "--expected-owner", "wrong-account",
                "--local-cache", str(self.root / "uncreated")]
        with patch.object(stage, "read_mount", side_effect=[writer, reader]), \
                patch("sys.argv", argv), patch.object(stage, "publish_cache") as publish:
            self.assert_gate("owner", stage.main)
            publish.assert_not_called()
        self.assertFalse((self.root / "uncreated").exists())
        self.assertEqual(list(self.writer.iterdir()), [])

    def test_mount_change_stops_before_file_mutation(self):
        path = self.writer / self.version_dir
        guard = Mock(side_effect=[None, stage.Rejected("mount", "mount detached")])
        self.assert_gate("mount", self.publish, check=guard)
        self.assertFalse(path.exists())

    def test_public_local_download_resumes_partial_and_checks_sha(self):
        row = {**self.rows[0], "url": "https://huggingface.co/fixture"}
        final = self.cache / row["path"]
        final.unlink()
        partial = final.with_name(f".{final.name}.part")
        partial.write_bytes(b"al")

        def fake_curl(argv, *, env, **_):
            self.assertNotIn("HTTPS_PROXY", env)
            self.assertNotIn("HF_TOKEN", env)
            self.assertIn("--continue-at", argv)
            self.assertEqual(argv[argv.index("--continue-at") + 1], "-")
            self.assertEqual(partial.read_bytes(), b"al")
            with partial.open("ab") as out:
                out.write(b"pha")
            child = Mock(returncode=0)
            child.communicate.return_value = (None, "")
            child.poll.return_value = 0
            return child

        with patch.dict(stage.os.environ, {"HTTPS_PROXY": "http://example.invalid", "HF_TOKEN": "fixture"}), \
                patch("colab.native_colab.subprocess.Popen", side_effect=fake_curl):
            stage.prepare_public(self.cache, [row], None, self.root, time.monotonic() + 5)
        self.assertEqual(final.read_bytes(), b"alpha")
        self.assertFalse(partial.exists())
        self.assertEqual(list(self.writer.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
