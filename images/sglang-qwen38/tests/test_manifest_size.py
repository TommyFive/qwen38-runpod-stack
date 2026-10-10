"""Offline tests for OCI compressed-size measurement, including common pitfalls."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("qwen38_manifest_size", ROOT / "manifest-size.py")
manifest_size = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest_size)


class ManifestSizeTests(unittest.TestCase):
    def test_single_platform_accurate_compressed_sum(self):
        doc = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {"size": 2024},
            "layers": [
                {"digest": "sha256:" + "a" * 64, "size": 1_000_000_000},
                {"digest": "sha256:" + "b" * 64, "size": 2_000_000_000},
            ]
        }
        result = manifest_size.summarize(doc)
        self.assertEqual(result["compressed_bytes"], 3_000_000_000)
        self.assertEqual(result["compressed_decimal_gb"], 3.0)
        self.assertEqual(result["layers"], 2)
        self.assertEqual(result["top_layers"][0]["bytes"], 2_000_000_000)
        # Config bytes are metadata and not image layer bytes.
        self.assertNotEqual(result["compressed_bytes"], 3_000_002_024)

    def test_multiarch_index_must_be_resolved(self):
        doc = {"mediaType": "application/vnd.oci.image.index.v1+json",
               "manifests": [
                   {"digest": "sha256:" + "c" * 64,
                    "size": 111,
                    "platform": {"os": "linux", "architecture": "amd64"}},
                   {"digest": "sha256:" + "d" * 64,
                    "size": 222,
                    "platform": {"os": "linux", "architecture": "arm64"}}
               ]}
        with self.assertRaisesRegex(ValueError, "fetch linux/amd64 digest"):
            manifest_size.summarize(doc)

    def test_no_uncompressed_docker_config_allowed(self):
        with self.assertRaisesRegex(ValueError, "nonempty layers"):
            manifest_size.summarize({"config": {"rootfs": {"diff_ids": []}}})

    def test_invalid_layer_rejected(self):
        doc = {"layers": [{"digest": "sha256:" + "a" * 64, "size": -8}]}
        with self.assertRaisesRegex(ValueError, "Negative size"):
            manifest_size.summarize(doc)
        doc["layers"][0]["size"] = 8.5
        with self.assertRaisesRegex(ValueError, "integer byte count"):
            manifest_size.summarize(doc)


if __name__ == "__main__":
    unittest.main()
