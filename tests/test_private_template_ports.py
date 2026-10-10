"""Fail-closed RunPod template hardening tests; all API calls mocked."""
import importlib.util
import io
import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/private-template-ports.py"
spec = importlib.util.spec_from_file_location("private_template_ports", SCRIPT)
ports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ports)


def template(items=None, mode="tailnet"):
    return {"id": "abc123", "ports": ["8888/http", "22/tcp"] if items is None else items,
            "env": {"NETWORK_MODE": mode, "BOOTSTRAP_B64": "fake",
                    "TAILSCALE_RUNTIME_B64": "fake"}}


class FakeResponse:
    def __init__(self, obj):
        self.data = json.dumps(obj).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, count=-1):
        return self.data


class PortsTests(unittest.TestCase):
    def test_repair_explicit_empty_ports_and_recheck(self):
        state = template()
        methods = []
        def mock_urlopen(request, timeout):
            methods.append(request.get_method())
            if request.get_method() == "PATCH":
                self.assertEqual(json.loads(request.data), {"ports": []})
                state["ports"] = []
            return FakeResponse(state)
        with patch.dict(os.environ, {"RUNPOD_API_KEY": "test-key"}), patch.object(
                ports.urllib.request, "urlopen", side_effect=mock_urlopen), patch("sys.stdout", new=io.StringIO()):
            ports.repair("abc123")
        self.assertEqual(methods, ["GET", "PATCH", "GET"])

    def test_backend_ignores_empty_ports_fail_closed(self):
        with patch.object(ports, "request", side_effect=[template(), {}, template()]):
            with self.assertRaisesRegex(ports.PortSafetyError, "public RunPod ports"):
                ports.repair("abc123")

    def test_private_validation_rejects_unknown_and_public(self):
        for t in (template(["8888/http"]), template(mode="runpod"),
                  template([]) | {"ports": None}):
            with self.subTest(t=t), self.assertRaises(ports.PortSafetyError):
                ports.validate(t, "abc123")

    def test_missing_ports_represents_empty_in_runpod_rest_json(self):
        t = template([])
        del t["ports"]
        ports.validate(t, "abc123")
        with patch.object(ports, "request", side_effect=[t, {}, t]) as req:
            with patch("sys.stdout", new=io.StringIO()):
                ports.repair("abc123")
        self.assertEqual(req.call_count, 3)

    def test_secret_reference_allowed_but_plaintext_rejected(self):
        t = template([])
        t["env"]["SGLANG_API_KEY"] = "{{ RUNPOD_SECRET_LLAMA_API_KEY }}"
        t["env"]["TS_AUTHKEY"] = "{{ RUNPOD_SECRET_TS_AUTHKEY }}"
        t["env"]["HF_TOKEN"] = "{{ RUNPOD_SECRET_CUSTOM_HF }}"
        ports.validate(t, "abc123")
        t["env"]["TS_AUTHKEY"] = "tskey-plaintext-not-real"
        with self.assertRaisesRegex(ports.PortSafetyError, "plaintext"):
            ports.validate(t, "abc123")

    def test_unknown_secret_rejected(self):
        t = template([])
        t["env"]["TS_AUTHKEY"] = "test-do-not-log"
        with self.assertRaisesRegex(ports.PortSafetyError, "plaintext"):
            ports.validate(t, "abc123")

    def test_requests_use_browser_compatible_user_agent(self):
        observed = []
        def mock_urlopen(req, timeout):
            observed.append((req.get_method(), req.get_header("User-agent")))
            return FakeResponse(template([]))
        with patch.dict(os.environ, {"RUNPOD_API_KEY": "test-key"}), patch.object(
                ports.urllib.request, "urlopen", side_effect=mock_urlopen):
            ports.request("GET", "abc123")
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0][0], "GET")
        self.assertTrue(observed[0][1].startswith("Mozilla/5.0"))
        self.assertNotIn("Python-urllib", observed[0][1])

    def test_native_config_fallback_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = Path(directory) / "config.toml"
            cfg.write_text('apiKey = "runpod-ci-test-only"\\n')
            cfg.chmod(0o600)
            with patch.dict(os.environ, {"RUNPOD_API_KEY": ""}):
                self.assertEqual(ports.runpod_api_key(cfg), "runpod-ci-test-only")
                cfg.chmod(0o644)
                with self.assertRaisesRegex(ports.PortSafetyError, "permissions unsafe"):
                    ports.runpod_api_key(cfg)

    def test_environment_key_takes_precedence(self):
        with patch.dict(os.environ, {"RUNPOD_API_KEY": "runpod-env-ci"}):
            self.assertEqual(ports.runpod_api_key(Path("/nonexistent")), "runpod-env-ci")

    def test_missing_key_denies_without_network(self):
        with patch.dict(os.environ, {"RUNPOD_API_KEY": ""}), \\
             patch.object(ports, "runpod_api_key", side_effect=ports.PortSafetyError("absent")):
            with self.assertRaises(ports.PortSafetyError):
                ports.request("GET", "abc123")

    def test_cleanup_on_failed_patch(self):
        with patch.object(ports, "repair", side_effect=ports.PortSafetyError("not allowed")), \
             patch.object(ports, "request", return_value={}) as request_mock, \
             patch("sys.stderr", new=io.StringIO()), \
             patch("sys.argv", ["script", "repair", "abc123", "--delete-on-failure"]):
            self.assertEqual(ports.main(), 1)
            request_mock.assert_called_once_with("DELETE", "abc123")


if __name__ == "__main__":
    unittest.main()
