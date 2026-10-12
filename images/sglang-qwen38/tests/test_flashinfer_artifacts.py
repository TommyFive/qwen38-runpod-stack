"""Offline-only regression tests for read-only FlashInfer audit."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools/inspect-flashinfer-artifacts.py"
spec = importlib.util.spec_from_file_location("flashinfer_audit", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FlashInferAuditTests(unittest.TestCase):
    def test_architecture_classification_is_conservative(self):
        self.assertEqual(mod.classify("kernels/Sm120f_foo.cubin")[0], "sm120_named")
        self.assertEqual(mod.classify("kernels/sm_100a_foo.cubin")[0], "other_arch_named")
        self.assertEqual(mod.classify("kernels/SM90a_SM120f.fatbin")[0], "multi_arch")
        self.assertEqual(mod.classify("kernels/opaque-kernel.fatbin")[0], "unknown")
        self.assertEqual(mod.classify("README-sm120-update.txt")[0], "unknown")

    def test_inventory_counts_files_without_changes_or_following_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            cubin = site / "flashinfer_cubin"
            jit = site / "flashinfer_jit_cache"
            cubin.mkdir()
            jit.mkdir()
            (cubin / "sm_120f_kernel.cubin").write_bytes(b"a" * 17)
            (cubin / "sm_100f_kernel.cubin").write_bytes(b"b" * 13)
            (cubin / "opaque.fatbin").write_bytes(b"c" * 11)
            (jit / "sm_120f_sm_100f.fatbin").write_bytes(b"d" * 7)
            (jit / "sm90a_kernel.bin").write_bytes(b"e" * 5)
            (cubin / "link.cubin").symlink_to(jit / "sm90a_kernel.bin")
            before = {p.relative_to(site): p.read_bytes() for p in site.rglob("*")
                      if p.is_file() and not p.is_symlink()}
            report = mod.inspect(site, sample_limit=1)
            self.assertEqual(report["schema"], 1)
            self.assertEqual(report["packages"]["flashinfer_cubin"]["logical_bytes"], 41)
            self.assertEqual(report["packages"]["flashinfer_cubin"]["skipped_symlinks"], 1)
            self.assertEqual(report["packages"]["flashinfer_jit_cache"]["logical_bytes"], 12)
            self.assertEqual(report["packages"]["flashinfer_jit_cache"]["by_path_category"]["multi_arch"]["files"], 1)
            after = {p.relative_to(site): p.read_bytes() for p in site.rglob("*")
                     if p.is_file() and not p.is_symlink()}
            self.assertEqual(before, after)

    def test_missing_package_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "flashinfer_cubin").mkdir()
            with self.assertRaises(ValueError):
                mod.inspect(Path(tmp))


if __name__ == "__main__":
    unittest.main()
