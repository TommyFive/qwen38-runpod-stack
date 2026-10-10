"""Contract tests: Mac mini reattachment is durable, safe, and no-VM-by-default."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "cloudzy"
MONITOR = MODULE / "monitor-from-mac.sh"
START = MODULE / "start-from-mac.sh"


class CloudzyReattachTests(unittest.TestCase):
    def test_no_registered_server_means_fail_closed_without_ssh(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "HOME": tmp, "PATH": "/usr/bin:/bin"}
            run = subprocess.run(
                ["bash", str(MONITOR), "status"],
                env=env, capture_output=True, text=True, timeout=5, check=False,
            )
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("No registered VM", run.stderr)

    def test_monitor_has_explicit_only_commands_and_pinned_ssh_hostkey(self):
        text = MONITOR.read_text(encoding="utf-8")
        self.assertIn("StrictHostKeyChecking=yes", text)
        self.assertIn('UserKnownHostsFile="$STATE/known_hosts"', text)
        self.assertIn("BatchMode=yes", text)
        self.assertIn("RequestTTY=no", text)
        self.assertIn("current-ip", text)
        self.assertIn("current-sha", text)
        self.assertIn("archive", text)
        self.assertIn("resources", text)
        self.assertIn("errors", text)

    def test_bootstrap_is_detached_and_target_persisted_once(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("StrictHostKeyChecking=accept-new", text)
        self.assertIn("systemd-run --unit=qwen38-cloudzy-bootstrap", text)
        self.assertIn('"$STATE/current-ip"', text)
        self.assertIn('"$STATE/current-sha"', text)
        self.assertIn("Existing registered Cloudzy VM", text)

    def test_invalid_monitor_operation_fails_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = subprocess.run(
                ["bash", str(MONITOR), "start"], env={**os.environ, "HOME": tmp},
                capture_output=True, text=True, timeout=5, check=False,
            )
            self.assertEqual(run.returncode, 64)


if __name__ == "__main__":
    unittest.main()
