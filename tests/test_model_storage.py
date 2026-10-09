#!/usr/bin/env python3
"""Offline, no GPU/network required. Run: python3 -m unittest discover -s tests -p 'test_model_storage.py'"""
import importlib.util
import io
from contextlib import redirect_stdout
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "model-storage.py"
spec = importlib.util.spec_from_file_location("model_storage", SOURCE)
ms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ms)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.ram = self.base / "shm" / "qwen38-hf"
        self.ram.parent.mkdir()
        self.state = self.base / "state"
        self.state.mkdir()
        self.env = patch.dict(os.environ, {
            "MODEL_STORAGE": "ram", "MODEL_RAM_DIR": str(self.ram),
            "MODEL_ID": "example/main", "SPEC": "dflash2",
            "QWEN38_STATE_DIR": str(self.state),
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def fake_mount(self, path, mountinfo="unused"):
        return str(self.ram.parent), "tmpfs"

    def test_mountinfo_decodes_paths_and_nearest_mount(self):
        filename = self.base / "mountinfo"
        filename.write_text("1 0 0:1 / / rw - overlay overlay rw\n"
                            "2 1 0:2 / /tmp/mock\\040space rw - tmpfs tmpfs rw\n")
        self.assertEqual(ms.mount_info("/tmp/mock space/model", str(filename)),
                         ("/tmp/mock space", "tmpfs"))

    def test_storage_mode_default_ram_and_reject_bad_values(self):
        os.environ.pop("MODEL_STORAGE")
        with patch.object(ms, "mount_info", side_effect=self.fake_mount):
            self.assertEqual(ms.selected_storage()[0], "ram")
            os.environ["MODEL_STORAGE"] = "RAM"
            with self.assertRaisesRegex(ms.StorageError, "exactly"):
                ms.selected_storage()

    def test_wrong_mount_and_ssd_opt_in(self):
        with patch.object(ms, "mount_info", return_value=(str(self.ram.parent), "overlay")):
            with self.assertRaisesRegex(ms.StorageError, "requires tmpfs"):
                ms.selected_storage()
            os.environ["MODEL_STORAGE"] = "ssd"
            os.environ["MODEL_SSD_DIR"] = str(self.base / "ssd")
            self.assertEqual(ms.selected_storage()[0], "ssd")

    def test_cgroup_limited_and_unlimited(self):
        cg = self.base / "cg"
        cg.mkdir()
        (cg / "memory.max").write_text("1000")
        (cg / "memory.current").write_text("350")
        self.assertEqual(ms.cgroup_available(str(cg)), 650)
        (cg / "memory.max").write_text("max")
        with self.assertRaisesRegex(ms.StorageError, "finite"):
            ms.cgroup_available(str(cg))

    def test_ram_full_cgroup_full_and_host_ram_limited(self):
        with patch.object(ms, "repo_bytes", return_value=10 * ms.GIB), \
             patch.object(ms, "cgroup_available", return_value=200 * ms.GIB), \
             patch.object(ms, "host_available", return_value=200 * ms.GIB), \
             patch("os.statvfs", return_value=SimpleNamespace(f_bavail=30, f_frsize=ms.GIB)):
            with self.assertRaisesRegex(ms.StorageError, "tmpfs needs"):
                ms.preflight(self.ram, str(self.ram.parent))
        with patch.object(ms, "repo_bytes", return_value=10 * ms.GIB), \
             patch.object(ms, "cgroup_available", return_value=20 * ms.GIB), \
             patch.object(ms, "host_available", return_value=200 * ms.GIB), \
             patch("os.statvfs", return_value=SimpleNamespace(f_bavail=80, f_frsize=ms.GIB)):
            with self.assertRaisesRegex(ms.StorageError, "cgroup needs"):
                ms.preflight(self.ram, str(self.ram.parent))
        with patch.object(ms, "repo_bytes", return_value=10 * ms.GIB), \
             patch.object(ms, "cgroup_available", return_value=100 * ms.GIB), \
             patch.object(ms, "host_available", return_value=10 * ms.GIB), \
             patch("os.statvfs", return_value=SimpleNamespace(f_bavail=80, f_frsize=ms.GIB)):
            with self.assertRaisesRegex(ms.StorageError, "host MemAvailable"):
                ms.preflight(self.ram, str(self.ram.parent))

    def test_preflight_includes_draft_model(self):
        self.assertEqual(ms.model_repos(), ["example/main", "incoai/Qwen3.8-27B-DFlash2"])
        os.environ["SPEC"] = "dspark"
        self.assertEqual(ms.model_repos()[-1], "RadixArk/Qwen3.8-27B-DSpark")
        os.environ["SPEC"] = "mtp"
        self.assertEqual(ms.model_repos(), ["example/main"])
        os.environ["SPEC"] = "unsupported"
        with self.assertRaisesRegex(ms.StorageError, "unsupported"):
            ms.model_repos()

    def test_missing_model_metadata_fails_closed(self):
        class HfApi:
            def __init__(self, **kw):
                pass
            def model_info(self, **kw):
                return SimpleNamespace(siblings=[SimpleNamespace(rfilename="foo", size=None)])
        with patch.dict(sys.modules, {"huggingface_hub": SimpleNamespace(HfApi=HfApi)}):
            with self.assertRaisesRegex(ms.StorageError, "missing file sizes"):
                ms.repo_bytes(["example/main"])

    def test_preflight_before_creating_files_and_env_propagation(self):
        with patch.object(ms, "mount_info", side_effect=self.fake_mount), \
             patch.object(ms, "preflight", side_effect=ms.StorageError("too little shm")):
            with self.assertRaisesRegex(ms.StorageError, "too little shm"):
                ms.prepare()
        self.assertFalse(self.ram.exists())
        with patch.object(ms, "mount_info", side_effect=self.fake_mount), \
             patch.object(ms, "preflight", return_value=None):
            out = io.StringIO()
            with redirect_stdout(out):
                ms.prepare()
            self.assertIn(f"export HF_HOME={self.ram}", out.getvalue())
            self.assertIn(f"export TMPDIR={self.ram / 'tmp'}", out.getvalue())
            for sub in ("hub", "xet", "assets", "tmp", "xdg", "torch", "datasets"):
                self.assertTrue((self.ram / sub).is_dir())

    def test_read_only_root_is_not_silently_changed(self):
        with patch.object(Path, "mkdir", side_effect=PermissionError("read-only filesystem")):
            with self.assertRaisesRegex(ms.StorageError, "read-only filesystem"):
                ms.make_dirs(self.ram)

    def test_cache_symlink_escape_blocked(self):
        snap = self.ram / "hub" / "snapshots" / "rev"
        snap.mkdir(parents=True)
        (snap / "config.json").write_text("{}")
        with patch.object(ms, "mount_info", side_effect=self.fake_mount):
            ms.verify_snapshot(snap, self.ram, str(self.ram.parent))
            (snap / "bad.bin").symlink_to("/etc/hosts")
            with self.assertRaisesRegex(ms.StorageError, "outside selected storage"):
                ms.verify_snapshot(snap, self.ram, str(self.ram.parent))

    def test_interrupted_draft_download_leaves_no_valid_path_metadata(self):
        self.ram.mkdir()
        snap = self.ram / "hub" / "snapshots" / "rev"
        snap.mkdir(parents=True)
        fake = ModuleType("huggingface_hub")
        called = []
        def snapshot_download(repo, **kw):
            called.append(repo)
            if len(called) == 2:
                raise ConnectionError("interrupted")
            return str(snap)
        fake.snapshot_download = snapshot_download
        with patch.dict(sys.modules, {"huggingface_hub": fake}), \
             patch.object(ms, "mount_info", side_effect=self.fake_mount):
            with self.assertRaisesRegex(ConnectionError, "interrupted"):
                ms.download()
        self.assertEqual(len(called), 2)
        self.assertFalse((self.state / "model_path").exists())
        self.assertFalse((self.state / "draft_path").exists())

    def test_successful_draft_preload_is_local_not_hf_id(self):
        self.ram.mkdir()
        main = self.ram / "hub" / "snapshots" / "main"
        draft = self.ram / "hub" / "snapshots" / "draft"
        main.mkdir(parents=True)
        draft.mkdir(parents=True)
        snapshots = iter([str(main), str(draft)])
        fake = ModuleType("huggingface_hub")
        fake.snapshot_download = lambda *args, **kwargs: next(snapshots)
        with patch.dict(sys.modules, {"huggingface_hub": fake}), \
             patch.object(ms, "mount_info", side_effect=self.fake_mount), \
             patch.object(ms, "cgroup_available", return_value=100 * ms.GIB):
            ms.download()
            result = io.StringIO()
            with redirect_stdout(result):
                ms.audit()
        self.assertEqual((self.state / "model_path").read_text(), str(main))
        self.assertEqual((self.state / "draft_path").read_text(), str(draft))
        self.assertIn(str(draft), result.getvalue())


if __name__ == "__main__":
    unittest.main()
