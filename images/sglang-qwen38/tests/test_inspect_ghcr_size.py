"""Unit tests: private GHCR checker never needs a live token in CI."""
import importlib.util
import unittest
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / "tools/inspect-registry.py"
spec = importlib.util.spec_from_file_location("qwen38_ghcr_inspect", FILE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class GhcrInspectionTests(unittest.TestCase):
    def test_exact_single_platform_layer_bytes(self):
        doc = {"layers": [
            {"size": 8_000_000_000, "digest": "sha256:" + "a" * 64},
            {"size": 2_000_000_000, "digest": "sha256:" + "b" * 64}
        ]}
        self.assertEqual(mod.measure(doc)[0], 10_000_000_000)

    def test_select_only_linux_amd64(self):
        doc = {"manifests": [
            {"digest": "sha256:" + "1" * 64, "platform": {"os": "linux", "architecture": "arm64"}},
            {"digest": "sha256:" + "2" * 64, "platform": {"os": "linux", "architecture": "amd64"}},
            {"digest": "sha256:" + "3" * 64, "platform": {"os": "unknown", "architecture": "unknown"}}
        ]}
        self.assertEqual(mod.measure(doc), "sha256:" + "2" * 64)

    def test_refuse_ambiguous_arch(self):
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            mod.measure({"manifests": [
                {"digest": "sha256:" + "1" * 64, "platform": {"os": "linux", "architecture": "amd64"}},
                {"digest": "sha256:" + "2" * 64, "platform": {"os": "linux", "architecture": "amd64"}}
            ]})

    def test_reject_bad_digests_before_auth_request(self):
        with self.assertRaisesRegex(RuntimeError, "Unexpected digest"):
            mod.retrieve_manifest("not-a-digest", "test-token")
        with self.assertRaisesRegex(RuntimeError, "Malformed"):
            mod.retrieve_manifest("sha256:" + "g" * 64, "test-token")

    def test_no_empty_manifest(self):
        with self.assertRaisesRegex(RuntimeError, "no compressed"):
            mod.measure({"layers": []})


if __name__ == "__main__":
    unittest.main()

class RegistryRedirectTests(unittest.TestCase):
    def test_head_redirect_preserves_method_and_drops_auth(self):
        req = mod.urllib.request.Request('https://ghcr.io/v2/example/blobs/sha256:abc',
                                        headers={'Authorization':'Bearer fake'}, method='HEAD')
        redirected = mod.BlobRedirect().redirect_request(req, None, 307, 'redirect', {},
                        'https://pkg-containers.githubusercontent.com/blob')
        self.assertEqual(redirected.get_method(), 'HEAD')
        self.assertIsNone(redirected.get_header('Authorization'))

    def test_unknown_or_plaintext_redirect_is_rejected(self):
        req = mod.urllib.request.Request('https://ghcr.io/token')
        for target in ('https://attacker.example/blob', 'http://pkg-containers.githubusercontent.com/blob'):
            with self.assertRaises(RuntimeError):
                mod.BlobRedirect().redirect_request(req, None, 307, '', {}, target)
