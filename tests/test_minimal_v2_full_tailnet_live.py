"""Offline-only Full Tailnet / blocking server benchmark acceptance tests.

Never contacts RunPod or starts a GPU. Mainline startup remains unchanged.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
GEN=ROOT/"images"/"sglang-qwen38"/"create-minimal-v2-full-tailnet-live.sh"
BOOT=ROOT/"scripts"/"bootstrap-sglang-openwebui.sh"


def fake_report(n=5):
    return {"status":"completed","completed_utc":"2026-10-12T00:00:00Z",
            "workloads":[{"id":name,"measurements":[{
                "token_count_source":"server_usage","completion_tokens":512,
                "ttft_seconds":0.05,"decode_tokens_per_second":150.0
            } for _ in range(n)]} for name in ("technical","code","code_edit")]}


def gate(report,n=5):
    bootstrap=BOOT.read_text()
    match=re.search(r"<<'BENCH_GATE'\n(?P<code>[\s\S]*?)\nBENCH_GATE\n",bootstrap)
    assert match, "The blocking report gate must exist"
    with tempfile.TemporaryDirectory() as d:
        report_path=Path(d)/"report.json"
        report_path.write_text(json.dumps(report))
        return subprocess.run([sys.executable,"-c",match.group("code"),
                               str(report_path),str(n)],
                               capture_output=True,text=True,timeout=8)


class FullTailnetLiveTests(unittest.TestCase):
    def test_generator_and_bootstrap_syntax(self):
        for file in (GEN,BOOT):
            result=subprocess.run(["bash","-n",str(file)],
                                  capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_dry_run_is_offline_and_b_image_is_pinned(self):
        env=dict(os.environ)
        env["QWEN38_RUNPODCTL"]="/definitely/nonexistent"
        p=subprocess.run(["bash",str(GEN),"--candidate=b"],env=env,
                         capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn("DRY RUN",p.stdout)
        self.assertIn("sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7",p.stdout)
        self.assertIn("full-tailnet",p.stdout)
        self.assertIn("BENCHMARK_BLOCKING=1",p.stdout)
        self.assertIn("No public ports",p.stdout)
        self.assertNotIn("RUNPOD_API_KEY",p.stdout)
        name=re.search(r"GPU live Full Tailnet template: (\\S+)",p.stdout)
        self.assertIsNotNone(name)
        self.assertLess(len(name.group(1)),50,"RunPod UI requires strictly fewer than 50 characters")
        self.assertEqual(name.group(1),"qwen38-gpulive-261012-v2b-full-tailnet-b5-debug")

    def test_other_images_are_pinned_and_separate(self):
        for name,sha in (
          ("a","ec013c2e20528a92d61b6a7a0352ba081e166ef99025a5fbb4be06572381bb1e"),
          ("v1","1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd"),
        ):
            p=subprocess.run(["bash",str(GEN),"--candidate="+name],
                             capture_output=True,text=True,timeout=20)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertIn("sha256:"+sha,p.stdout)
            name_match=re.search(r"GPU live Full Tailnet template: (\\S+)",p.stdout)
            self.assertIsNotNone(name_match)
            self.assertLess(len(name_match.group(1)),50)
            self.assertIn("-"+name+"-" if name=="v1" else "-v2a-",name_match.group(1))

    def test_fail_closed_invalid_disk_and_secrets(self):
        env=dict(os.environ,QWEN38_LIVE_DISK_GB="10")
        p=subprocess.run(["bash",str(GEN)],env=env,capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
        self.assertIn("20..150",p.stderr)
        env=dict(os.environ,QWEN38_LIVE_WEBUI_PASSWORD_SECRET="LLAMA_API_KEY")
        p=subprocess.run(["bash",str(GEN)],env=env,capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
        self.assertIn("separate",p.stderr)

    def test_gate_accepts_three_full_workloads(self):
        p=gate(fake_report())
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn("BENCHMARK_GATE_VERIFIED workloads=3 runs_per_workload=5",p.stdout)

    def test_gate_rejects_partial_workload(self):
        d=fake_report()
        d["workloads"][1]["measurements"].pop()
        p=gate(d)
        self.assertNotEqual(p.returncode,0)
        self.assertIn("measurement count mismatch",p.stderr)

    def test_gate_rejects_missing_server_usage_and_nonfinite_numbers(self):
        for field,value in (("token_count_source","unavailable"),
                            ("decode_tokens_per_second",float("nan")),
                            ("ttft_seconds",0)):
            d=fake_report()
            d["workloads"][2]["measurements"][0][field]=value
            p=gate(d)
            self.assertNotEqual(p.returncode,0,(field,p.stdout,p.stderr))

    def test_blocking_gate_precedes_full_webui_launch(self):
        s=BOOT.read_text()
        self.assertLess(s.index("QWEN38_BENCHMARK_GATE status=started"),
                        s.index('if [[ "$SERVE_WEBUI" == 1 ]]; then\n  # Public OpenWebUI'))
        self.assertIn('if [[ "$BENCHMARK" == 1 && "$BENCHMARK_BLOCKING" == 0 ]]',s)
        self.assertIn('BENCHMARK_BLOCKING requires BENCHMARK=1',s)

    def test_no_pod_create_in_generator(self):
        s=GEN.read_text()
        self.assertNotIn("pod create",s)
        self.assertNotIn("pod delete",s)
        self.assertIn('template create',s)
        self.assertIn('template update',s)
        self.assertIn('repair "$ID"',s)
        self.assertIn('RUNPOD_SECRET_',s)
        self.assertNotIn('PUBLIC_KEY',s)
        self.assertIn('if (( ${#NAME} >= 50 ))',s)


if __name__=="__main__":
    unittest.main()
