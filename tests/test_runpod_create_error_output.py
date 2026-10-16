#!/usr/bin/env python3
"""Offline contract for the embedded RunPod Pod-create response parser."""
import pathlib
import subprocess
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
source=(ROOT/"bin/qwen38fast").read_text()
head='        "${options[@]}" 2>&1 | python3 -c '+chr(39)
assert source.count(head)==1
program=source.split(head,1)[1].split("\n"+chr(39)+"\n}\n\ncold_mark pod_create_request",1)[0]
assert "sys.exit(75 if kind" in program

def parse(text):
    return subprocess.run(["python3","-c",program],input=text,text=True,capture_output=True,timeout=8)

class RunPodErrorPresentationTests(unittest.TestCase):
    def test_success_never_repeats_wrapper_notices(self):
        output=("rp: no server-side termination timer\n"
                "rp: local reaper may enforce one-hour limit\n"
                '{"id":"pod-ci"}')
        result=parse(output)
        self.assertEqual(result.returncode,0)
        self.assertEqual(result.stdout.strip(),"pod-ci")
        self.assertEqual(result.stderr,"")

    def test_template_missing_no_retry_and_no_secrets(self):
        secret="SENTINEL_SECRET_TOKEN_HF_TOKEN_DO_NOT_LEAK"
        output=("rp: first wrapper notice\nrp: second wrapper notice\n"
              '{"error":"template not found: abcdef '+secret+'","code":"not_found"}')
        result=parse(output)
        self.assertEqual(result.returncode,65)
        self.assertIn("template_missing",result.stderr)
        self.assertIn("not_found",result.stderr)
        self.assertNotIn(secret,result.stderr)
        self.assertNotIn("wrapper notice",result.stderr)
        self.assertEqual(result.stdout,"")

    def test_gpu_stock_is_only_retryable_type(self):
        cases=[
            ('{"error":"No GPUs available for this instance type"}',75,"gpu_capacity"),
            ('{"error":"requested GPU is currently unavailable"}',75,"gpu_capacity"),
            ('{"error":"insufficient account balance"}',65,"billing"),
            ('{"error":"API unauthorized"}',65,"authentication"),
            ('{"error":"invalid GPU id"}',65,"configuration"),
            ('{"error":"confidential diagnostic: SENTINEL_SECRET"}',65,"unknown"),
            ('{"errors":[{"message":"out of GPU stock"}]}',75,"gpu_capacity"),
        ]
        for body,code,kind in cases:
            with self.subTest(body=body):
                result=parse(body)
                self.assertEqual(result.returncode,code)
                self.assertIn(kind,result.stderr)
                self.assertNotIn("SENTINEL_SECRET",result.stderr)

    def test_unstructured_response_is_not_retried(self):
        result=parse("rp: first\nrp: second\ninternal failure\n")
        self.assertEqual(result.returncode,65)
        self.assertIn("no structured API response",result.stderr)
        self.assertNotIn("rp:",result.stderr)

if __name__=="__main__":
    unittest.main()
