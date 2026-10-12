"""Offline regression: anonymous GHCR visibility & exact image manifest pin."""
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

CHECKER = Path(__file__).resolve().parents[1] / "tools/check-public.py"
spec = importlib.util.spec_from_file_location("ghcr_public_check", CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PublicPullCheckTests(unittest.TestCase):
    def setUp(self):
        self.blob = json.dumps({"schemaVersion": 2, "layers": [
            {"digest": "sha256:" + "a" * 64, "size": 1} for _ in range(8)
        ]}).encode()
        self.expected = "sha256:" + hashlib.sha256(self.blob).hexdigest()

    def test_exact_digest_anonymous_pull(self):
        calls = []

        def fake_get(uri, headers=None):
            calls.append((uri, headers))
            if uri.startswith("https://ghcr.io/token?"):
                return json.dumps({"token": "public-anonymous-token"}).encode(), {}
            self.assertEqual(headers["Authorization"], "Bearer public-anonymous-token")
            self.assertIn(self.expected, uri)
            return self.blob, {"Docker-Content-Digest": self.expected}

        with patch.object(checker, "PINNED", self.expected), patch.object(checker, "get_json", fake_get):
            self.assertEqual(checker.verify_anonymous(), 8)
        self.assertEqual(len(calls), 2)

    def test_wrong_manifest_rejected(self):
        with patch.object(checker, "get_json", side_effect=[
            (b'{"token":"public-anonymous-token"}', {}),
            (self.blob, {"Docker-Content-Digest": self.expected})
        ]):
            with self.assertRaisesRegex(RuntimeError, "different manifest"):
                checker.verify_anonymous()

    def test_private_package_no_anonymous_pull(self):
        with patch.object(checker, "get_json", side_effect=[
            (b'{"token":"token"}', {}),
            PermissionError("Forbidden")
        ]):
            with self.assertRaises(PermissionError):
                checker.verify_anonymous()

    def test_reject_wrong_layer_count(self):
        short = json.dumps({"layers": [{"size": 100}]}).encode()
        digest = "sha256:" + hashlib.sha256(short).hexdigest()
        with patch.object(checker, "PINNED", digest), patch.object(checker, "get_json", side_effect=[
            (b'{"token":"public-token"}', {}),
            (short, {"Docker-Content-Digest": digest})
        ]):
            with self.assertRaisesRegex(RuntimeError, "8-layer"):
                checker.verify_anonymous()


if __name__ == "__main__":
    unittest.main()
