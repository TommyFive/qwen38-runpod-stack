"""Offline regression checks for the CPU image-forensics tools."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tools/audit"


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


collect = load("collect.py", "qwen38_collect")
analyze_mod = load("analyze.py", "qwen38_analyze")
dupes = load("verify-duplicates.py", "qwen38_dupes")


class CpuAuditTests(unittest.TestCase):
    def test_read_only_stat_and_symlink_without_follow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = root / "ordinary"
            item.write_bytes(b"abc" * 9)
            link = root / "link"
            link.symlink_to(item)
            self.assertEqual(collect.record(item)["size"], 27)
            self.assertEqual(collect.record(item)["k"], "file")
            self.assertEqual(collect.record(link)["k"], "link")
            self.assertEqual(collect.record(link)["target"], str(item))

    def test_summary_aggregates_without_compressed_savings_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entries = [
                {"p": "/opt/sglang/lib/python3.12/site-packages/foo/a.so",
                 "k": "file", "size": 12000000},
                {"p": "/usr/local/cuda-13.0/lib64/a.so",
                 "k": "file", "size": 12000000},
                {"p": "/sgl-workspace/sglang/test.py",
                 "k": "file", "size": 23},
                {"p": "/tmp/ignored", "k": "link", "size": 0},
            ]
            (root / "files.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in entries)
            )
            (root / "python.jsonl").write_text(json.dumps({
                "name": "foo", "version": "1.0", "requires": [],
                "reported_files": 1,
            }) + "\n")
            (root / "dpkg.jsonl").write_text(json.dumps({
                "name": "gcc", "version": "1", "installed_kib": 3500
            }) + "\n")
            data = analyze_mod.analyze(root)
            self.assertEqual(data["logical_bytes_total"], 24000023)
            self.assertEqual(data["file_count"], 3)
            self.assertEqual(data["link_count"], 1)
            self.assertEqual(len(data["possible_same_name_size"]), 1)
            self.assertIn("logical/uncompressed", analyze_mod.report(data))
            self.assertEqual(len(data["dpkg"]), 1)

    def test_duplicate_hash_matches_real_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / "a", root / "b"
            a.write_bytes(b"abc")
            b.write_bytes(b"abc")
            self.assertEqual(dupes.digest(a), dupes.digest(b))
            b.write_bytes(b"abd")
            self.assertNotEqual(dupes.digest(a), dupes.digest(b))


if __name__ == "__main__":
    unittest.main()
