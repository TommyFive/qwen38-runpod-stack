"""Offline contract/integration tests for the opt-in SGLang benchmark."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "benchmark_sglang", ROOT / "scripts/benchmark_sglang.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

PAYLOAD_EVENTS = [
    {"choices": [{"delta": {"role": "assistant"}}]},
    {"choices": [{"delta": {"content": ""}}]},
    {"choices": [{"delta": {"reasoning_content": "thinking"}}]},
    {"choices": [{"delta": {"content": "some text"}}]},
    {"choices": [{"delta": {"tool_calls": [{"id": "x"}]}}]},
    {"choices": [{"delta": {"tool_calls": [
        {"function": {"arguments": "{\"a\":1}"}}]}}]},
    {"choices": [], "usage": {"prompt_tokens": 24, "completion_tokens": 27}},
]


def stream_bytes(usage=True, done=True):
    events = PAYLOAD_EVENTS if usage else PAYLOAD_EVENTS[:-1]
    chunks = [":heartbeat\n\n", "data: \n\n"]
    chunks.extend("data: " + json.dumps(e) + "\n\n" for e in events)
    if done:
        chunks.append("data: [DONE]\n\n")
    return "".join(chunks).encode()


class FakeResponse:
    def __init__(self, body):
        self.body = body
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __iter__(self):
        return iter(self.body.splitlines(keepends=True))


class Handler(BaseHTTPRequestHandler):
    hits = 0
    auth = "unit-test-key"

    def log_message(self, *_):
        pass

    def _check_auth(self):
        if self.headers.get("Authorization") != "Bearer " + self.auth:
            self.send_response(401)
            self.end_headers()
            return False
        return True

    def do_GET(self):
        if not self._check_auth():
            return
        if self.path != "/v1/models":
            self.send_error(404)
            return
        body = json.dumps({"data": [{"id": "test-model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self._check_auth():
            return
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        body = self.rfile.read(int(self.headers["Content-Length"]))
        req = json.loads(body)
        assert req["stream"] is True
        assert req["temperature"] == 0
        assert req["stream_options"]["include_usage"] is True
        assert req["chat_template_kwargs"]["enable_thinking"] is False
        assert req["max_tokens"] == 16
        Handler.hits += 1
        payload = stream_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class BenchmarkTests(unittest.TestCase):
    def test_config_and_headers(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(bench.settings()["runs"], 3)
            self.assertNotIn("Authorization", bench.headers())
        with mock.patch.dict(os.environ, {"SGLANG_API_KEY": "secret"}, clear=True):
            self.assertEqual(bench.headers()["Authorization"], "Bearer secret")
        for key, val in (
            ("BENCHMARK_RUNS", "0"), ("BENCHMARK_RUNS", "oops"),
            ("BENCHMARK_MAX_TOKENS", "-1"),
            ("BENCHMARK_TIMEOUT_SECONDS", "7201"),
            ("BENCHMARK_RUNS", "21"),
        ):
            with self.subTest(key=key, val=val), mock.patch.dict(
                    os.environ, {key: val}, clear=True):
                with self.assertRaises(bench.BenchmarkError):
                    bench.settings()

    def test_sse_usage_not_chunk_count_and_reasoning_ttft(self):
        with mock.patch.object(bench, "request", return_value=FakeResponse(stream_bytes())):
            result = bench.one_run("test-model", "hello", 16, time.monotonic() + 5)
        self.assertEqual(result["completion_tokens"], 27)
        self.assertEqual(result["prompt_tokens"], 24)
        self.assertEqual(result["token_count_source"], "server_usage")
        self.assertTrue(result["first_output_observed"])
        self.assertGreaterEqual(result["ttft_seconds"], 0)
        self.assertGreater(result["decode_tokens_per_second"], 0)

    def test_sse_without_usage_does_not_invent_tokens(self):
        with mock.patch.object(bench, "request", return_value=FakeResponse(stream_bytes(usage=False))):
            result = bench.one_run("test-model", "hello", 16, time.monotonic() + 5)
        self.assertIsNone(result["completion_tokens"])
        self.assertIsNone(result["decode_tokens_per_second"])
        self.assertIsNone(result["tpot_seconds"])
        self.assertEqual(result["token_count_source"], "unavailable")

    def test_empty_and_tool_only_sse(self):
        body = b''.join([
            b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n',
            b'data: {"choices":[{"delta":{"tool_calls":[{"id":"x"}]}}]}\n\n',
            b'data: {"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"abc"}}]}}]}\n\n',
            b'data: {"choices":[],"usage":{"completion_tokens":2}}\n\n',
            b'data: [DONE]\n\n',
        ])
        with mock.patch.object(bench, "request", return_value=FakeResponse(body)):
            r = bench.one_run("test-model", "hello", 16, time.monotonic() + 5)
        self.assertTrue(r["first_output_observed"])
        self.assertEqual(r["completion_tokens"], 2)

    def test_incomplete_sse_fails(self):
        with mock.patch.object(bench, "request", return_value=FakeResponse(stream_bytes(done=False))):
            with self.assertRaisesRegex(bench.BenchmarkError, "incomplete"):
                bench.one_run("test-model", "hello", 16, time.monotonic() + 5)

    def test_readiness_retries_and_auth_failure(self):
        outputs = [
            FakeResponse(b'{"data":[]}\n'),
            FakeResponse(b'{"data":[{"id":"model"}]}\n'),
        ]
        with mock.patch.object(bench, "request", side_effect=outputs) as call:
            with mock.patch.object(bench.time, "sleep"):
                self.assertEqual(bench.ready_model(time.monotonic() + 5), "model")
            self.assertEqual(call.call_count, 2)
        with mock.patch.object(bench, "request", side_effect=bench.Unauthorized("unauthorized")):
            with self.assertRaises(bench.Unauthorized):
                bench.ready_model(time.monotonic() + 5)

    def test_deadline(self):
        with self.assertRaises(bench.DeadlineExceeded):
            bench.ready_model(time.monotonic() - 1)
        with self.assertRaises(bench.DeadlineExceeded):
            bench.one_run("test-model", "hello", 16, time.monotonic() - 1)

    def test_full_fake_server_has_exactly_three_workloads(self):
        Handler.hits = 0
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        old_alarm = signal.getsignal(signal.SIGALRM)
        old_term = signal.getsignal(signal.SIGTERM)
        old_int = signal.getsignal(signal.SIGINT)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                report = Path(tmp) / "report.json"
                env = {
                    "SGLANG_API_KEY": Handler.auth, "BENCHMARK_RUNS": "2",
                    "BENCHMARK_MAX_TOKENS": "16",
                    "BENCHMARK_TIMEOUT_SECONDS": "20",
                    "BENCHMARK_REPORT_PATH": str(report),
                    "MODEL_ID": "unit-model", "SPEC": "dflash2",
                }
                with mock.patch.dict(os.environ, env, clear=True):
                    with mock.patch.object(
                        bench, "API", f"http://127.0.0.1:{server.server_port}/v1"):
                        with mock.patch.object(bench, "_gpu_metadata", return_value={}):
                            self.assertEqual(bench.main(), 0)
                raw = report.read_text()
                self.assertNotIn(Handler.auth, raw)
                self.assertNotIn("Write a self-contained", raw)
                obj = json.loads(raw)
                self.assertEqual(obj["status"], "completed")
                self.assertEqual(obj["prompt_set_revision"], bench.PROMPT_SET_REVISION)
                self.assertEqual(Handler.hits, 3 * (1 + 2))
                self.assertEqual([w["id"] for w in obj["workloads"]],
                                 ["technical", "code", "code_edit"])
                self.assertTrue(all(len(w["measurements"]) == 2 for w in obj["workloads"]))
                self.assertTrue(all(w["warmup_excluded"] for w in obj["workloads"]))
                self.assertEqual(report.stat().st_mode & 0o777, 0o600)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_alarm)
            signal.signal(signal.SIGTERM, old_term)
            signal.signal(signal.SIGINT, old_int)
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_worker_sigterm_is_bounded_and_writes_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            env = dict(os.environ, BENCHMARK_RUNS="1",
                       BENCHMARK_MAX_TOKENS="16",
                       BENCHMARK_TIMEOUT_SECONDS="60",
                       BENCHMARK_REPORT_PATH=str(path))
            child = subprocess.Popen(
                [sys.executable, str(ROOT / "scripts/benchmark_sglang.py")],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                time.sleep(0.7)
                self.assertIsNone(child.poll())
                child.terminate()
                self.assertNotEqual(child.wait(timeout=5), 0)
                self.assertEqual(json.loads(path.read_text())["status"], "failed")
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)

    def test_external_headers_and_sse(self):
        spec2 = importlib.util.spec_from_file_location("qwen38bench", ROOT / "bin/qwen38bench")
        # Extensionless script is valid Python, but SourceFileLoader is explicit.
        from importlib.machinery import SourceFileLoader
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(
            "qwen38bench", SourceFileLoader("qwen38bench", str(ROOT / "bin/qwen38bench"))))
        mod.__loader__.exec_module(mod)
        self.assertEqual(mod.api_headers("mykey")["Authorization"], "Bearer mykey")
        self.assertEqual(list(mod.events(FakeResponse(stream_bytes())))[-1], "[DONE]")


if __name__ == "__main__":
    unittest.main()
