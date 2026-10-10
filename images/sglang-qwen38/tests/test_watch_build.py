"""Offline checks: safety boundaries for the hosted-runner telemetry watchdog."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "watch-build.py"
spec = importlib.util.spec_from_file_location("watch_build", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class WatchdogTests(unittest.TestCase):
    def test_resource_snapshot_is_numeric_and_scrubs_build_content(self):
        with tempfile.TemporaryDirectory() as work:
            log = Path(work) / "build.log"
            log.write_text(
                "Authorization: Bearer secret-token\n"
                "#21 [stage 2/3] RUN echo secret-password\n"
                "private/path model-sensitive\n"
                "#42 DONE 9.0s\n",
                encoding="utf-8",
            )
            self.assertEqual(mod.last_buildkit_step(log), 42)
            data = {
                "time_utc": "2026-10-10 11:59:00 UTC",
                "disk_free_gib": 55.1,
                "disk_used_gib": 70.0,
                "disk_total_gib": 125.1,
                "disk_used_percent": 56.0,
                "mem_available_gib": 7.2,
                "mem_used_gib": 8.8,
                "mem_total_gib": 16.0,
                "mem_used_percent": 55.0,
                "elapsed_seconds": 1800,
                "cgroup_oom_kill": 0,
                "buildkit_step_number": 42,
                "build_log_bytes": log.stat().st_size,
            }
            comment = mod.make_comment(data, 38042274792, "building")
            self.assertIn("SSD used: **70.00 / 125.10 GiB** (56.0 %), free: **55.10 GiB**", comment)
            self.assertIn("RAM used: **8.80 / 16.00 GiB** (55.0 %), available: **7.20 GiB**", comment)
            self.assertIn("Build elapsed: **30 min 00 s**", comment)
            self.assertIn("Last BuildKit step ID: 42", comment)
            self.assertIn("https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38042274792", comment)
            for secret in ("secret-token", "secret-password", "model-sensitive", "Authorization:"):
                self.assertNotIn(secret, comment)

    def test_adaptive_pr_heartbeat_switches_after_30_minutes(self):
        due = mod.should_publish
        self.assertTrue(due(0, None))
        self.assertFalse(due(1790, 50))
        self.assertFalse(due(1799, 119))
        self.assertTrue(due(1799, 120))
        self.assertFalse(due(1800, 29))
        self.assertTrue(due(1800, 30))
        self.assertFalse(due(1850, 15))
        self.assertTrue(due(1850, 30))

    def test_snapshot_contains_used_and_free_resource_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "build.log"
            log.write_text("#30 DONE 5.0s\n")
            with mock.patch.object(mod.shutil, "disk_usage", return_value=mock.Mock(total=128 * mod.GIB, used=78 * mod.GIB, free=50 * mod.GIB)):
                with mock.patch.object(mod, "memory_bytes", return_value=(16 * mod.GIB, 6 * mod.GIB)):
                    snap = mod.snapshot(log, tmp)
            self.assertEqual(snap["disk_used_gib"], 78.0)
            self.assertEqual(snap["disk_free_gib"], 50.0)
            self.assertEqual(snap["disk_used_percent"], 60.9)
            self.assertEqual(snap["mem_used_gib"], 10.0)
            self.assertEqual(snap["mem_available_gib"], 6.0)
            self.assertEqual(snap["mem_used_percent"], 62.5)

    def test_missing_files_do_not_crash_sample_helpers(self):
        self.assertIsNone(mod.mem_available_bytes("/missing/this-file"))
        self.assertIsNone(mod.oom_kills("/missing/this-file"))
        self.assertIsNone(mod.last_buildkit_step("/missing/this-file"))

    def test_memory_and_cgroup_parsing(self):
        with tempfile.TemporaryDirectory() as work:
            mem = Path(work) / "meminfo"
            oom = Path(work) / "events"
            mem.write_text("MemTotal: 16000000 kB\nMemAvailable: 12345 kB\n")
            oom.write_text("low 0\noom_kill 3\n")
            self.assertEqual(mod.mem_available_bytes(mem), 12345 * 1024)
            self.assertEqual(mod.memory_bytes(mem), (16000000 * 1024, 12345 * 1024))
            self.assertEqual(mod.oom_kills(oom), 3)

    def test_no_external_comment_without_explicit_token(self):
        with mock.patch.dict("os.environ", {"GH_TOKEN": ""}):
            with mock.patch.object(mod.urllib.request, "urlopen") as request:
                self.assertIsNone(mod.github_comment("no secrets here"))
                request.assert_not_called()

    def test_memory_pressure_stops_before_99_percent_usage(self):
        severe, count = mod.memory_critical(2.33, 0)
        self.assertTrue(severe)
        self.assertEqual(count, 1)
        severe, count = mod.memory_critical(3.0, 0)
        self.assertFalse(severe)
        self.assertEqual(count, 0)
        severe, count = mod.memory_critical(1.12, 0)
        self.assertTrue(severe)
        self.assertEqual(count, 1)
        severe, count = mod.memory_critical(2.0, 0)
        self.assertFalse(severe)
        self.assertEqual(count, 1)
        severe, count = mod.memory_critical(2.0, count)
        self.assertTrue(severe)
        self.assertEqual(count, 2)
        severe, count = mod.memory_critical(None, 1)
        self.assertFalse(severe)
        self.assertEqual(count, 0)

    def test_never_kill_an_unisolated_process_group(self):
        with mock.patch.object(mod.os, "getpgid", return_value=4711):
            with mock.patch.object(mod.os, "killpg") as kill:
                mod.stop_build(4712, "low RAM")
                kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
