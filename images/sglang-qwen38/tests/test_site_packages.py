"""Offline contracts for read-only site-packages inventory."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "inspect-site-packages.py"
spec = importlib.util.spec_from_file_location("qwen38_pkg_sizes", TARGET)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class PackageInventoryTests(unittest.TestCase):
    def test_counts_nested_files_without_following_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "site-packages"
            (base / "torch" / "lib").mkdir(parents=True)
            (base / "torch" / "lib" / "x.so").write_bytes(b"x" * 300)
            (base / "numpy").mkdir()
            (base / "numpy" / "x.so").write_bytes(b"y" * 200)
            (base / "numpy" / "big-linked.so").symlink_to(base / "torch" / "lib" / "x.so")
            actual = mod.inventory(base)
            self.assertEqual(actual["total_bytes"], 500)
            self.assertEqual([e["name"] for e in actual["entries"]], ["torch", "numpy"])
            self.assertEqual([e["bytes"] for e in actual["entries"]], [300, 200])

    def test_symlink_dir_does_not_escape(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "site").mkdir()
            (p / "outside").mkdir()
            (p / "outside" / "secret.bin").write_bytes(b"s" * 800)
            (p / "site" / "outside-link").symlink_to(p / "outside", target_is_directory=True)
            self.assertEqual(mod.inventory(p / "site")["total_bytes"], 0)

    def test_fails_closed_for_missing_path(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "Missing"):
                mod.inventory(Path(td) / "missing")


if __name__ == "__main__":
    unittest.main()
