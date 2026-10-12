"""Offline-only tests for qwen38bench's private Tailnet HTTPS mode."""
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout, redirect_stderr

SCRIPT=Path(__file__).resolve().parents[1]/"bin"/"qwen38bench"
loader=importlib.machinery.SourceFileLoader("bench_tailnet",str(SCRIPT))
spec=importlib.util.spec_from_loader(loader.name,loader)
mod=importlib.util.module_from_spec(spec)
loader.exec_module(mod)

class MockModels:
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def read(self,*_):return json.dumps({"data":[{"id":"test-model"}]}).encode()

def mock_run(*args,**kwargs):
    return {"tps":150.0,"ttft":0.03,"total":3.2,"out_tokens":512,
            "prompt_tokens":8192,"token_count_source":"server_usage"}

class TailnetBenchmarkTests(unittest.TestCase):
    def test_direct_tailnet_never_uses_runpod_public_proxy(self):
        with tempfile.TemporaryDirectory() as td:
            key=Path(td)/"key";key.write_text("only-test-token")
            with mock.patch.object(sys,"argv",[
                "qwen38bench","--api-base","https://pod.tailnet.ts.net/v1",
                "--key-file",str(key),"--runs","2"]),\
                mock.patch.object(mod,"running_pod",side_effect=AssertionError("public proxy")),\
                mock.patch.object(mod,"get",return_value=MockModels()) as get,\
                mock.patch.object(mod,"one_run",side_effect=mock_run) as run,\
                redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(mod.main(),0)
            self.assertEqual(get.call_args[0][0],"https://pod.tailnet.ts.net/v1/models")
            self.assertIn("tailnet-only",stdout.getvalue())
            self.assertEqual(run.call_count,3) # discarded warmup + 2 runs

    def test_rejects_public_and_unsafe_urls(self):
        with tempfile.TemporaryDirectory() as td:
            key=Path(td)/"key";key.write_text("only-test-token")
            urls=["http://pod.tailnet.ts.net/v1",
                  "https://example.com/v1",
                  "https://pod.tailnet.ts.net:8080/v1",
                  "https://user:password@pod.tailnet.ts.net/v1",
                  "https://pod.tailnet.ts.net/v1?api_key=x",
                  "https://pod.tailnet.ts.net/v2"]
            for url in urls:
                with self.subTest(url=url),mock.patch.object(sys,"argv",[
                    "qwen38bench","--api-base",url,"--key-file",str(key)]),\
                     redirect_stderr(io.StringIO()),\
                     self.assertRaises(SystemExit):
                    mod.main()

    def test_private_mode_requires_matching_key_file(self):
        with mock.patch.object(sys,"argv",["qwen38bench","--api-base",
             "https://pod.tailnet.ts.net/v1","--key-file","/does/not/exist"]),\
             redirect_stderr(io.StringIO()),\
             self.assertRaises(SystemExit):
            mod.main()

if __name__=="__main__": unittest.main()
