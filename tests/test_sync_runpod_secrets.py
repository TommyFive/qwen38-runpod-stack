"""Offline unit tests for safe RunPod template Secret migration."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "scripts/sync-runpod-secrets.py"
spec = importlib.util.spec_from_file_location("sync_runpod_secrets", PATH)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def stub(mode="tailnet"):
    return {
        "id": "abc123",
        "ports": ["8888/http"] if mode == "tailnet" else ["8000/http"],
        "env": {"NETWORK_MODE": mode, "BOOTSTRAP_B64": "mock",
                "TAILSCALE_RUNTIME_B64": "mock", "MODEL_ID": "example/main"},
    }


class SyncTests(unittest.TestCase):
    def test_secrets_are_only_references(self):
        env = sync.make_env(stub()["env"], "tailnet", "MY_HF")
        self.assertEqual(env["SGLANG_API_KEY"], "{{ RUNPOD_SECRET_LLAMA_API_KEY }}")
        self.assertEqual(env["TS_AUTHKEY"], "{{ RUNPOD_SECRET_TS_AUTHKEY }}")
        self.assertEqual(env["HF_TOKEN"], "{{ RUNPOD_SECRET_MY_HF }}")

    def test_public_omits_tailscale(self):
        env = sync.make_env(stub("runpod")["env"], "runpod", "")
        self.assertNotIn("TS_AUTHKEY", env)
        self.assertNotIn("HF_TOKEN", env)
        self.assertIn("SGLANG_API_KEY", env)

    def test_reject_malformed_hf_name(self):
        with self.assertRaises(sync.ports.PortSafetyError):
            sync.make_env(stub()["env"], "tailnet", "FOO }} injection")

    def test_never_copy_existing_webui_password(self):
        e = stub()["env"]
        e["WEBUI_ADMIN_PASSWORD"] = "unsafe-old-value"
        with self.assertRaises(sync.ports.PortSafetyError):
            sync.make_env(e, "tailnet", "")

    def test_migration_uses_hf_token_secret_by_default(self):
        import io
        import os
        import sys
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(sys, "argv", ["sync", "--public-full", "pubfull",
                  "--public-lean", "publean", "--private-full", "privfull",
                  "--private-lean", "privlean"]), \
             patch.object(sync, "sync") as update, \
             patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(sync.main(), 0)
        self.assertEqual(update.call_count, 4)
        self.assertTrue(all(call.args[2] == "HF_TOKEN" for call in update.call_args_list))

    def test_explicit_empty_hf_name_skips_optional_secret(self):
        import io
        import os
        import sys
        with patch.dict(os.environ, {"QWEN38_HF_SECRET_NAME": ""}, clear=True), \
             patch.object(sys, "argv", ["sync", "--public-full", "pubfull",
                  "--public-lean", "publean", "--private-full", "privfull",
                  "--private-lean", "privlean"]), \
             patch.object(sync, "sync") as update, \
             patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(sync.main(), 0)
        self.assertTrue(all(call.args[2] == "" for call in update.call_args_list))

    def test_repair_private_in_place_no_pod_create(self):
        state = stub()
        calls = []
        def request(method, template_id, payload=None):
            calls.append((method, payload))
            if method == "PATCH":
                state.update(payload)
            return dict(state)
        with patch.object(sync.ports, "request", side_effect=request), \
             patch.object(sync.ports, "repair") as repair:
            sync.sync("abc123", "tailnet", "HF_TOKEN")
        repair.assert_called_once_with("abc123")
        self.assertEqual([x[0] for x in calls], ["GET", "PATCH", "GET"])
        self.assertEqual(calls[1][1]["env"]["HF_TOKEN"],
                         "{{ RUNPOD_SECRET_HF_TOKEN }}")

    def test_do_not_update_on_wrong_network_mode(self):
        with patch.object(sync.ports, "request", return_value=stub(mode="runpod")) as req:
            with self.assertRaises(sync.ports.PortSafetyError):
                sync.sync("abc123", "tailnet", "")
            req.assert_called_once()


if __name__ == "__main__":
    unittest.main()
