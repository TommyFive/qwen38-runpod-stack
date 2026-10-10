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

    def test_debug_monitor_records_peak_without_modifying_cache(self):
        from contextlib import redirect_stdout
        import io
        outputs = io.StringIO()
        samples = iter([100, 90, 80, 95])
        fake = lambda path: SimpleNamespace(f_bavail=next(samples), f_frsize=ms.GIB, f_blocks=128)
        calls = []
        def done(seconds):
            calls.append(seconds)
            if len(calls) == 3:
                raise KeyboardInterrupt
        with patch.object(ms, "selected_storage", return_value=("ram", self.ram, str(self.ram.parent), "tmpfs")), \
             patch.object(ms, "existing_ancestor", return_value=self.ram.parent), \
             patch("os.statvfs", side_effect=fake), \
             patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="1234")), \
             patch("time.sleep", side_effect=done), \
             redirect_stdout(outputs):
            with self.assertRaises(KeyboardInterrupt):
                ms.monitor()
        lines = [line for line in outputs.getvalue().splitlines()
                 if line.startswith("QWEN38_STORAGE_METRIC ")]
        self.assertEqual(len(lines), 1)
        self.assertIn('"gpu_used_mib":[1234]', lines[0])
        self.assertIn('"peak_tmpfs_delta_gib":10.0', lines[0])

    def release_fixture(self):
        """Two independent HF repos with one reproducible safetensors blob each."""
        root = self.ram
        blob_names = []
        for repo, name in zip(ms.model_repos(), ("model", "draft")):
            base = root / "hub" / ("models--" + repo.replace("/", "--"))
            snapshot = base / "snapshots" / "fixture-rev"
            blobdir = base / "blobs"
            snapshot.mkdir(parents=True)
            blobdir.mkdir(parents=True)
            blob = blobdir / ("a" * 62 + name[:2])
            blob.write_bytes(b"x" * (2 * 1024 * 1024))
            (snapshot / "weight.safetensors").symlink_to(blob)
            (snapshot / "config.json").write_text("{}")
            (self.state / (name + "_path")).write_text(str(snapshot))
            blob_names.append(blob)
        proc = self.base / "proc"
        pid = proc / "123"
        (pid / "fd").mkdir(parents=True)
        (pid / "maps").write_text("")
        return root, blob_names, proc

    def test_release_default_off_fails_closed(self):
        root, blobs, proc = self.release_fixture()
        with patch.object(ms, "selected_storage",
                          return_value=("ram", root, str(self.ram.parent), "tmpfs")):
            with self.assertRaisesRegex(ms.StorageError, "explicit"):
                ms.release_weight_blobs(proc)
        self.assertTrue(all(p.exists() for p in blobs))

    def test_release_preserves_config_and_releases_only_verified_blobs(self):
        root, blobs, proc = self.release_fixture()
        os.environ["MODEL_RAM_RELEASE_AFTER_LOAD"] = "1"
        with patch.object(ms, "selected_storage",
                          return_value=("ram", root, str(self.ram.parent), "tmpfs")), \
             patch.object(ms, "mount_info", side_effect=self.fake_mount):
            count, bytes_removed = ms.release_weight_blobs(proc)
        self.assertEqual(count, 2)
        self.assertEqual(bytes_removed, 4 * 1024 * 1024)
        self.assertTrue(all(not p.exists() for p in blobs))
        self.assertEqual(len(list(root.rglob("*.safetensors"))), 0)
        self.assertEqual(len(list(root.rglob("config.json"))), 2)

    def test_release_fails_closed_for_open_mapping_and_fd(self):
        root, blobs, proc = self.release_fixture()
        os.environ["MODEL_RAM_RELEASE_AFTER_LOAD"] = "1"
        mapped = proc / "123" / "maps"
        mapped.write_text("abc " + str(blobs[0]) + " r--p\n")
        with patch.object(ms, "selected_storage",
                          return_value=("ram", root, str(self.ram.parent), "tmpfs")), \
             patch.object(ms, "mount_info", side_effect=self.fake_mount):
            with self.assertRaisesRegex(ms.StorageError, "mapped"):
                ms.release_weight_blobs(proc)
            mapped.write_text("")
            (proc / "123" / "fd" / "6").symlink_to(blobs[0])
            with self.assertRaisesRegex(ms.StorageError, "held open"):
                ms.release_weight_blobs(proc)
        self.assertTrue(all(p.exists() for p in blobs))

    def test_release_refuses_wrong_mode_symlink_and_alternate_format(self):
        root, blobs, proc = self.release_fixture()
        os.environ["MODEL_RAM_RELEASE_AFTER_LOAD"] = "1"
        with patch.object(ms, "selected_storage",
                          return_value=("ssd", root, str(self.ram.parent), "overlay")):
            with self.assertRaisesRegex(ms.StorageError, "tmpfs"):
                ms.release_weight_blobs(proc)
        snapshot = root / "hub" / "models--example--main" / "snapshots" / "fixture-rev"
        (snapshot / "unverified.bin").write_bytes(b"unverified")
        with patch.object(ms, "selected_storage",
                          return_value=("ram", root, str(self.ram.parent), "tmpfs")), \
             patch.object(ms, "mount_info", side_effect=self.fake_mount):
            with self.assertRaisesRegex(ms.StorageError, "alternate"):
                ms.release_weight_blobs(proc)
        self.assertTrue(all(p.exists() for p in blobs))

    def test_release_waits_for_authenticated_inference_and_benchmark(self):
        root, blobs, proc = self.release_fixture()
        os.environ["MODEL_RAM_RELEASE_AFTER_LOAD"] = "1"
        os.environ["BENCHMARK"] = "1"
        report = self.base / "report.json"
        os.environ["BENCHMARK_REPORT_PATH"] = str(report)
        with patch.object(ms, "_infer_ready", return_value=False), \
             patch.object(ms.time, "monotonic", side_effect=[0, 1201]):
            with self.assertRaisesRegex(ms.StorageError, "not ready"):
                ms.release_after_ready()
        self.assertTrue(all(p.exists() for p in blobs))

    def test_cgroup_limited_and_unlimited(self):
        cg = self.base / "cg"
        cg.mkdir()
        (cg / "memory.max").write_text("1000")
        (cg / "memory.current").write_text("350")
        self.assertEqual(ms.cgroup_available(str(cg)), 650)
        (cg / "memory.max").write_text("max")
        with self.assertRaisesRegex(ms.StorageError, "finite"):
            ms.cgroup_available(str(cg))

    def test_cgroup_v1_mounted_memory_controller(self):
        controller = self.base / "sys" / "memory"
        member = controller / "slice" / "pod"
        member.mkdir(parents=True)
        (member / "memory.limit_in_bytes").write_text("10000")
        (member / "memory.usage_in_bytes").write_text("2500")
        mountinfo = self.base / "mountinfo"
        mountinfo.write_text(
            f"11 5 0:42 / {controller} rw - cgroup cgroup rw,memory\n")
        membership = self.base / "cgroup"
        membership.write_text("7:cpu,cpuacct:/slice/pod\n8:memory:/slice/pod\n")
        self.assertEqual(ms.cgroup_available(str(controller), str(mountinfo),
                                             str(membership)), 7500)

    def test_cgroup_v1_delegated_mount_root(self):
        controller = self.base / "sys" / "memory"
        controller.mkdir(parents=True)
        (controller / "memory.limit_in_bytes").write_text("10000")
        (controller / "memory.usage_in_bytes").write_text("3000")
        mountinfo = self.base / "mountinfo"
        mountinfo.write_text(
            f"11 5 0:42 /outer/pod {controller} rw - cgroup cgroup rw,memory\n")
        membership = self.base / "cgroup"
        membership.write_text("8:memory:/outer/pod\n")
        self.assertEqual(ms.cgroup_available(str(controller), str(mountinfo),
                                             str(membership)), 7000)

    def test_cgroup_v1_unlimited_and_missing_fail_closed(self):
        controller = self.base / "sys" / "memory"
        controller.mkdir(parents=True)
        (controller / "memory.limit_in_bytes").write_text("9223372036854771712")
        (controller / "memory.usage_in_bytes").write_text("500")
        mountinfo = self.base / "mountinfo"
        mountinfo.write_text(
            f"11 5 0:42 / {controller} rw - cgroup cgroup rw,memory\n")
        membership = self.base / "cgroup"
        membership.write_text("8:memory:/\n")
        with self.assertRaisesRegex(ms.StorageError, "unlimited"):
            ms.cgroup_available(str(controller), str(mountinfo), str(membership))
        (controller / "memory.limit_in_bytes").unlink()
        with self.assertRaisesRegex(ms.StorageError, "cannot read"):
            ms.cgroup_available(str(controller), str(mountinfo), str(membership))

    def test_cgroup_missing_controller_fails_closed(self):
        directory = self.base / "nomemory"
        directory.mkdir()
        mountinfo = self.base / "mountinfo"
        mountinfo.write_text("4 1 0:7 / /sys/fs/cgroup ro - tmpfs tmpfs rw\n")
        membership = self.base / "cgroup"
        membership.write_text("2:cpu:/\n")
        with self.assertRaisesRegex(ms.StorageError, "cannot establish finite"):
            ms.cgroup_available(str(directory), str(mountinfo), str(membership))

    def test_ram_preflight_reports_tmpfs_capacity_before_missing_cgroup(self):
        err = io.StringIO()
        with patch.object(ms, "repo_bytes", return_value=10 * ms.GIB), \
             patch.object(ms, "cgroup_available", side_effect=ms.StorageError("missing cgroup")), \
             patch("os.statvfs", return_value=SimpleNamespace(f_bavail=90, f_frsize=ms.GIB)), \
             patch("sys.stderr", err):
            with self.assertRaisesRegex(ms.StorageError, "missing cgroup"):
                ms.preflight(self.ram, str(self.ram.parent))
        self.assertIn("shm_available=90.00 GiB", err.getvalue())
        self.assertIn("shm_required=33.00 GiB", err.getvalue())

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
