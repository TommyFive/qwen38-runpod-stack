#!/usr/bin/env python3
"""Offline tests of qwen38-proxy's HTTPS endpoint selection."""
import importlib.machinery
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def load_proxy():
    source = Path(__file__).resolve().parents[1] / "bin" / "qwen38-proxy"
    loader = importlib.machinery.SourceFileLoader("qwen38_proxy", str(source))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


PROXY = load_proxy()


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.marker = Path(self.tmp.name) / "endpoint.json"
        self.patch = patch.object(PROXY, "ENDPOINT_FILE", self.marker)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_legacy_without_marker(self):
        self.assertEqual(PROXY.upstream_target("my-pod"),
                         ("my-pod-8000.proxy.runpod.net", 443))

    def test_tailnet_endpoint(self):
        self.marker.write_text(json.dumps({
            "pod_id": "test-pod",
            "api_url": "https://qwen38-test.tailc8dece.ts.net/v1",
        }))
        self.assertEqual(PROXY.upstream_target("test-pod"),
                         ("qwen38-test.tailc8dece.ts.net", 443))

    def test_runpod_endpoint(self):
        self.marker.write_text(json.dumps({
            "pod_id": "test-pod",
            "api_url": "https://test-pod-8000.proxy.runpod.net/v1",
        }))
        self.assertEqual(PROXY.upstream_target("test-pod"),
                         ("test-pod-8000.proxy.runpod.net", 443))

    def test_invalid_marker_is_fail_closed(self):
        values = (
            "http://qwen38-test.tailc8dece.ts.net/v1",
            "https://evil.example/v1",
            "https://qwen38-test.tailc8dece.ts.net:8000/v1",
            "https://qwen38-test.tailc8dece.ts.net/other",
            "https://user@qwen38-test.tailc8dece.ts.net/v1",
        )
        for value in values:
            with self.subTest(value=value):
                self.marker.write_text(json.dumps({
                    "pod_id": "test-pod", "api_url": value,
                }))
                with self.assertRaises(ValueError):
                    PROXY.upstream_target("test-pod")

    def test_stale_marker_ignored_for_other_pod(self):
        self.marker.write_text(json.dumps({
            "pod_id": "old-pod",
            "api_url": "https://old-host.tailc8dece.ts.net/v1",
        }))
        self.assertEqual(PROXY.upstream_target("new-pod"),
                         ("new-pod-8000.proxy.runpod.net", 443))


if __name__ == "__main__":
    unittest.main()
