"""Offline safety/telemetry contract tests for the detached Cloudzy builder."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "cloudzy" / "observer.py"
spec = importlib.util.spec_from_file_location("cloudzy_image_observer", SCRIPT)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class CloudzyObserverTests(unittest.TestCase):
    def test_snapshots_read_metrics_without_disclosing_logs(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "buildkit.log"
            log.write_text("SECRET=do-not-copy\n#42 [runtime 1/9] RUN true\n", encoding="utf-8")
            with mock.patch.object(observer.Path, "read_text",
                                   return_value="MemTotal: 67108864 kB\nMemAvailable: 33554432 kB\n"):
                with mock.patch.object(observer.shutil, "disk_usage",
                                       return_value=mock.Mock(total=1500*observer.GIB,
                                                              used=200*observer.GIB,
                                                              free=1300*observer.GIB)):
                    snap = observer.snapshot(log)
            self.assertEqual(snap["buildkit_step_id"], 42)
            self.assertEqual(snap["ram_total_gib"], 64)
            self.assertEqual(snap["ram_used_gib"], 32)
            self.assertEqual(snap["ram_available_gib"], 32)
            self.assertEqual(snap["ssd_free_gib"], 1300)
            self.assertNotIn("do-not-copy", json.dumps(snap))

    def test_unknown_buildkit_step(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(observer.Path, "read_text",
                                   return_value="MemTotal: 67108864 kB\nMemAvailable: 33554432 kB\n"):
                with mock.patch.object(observer.shutil, "disk_usage",
                                       return_value=mock.Mock(total=100*observer.GIB,
                                                              used=5*observer.GIB,
                                                              free=95*observer.GIB)):
                    self.assertIsNone(observer.snapshot(Path(td) / "missing.log")["buildkit_step_id"])

    def test_signals_only_process_group_leader(self):
        with mock.patch.object(observer.os, "getpgid", return_value=987):
            with mock.patch.object(observer.os, "killpg") as signal_group:
                observer.guarded_stop(988)
                signal_group.assert_not_called()


if __name__ == "__main__":
    unittest.main()
