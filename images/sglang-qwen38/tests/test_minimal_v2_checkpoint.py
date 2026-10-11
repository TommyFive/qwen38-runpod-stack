"""Offline, no-VPS integrity contract for the archived minimal-v2 checkpoint.

The test only cross-checks immutable historical evidence captured from successful
GitHub Actions / GitHub Releases. It cannot prove current registry availability,
a restored runtime image or GPU correctness.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "MINIMAL_V2_CHECKPOINT_2026-10-12.md").read_text()
RUNBOOK = (ROOT / "MINIMAL_V2_RECOVERY.md").read_text()
DATA = json.loads((ROOT / "MINIMAL_V2_EVIDENCE.json").read_text())


class MinimalV2CheckpointTests(unittest.TestCase):
    def test_evidence_contains_two_distinct_immutable_remote_manifests(self):
        self.assertEqual(DATA["github_repository"], "TommyFive/qwen38-runpod-stack")
        self.assertEqual(DATA["ghcr_repository"], "ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint")
        self.assertEqual(set(DATA["candidates"]), {"rust", "rust-cuda"})
        manifests = set()
        for candidate in DATA["candidates"].values():
            digest = candidate["remote_manifest_digest"]
            self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(candidate["original_oci_tar_sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(candidate["original_compressed_oci_layers_bytes"], 10000000000)
            self.assertNotIn(candidate["original_oci_tar_sha256"], digest)
            for doc in (DOC, RUNBOOK):
                self.assertIn(digest, doc)
                self.assertIn(candidate["ghcr_tag"], doc)
            manifests.add(digest)
        self.assertEqual(len(manifests), 2)
        self.assertTrue(DATA["ghcr_publish_verified_workflow"]["remote_tags_manifest_inspected"])

    def test_release_blocks_are_contiguous_and_all_present(self):
        assets = DATA["assets"]
        self.assertEqual(len(assets), 30)
        self.assertEqual(len({x["name"] for x in assets}), 30)
        by_name = {x["name"]: x for x in assets}
        for x in assets:
            self.assertGreater(x["bytes"], 0, x["name"])
            self.assertRegex(x["digest"], r"^sha256:[0-9a-f]{64}$")
        for mode, candidate in DATA["candidates"].items():
            parts = sorted(x for x in assets if re.fullmatch(
                r"release-" + re.escape(mode) + r"\.part-[a-z]{2}", x["name"]
            ))
            self.assertEqual(len(parts), candidate["release_part_count"])
            expected = ["release-" + mode + ".part-a" + chr(ord("a") + n)
                        for n in range(candidate["release_part_count"])]
            self.assertEqual([p["name"] for p in parts], expected)
            self.assertEqual(sum(x["bytes"] for x in parts), candidate["release_part_bytes"])
            self.assertIn(candidate["release_parts_checksum_asset"], by_name)
        encrypted = sorted(name for name in by_name if name.endswith(".age"))
        self.assertEqual(encrypted, sorted([
            "qwen38-checkpoint-logs.tar.gz.age",
            "qwen38-checkpoint-after-split.tar.gz.age",
            "qwen38-original-v1-build-logs.tar.age",
        ]))
        self.assertTrue(DATA["release_assets_verified_workflow"]["release_asset_sha256_verified"])

    def test_docs_distinguish_backed_up_from_runtime_tested(self):
        self.assertNotIn("**PENDING**", DOC)
        self.assertNotIn("splitting in progress at time of initial checkpoint", DOC)
        self.assertNotIn("qwen38-minimal-v2-cpu`", DOC)
        for doc in (DOC, RUNBOOK):
            self.assertIn("issues/46", doc)
            self.assertIn("38159273066", doc)
            self.assertIn("38158692348", doc)
        self.assertIn("NOT VERIFIED", DOC)
        self.assertIn("NOT YET", RUNBOOK)
        self.assertIn("no further access", DOC)
        self.assertIn("No full cold pull", RUNBOOK)


if __name__ == "__main__":
    unittest.main()
