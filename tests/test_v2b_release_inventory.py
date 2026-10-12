"""Contract tests for the exhaustive, evidence-backed minimal-v2B removal inventory."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
INVENTORY=ROOT/"docs/releases/v0.2.2-removal-inventory"

class V2BRemovalReleaseAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((INVENTORY/"removal-summary.json").read_text())

    def test_expected_immutable_image_identities(self):
        self.assertTrue(self.data["original_v1_image"].endswith("1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd"))
        self.assertTrue(self.data["result_v2b_image"].endswith("820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7"))

    def test_all_1192_removed_rust_paths_reconcile_with_pruner(self):
        spec=importlib.util.spec_from_file_location("prune",ROOT/"images/sglang-qwen38/cpu-audit/prune-candidate.py")
        prune=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prune)
        with (INVENTORY/"removed-rust-files-v1-to-v2b.tsv").open() as f:
            records=list(csv.DictReader(f,delimiter="\t"))
        self.assertEqual(len(records),1192)
        self.assertEqual(sum(int(x["logical_size_bytes"]) for x in records),1665334510)
        self.assertEqual(len(set(x["original_v1_regular_file"] for x in records)),1192)
        self.assertEqual(sum(x["file_type"]==".rlib" for x in records),597)
        self.assertEqual(sum(x["file_type"]==".rmeta" for x in records),595)
        for x in records:
            path=x["original_v1_regular_file"]
            self.assertTrue(path.startswith(str(prune.RUST)+"/"))
            self.assertTrue(path.endswith((".rlib",".rmeta")))
            self.assertEqual(x["file_type"],Path(path).suffix)
        self.assertEqual(self.data["actual_rust_removal"]["count"],1192)

    def test_all_11_cuda_pairs_match_prune_allowlist_and_original_hashes(self):
        spec=importlib.util.spec_from_file_location("prune",ROOT/"images/sglang-qwen38/cpu-audit/prune-candidate.py")
        prune=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prune)
        with (INVENTORY/"deduplicated-cuda-libraries-v1-to-v2b.tsv").open() as f:
            records=list(csv.DictReader(f,delimiter="\t"))
        self.assertEqual(len(records),11)
        self.assertEqual(sum(int(x["old_regular_file_bytes"]) for x in records),1679571048)
        self.assertEqual(len(set(x["v1_regular_file_replaced_by_symlink"] for x in records)),11)
        actual={(x["v1_regular_file_replaced_by_symlink"],x["unchanged_system_file_symlink_target"]) for x in records}
        expected={(str(prune.WHEEL/w),str(prune.SYSTEM/s)) for w,s in prune.PAIRS}
        self.assertEqual(actual,expected)
        self.assertTrue(all(len(x["verified_identical_sha256"])==64 for x in records))
        self.assertEqual(self.data["actual_cuda_dedup"]["regular_files_replaced_by_links"],11)

    def test_release_inventories_match_checksums(self):
        for name,expected in self.data["inventory_sha256"].items():
            self.assertEqual(hashlib.sha256((INVENTORY/name).read_bytes()).hexdigest(),expected)
        with (INVENTORY/"upstream-all-extra-direct-declarations.tsv").open() as f:
            rows=list(csv.DictReader(f,delimiter="\t"))
        self.assertEqual(len(rows),25)
        self.assertEqual({k:sum(x["upstream_optional_extra"]==k for x in rows)
                          for k in ("diffusion","http2","tracing")},
                         {"diffusion":20,"http2":1,"tracing":4})

    def test_release_clearly_distinguishes_two_baselines(self):
        text=(ROOT/"docs/releases/v0.2.2.md").read_text()
        for token in ("PROPOSED","original upstream","minimal-v1","minimal-v2 B",
                      "not supported by evidence","1,192","11 byte-identical pairs",
                      "1,203","2,203,696,500","OpenWebUI is NOT baked"):
            self.assertIn(token,text)

if __name__=="__main__":
    unittest.main()
