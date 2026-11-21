import hashlib
import json
from concurrent.futures import Future
from itertools import count
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from colab import native_colab as job


class NativeJobTests(unittest.TestCase):
    def assert_gate(self, gate, func, *args):
        with self.assertRaises(job.Rejected) as error:
            func(*args)
        self.assertEqual(error.exception.gate, gate)

    def test_device_gates(self):
        valid = "NVIDIA RTX PRO 6000 Blackwell, 12.0, 98304, 8, 590.55"
        job.device_check(valid, "", 90_000_000_000)
        for report, active, gate in [
            ("", "", "gpu"), (valid + "\n" + valid, "", "gpu"), ("garbled", "", "gpu"),
            (valid.replace("Blackwell", "Ada"), "", "gpu"), (valid.replace("12.0", "8.9"), "", "gpu"),
            (valid.replace("98304", "49152"), "", "gpu"), (valid.replace("590.55", "550.1"), "", "driver"),
            (valid.replace(", 8,", ", 4096,"), "", "gpu_busy"), (valid, "1234", "gpu_busy"),
        ]:
            with self.subTest(report=report, active=active):
                self.assert_gate(gate, job.device_check, report, active, 90_000_000_000)

    def test_host_and_mount_gates(self):
        with patch.object(job.platform, "machine", return_value="aarch64"):
            self.assert_gate("host", job.host_check)
        fake = "3 2 0:2 / / rw - overlay overlay rw\n4 3 0:4 / /content/drive rw - fuse.drive drive rw\n"
        with patch.object(Path, "read_text", return_value=fake):
            job.local_storage(Path("/content/cache"))
            self.assert_gate("local_cache", job.local_storage, Path("/content/drive/MyDrive/cache"))

    def test_cache_missing_size_hash_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            row = {"path": "file", "bytes": 4, "sha256": hashlib.sha256(b"safe").hexdigest()}
            deadline = time.monotonic() + 2
            self.assert_gate("cache", job.check_cache, home, [row], deadline)
            (home / "file").write_bytes(b"few")
            self.assert_gate("cache", job.check_cache, home, [row], deadline)
            (home / "file").write_bytes(b"fail")
            self.assert_gate("integrity", job.check_cache, home, [row], deadline)
            (home / "file").write_bytes(b"safe")
            job.check_cache(home, [row], deadline)
            (home / "alias").symlink_to("file")
            self.assert_gate("cache", job.check_cache, home, [{**row, "path": "alias"}], deadline)

    def test_every_failed_preparation_blocks_install_or_launch(self):
        ordered = ["host_check", "local_storage", "eligible_gpu", "disk_usage", "check_daemon",
                   "check_cache", "prove_docker", "install_software", "command", "trial"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for fail, gate in zip(ordered[:-1], ["host", "local_cache", "gpu", "disk", "docker",
                                                "cache", "isolation", "install", "cuda"]):
                with self.subTest(fail=fail), unittest.mock.patch.multiple(
                        job, **{name: Mock() for name in ordered if name != "disk_usage"}):
                    stage = root / fail
                    stage.mkdir()
                    job.install_software.return_value = (Path("/test/python"), Path("/test/vllm"))
                    job.check_daemon.return_value = ["docker"]
                    free = Mock(free=0 if fail == "disk_usage" else 10 ** 12)
                    if fail != "disk_usage":
                        getattr(job, fail).side_effect = job.Rejected(gate, gate)
                    with patch.object(job.shutil, "disk_usage", return_value=free):
                        self.assert_gate(gate, job.run_prepared, root, root, stage,
                                         {"minimum_vram_bytes": 90, "files": [], "docker": {"image_id": "pinned"}},
                                         time.monotonic() + 4)
                    job.trial.assert_not_called()
                    if ordered.index(fail) < ordered.index("install_software"):
                        job.install_software.assert_not_called()

    def test_docker_load_identity_and_functional_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            image = {"image_id": "sha256:approved", "path": "image.tar"}
            with patch.object(job, "command", side_effect=["", "sha256:other linux amd64"]):
                self.assert_gate("docker_image", job.prove_docker, ["docker"], home, home, image, 1, {})
            with patch.object(job, "command", side_effect=[
                    "", "sha256:approved linux amd64", job.Rejected("isolation", "no IPC namespace")]) as call:
                self.assert_gate("isolation", job.prove_docker, ["docker"], home, home, image, 1, {})
                argv = call.call_args.args[0]
                self.assertIn("--pull=never", argv)
                self.assertIn("--network=none", argv)

    def test_public_source_timeout_rate_and_offline_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            row = {"path": "file", "bytes": 4, "sha256": "unused", "url": "https://private.invalid/file"}
            with patch.object(job.subprocess, "Popen") as start:
                self.assert_gate("public_source", job.fetch_one, home, row, time.monotonic() + 2, {})
                start.assert_not_called()
            self.assertFalse(job.transfer_guard(200, 10, 19))
            self.assertFalse(job.transfer_guard(200, 0, 20))
            self.assertTrue(job.transfer_guard(200, 10, 20))
            self.assertTrue(job.transfer_guard(0, 0, 0))
            self.assert_gate("preparation_timeout", job.seconds_left, lambda: time.monotonic() - 1)
            with patch.dict(job.os.environ, {"HF_TOKEN": "fixture", "HTTPS_PROXY": "http://example.invalid"}):
                self.assertNotIn("HF_TOKEN", job.trusted_env(home))
                self.assertNotIn("HTTPS_PROXY", job.trusted_env(home))

    def test_public_download_stops_and_cancels_on_insufficient_rate(self):
        row = {"path": "large", "bytes": 800_000, "sha256": "unused", "url": "https://huggingface.co/file"}
        ticks = count(0, 50)
        pending = Future()
        pool = Mock()
        pool.submit.return_value = pending
        factory = unittest.mock.MagicMock()
        factory.return_value.__enter__.return_value = pool
        with tempfile.TemporaryDirectory() as tmp, patch.object(job, "ThreadPoolExecutor", factory), \
                patch.object(job.time, "monotonic", side_effect=lambda: next(ticks)):
            self.assert_gate("public_throughput", job.fetch_public, Path(tmp), [row], 480, Path(tmp))
        self.assertTrue(pending.cancelled())

    def test_success_dispatches_exactly_one_locked_trial_without_fetching(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(job, "host_check"), patch.object(job, "local_storage"), \
                    patch.object(job, "eligible_gpu"), patch.object(job.shutil, "disk_usage", return_value=Mock(free=10**12)), \
                    patch.object(job, "check_daemon", return_value=["docker"]), patch.object(job, "check_cache"), \
                    patch.object(job, "prove_docker"), patch.object(job, "command"), \
                    patch.object(job, "install_software", return_value=(root/"python", root/"vllm")), \
                    patch.object(job, "fetch_public") as fetch, patch.object(job, "trial") as launch:
                job.run_prepared(root, root, root, {"minimum_vram_bytes": 90, "files": [],
                                 "docker": {"image_id": "pinned"}}, time.monotonic() + 4)
            fetch.assert_not_called()
            launch.assert_called_once()
            args = launch.call_args.args[0]
            self.assertEqual(args, [str(root/"python"), "-u", "-m", "colab.g4_first", str(root/"snapshot"),
                                    str(root/"trial"), "--vllm", str(root/"vllm"), "--allow-existing-g4"])

    def test_command_nonzero_missing_timeout_and_trial_kill(self):
        deadline = time.monotonic() + 2
        self.assert_gate("docker", job.command, ["/no-such-command"], deadline, {}, "docker")
        self.assert_gate("install", job.command, [sys.executable, "-c", "raise SystemExit(7)"],
                         deadline, {}, "install")
        self.assert_gate("docker", job.command, [sys.executable, "-c", "import time;time.sleep(1)"],
                         deadline, {}, "docker", 0.02)
        with tempfile.TemporaryDirectory() as tmp:
            process = Mock(pid=9999)
            process.wait.side_effect = [subprocess.TimeoutExpired("trial", 1),
                                        subprocess.TimeoutExpired("trial", 18), -9]
            with patch.object(job.subprocess, "Popen", return_value=process), patch.object(job.os, "killpg") as kill:
                self.assert_gate("trial_timeout", job.trial, [sys.executable], {}, Path(tmp), deadline)
            self.assertEqual([item.args[1] for item in kill.call_args_list], [job.signal.SIGINT, job.signal.SIGKILL])

    def test_manifest_matches_locked_model_and_image(self):
        root = Path(__file__).resolve().parents[1]
        current = json.loads((root / "protocol/native-colab-cache.json").read_text())
        model = json.loads((root / "protocol/colab-g4-v1.json").read_text())["model"]
        self.assertEqual((current["model_id"], current["model_revision"]), (model["id"], model["revision"]))
        self.assertEqual({r["path"].split("/", 1)[1]: r["sha256"] for r in current["files"]
                          if r["path"].startswith("snapshot/")}, model["files"])
        self.assertEqual(len({r["path"] for r in current["files"]}), 356)
        self.assertEqual(current["docker"]["registry_ref"],
                         json.loads((root / "protocol/cpu-v1.json").read_text())["image"])


if __name__ == "__main__":
    unittest.main()
