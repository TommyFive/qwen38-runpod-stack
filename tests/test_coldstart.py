#!/usr/bin/env python3
"""Offline regression tests: no pod/GPU, HF download or RunPod credentials required."""
import json
import pathlib
import runpy
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "qwen38cold"
LIB = runpy.run_path(str(SCRIPT))


def marker(event, utc, mono, secret=None):
    payload = {"schema": 1, "event": event, "utc": utc, "mono": mono}
    if secret:
        payload["HF_TOKEN"] = secret
    return "noise\nQWEN38_COLDSTART " + json.dumps(payload) + "\n"


class ColdstartTests(unittest.TestCase):
    def test_durations_and_ttf_inference_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            host = root / "host.log"
            pod = root / "bootstrap.log"
            host.write_text(
                marker("pod_create_request", "2026-10-09T15:00:00Z", 100) +
                marker("pod_created", "2026-10-09T15:00:05Z", 105) +
                marker("api_models_ready", "2026-10-09T15:06:00Z", 460) +
                marker("first_inference_ok", "2026-10-09T15:06:50Z", 510,
                       secret="HUGGING_FACE_TOKEN_NEVER_EMIT"))
            pod.write_text(
                marker("bootstrap_start", "2026-10-09T15:03:00Z", 1000) +
                marker("network_probe_start", "2026-10-09T15:03:01Z", 1001) +
                marker("network_probe_end", "2026-10-09T15:03:03Z", 1003) +
                marker("main_download_start", "2026-10-09T15:03:04Z", 1004) +
                marker("main_download_end", "2026-10-09T15:04:44Z", 1104))
            platform = root / "platform.json"
            platform.write_text(json.dumps({
                "scheduling_start": "2026-10-09T15:00:06Z",
                "image_pull_start": "2026-10-09T15:00:15Z",
                "image_pull_end": "2026-10-09T15:02:50Z",
                "container_started": "2026-10-09T15:02:59Z",
                "target_weights_start": "2026-10-09T15:04:50Z",
                "target_weights_end": "2026-10-09T15:04:55Z"
            }))
            out = root / "sample.json"
            cmd = [sys.executable, str(SCRIPT), "report", "--host", str(host),
                   "--bootstrap", str(pod), "--platform", str(platform),
                   "--cloud", "community", "--region", "EU-RO-1",
                   "--output", str(out)]
            subprocess.run(cmd, check=True)
            result = json.loads(out.read_text())
            self.assertEqual(result["durations_sec"]["ttfi_sec"], 410)
            self.assertEqual(result["durations_sec"]["api_ready_since_create_sec"], 360)
            self.assertEqual(result["durations_sec"]["hf_main_download_sec"], 100)
            self.assertEqual(result["durations_sec"]["image_pull_sec"], 155)
            self.assertEqual(result["durations_sec"]["target_weights_sec"], 5)
            self.assertIsNone(result["durations_sec"]["draft_weights_sec"])
            self.assertNotIn("HUGGING_FACE_TOKEN_NEVER_EMIT", out.read_text())
            self.assertEqual(result["metadata"]["region"], "EU-RO-1")
            summary = subprocess.run([sys.executable, str(SCRIPT), "summary",
                                      str(out)], capture_output=True, text=True, check=True)
            self.assertIn("410.0", summary.stdout)
            self.assertIn("exploratory (N<5)", summary.stdout)

    def test_models_ready_is_not_inference(self):
        indexed = {
            "pod_create_request": {"event": "pod_create_request", "utc": LIB["parse_utc"]("2026-10-10T00:00:00Z"), "mono": 1, "source": "host"},
            "api_models_ready": {"event": "api_models_ready", "utc": LIB["parse_utc"]("2026-10-10T00:04:00Z"), "mono": 241, "source": "host"},
        }
        report = LIB["build_report"](indexed, {})
        self.assertEqual(report["durations_sec"]["api_ready_since_create_sec"], 240)
        self.assertIsNone(report["durations_sec"]["ttfi_sec"])
        self.assertTrue(any("TTFI is unknown" in w for w in report["warnings"]))

    def test_reject_bad_or_naive_timestamps(self):
        for value in ("2026-10-09T15:00:00", "not a date"):
            with self.assertRaises(ValueError):
                LIB["parse_utc"](value)

    def test_monotonic_preferred_over_host_clock_jump(self):
        a = {"source": "pod", "mono": 10, "utc": LIB["parse_utc"]("2026-10-10T10:00:00Z")}
        b = {"source": "pod", "mono": 20, "utc": LIB["parse_utc"]("2026-10-10T09:00:00Z")}
        self.assertEqual(LIB["elapsed"](a, b), 10)
        a["source"] = "platform"
        self.assertIsNone(LIB["elapsed"](a, b))

    def test_p95_nearest_rank(self):
        self.assertEqual(LIB["percentile95"]([1, 2, 3, 4, 5]), 5)
        self.assertEqual(LIB["percentile95"](list(range(1, 21))), 19)

    def test_unsupported_platform_event_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            data = pathlib.Path(directory) / "platform.json"
            data.write_text('{"HF_TOKEN": "SECRET"}')
            with self.assertRaises(ValueError):
                LIB["load_platform"](data)

    def test_shell_instrumentation_is_opt_out_and_nonintrusive(self):
        bootstrap = (ROOT / "scripts/bootstrap-sglang-openwebui.sh").read_text()
        launcher = (ROOT / "bin/qwen38fast").read_text()
        template = (ROOT / "create-templates.sh").read_text()
        self.assertIn("cold_mark health_generate_ready", bootstrap)
        self.assertIn("cold_mark main_download_end", bootstrap)
        self.assertIn("cold_mark first_inference_ok", launcher)
        self.assertIn('"COLDSTART_TRACE": sys.argv[25]', launcher)
        self.assertIn('"COLDSTART_TRACE":"1"', template)
        self.assertIn("QWEN38_COLDSTART_TRACE:-1", launcher)
        # No change to serving / speculative decoding flags is needed to measure.
        self.assertIn("--speculative-algorithm DFLASH", bootstrap)


if __name__ == "__main__":
    unittest.main()
