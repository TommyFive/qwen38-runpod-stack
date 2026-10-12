"""Offline tests for CPU-only OCI repack contract (no docker, GPU or network)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "tools/audit"


def load(name, identifier):
    spec = importlib.util.spec_from_file_location(identifier, ROOT / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prune = load("prune-candidate.py", "prune_candidate")
generator = load("generate-repack.py", "generate_repack")


class LocalRepackTests(unittest.TestCase):
    def test_dockerfile_copies_modified_root_only_in_scratch_stage(self):
        config = {
            "Entrypoint": ["/opt/nvidia/nvidia_entrypoint.sh"],
            "Cmd": ["/bin/bash"],
            "WorkingDir": "/sgl-workspace/sglang",
            "Env": ["PATH=/opt/sglang/bin:/bin", "CUDA_HOME=/usr/local/cuda"],
            "Labels": {"org.opencontainers.image.version": "v1"},
            "User": "",
        }
        text = generator.build(config, "rust-cuda")
        self.assertIn("FROM scratch", text)
        self.assertIn("COPY --from=prune / /", text)
        self.assertEqual(text.count("--mode rust"), 1)
        self.assertEqual(text.count("--mode cuda"), 1)
        self.assertIn("--network=none", text)
        self.assertIn('ENTRYPOINT ["/opt/nvidia/nvidia_entrypoint.sh"]', text)
        self.assertIn('CMD ["/bin/bash"]', text)
        self.assertIn("SGLANG", generator.SOURCE.upper())
        self.assertNotIn("RUN apt", text)
        with self.assertRaises(ValueError):
            generator.build(dict(config, Entrypoint=["/bin/false"]), "rust")

    def test_rust_removes_only_explicit_intermediate_suffixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "release" / "deps"
            path.mkdir(parents=True)
            a = path / "a.rlib"
            b = path / "a.rmeta"
            dynamic = path / "a.so"
            with a.open("wb") as f:
                f.truncate(1_100_000_000)  # sparse allocation, fast
            with b.open("wb") as f:
                f.truncate(565_334_510)
            dynamic.write_bytes(b"necessary library")
            with patch.object(prune, "RUST", path):
                prune.rust()
            self.assertFalse(a.exists())
            self.assertFalse(b.exists())
            self.assertEqual(dynamic.read_bytes(), b"necessary library")

    def test_cuda_fail_closed_before_any_file_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wheel = root / "wheel"
            system = root / "system"
            wheel.mkdir()
            system.mkdir()
            (wheel / "a.so").write_bytes(b"same")
            (system / "a.so").write_bytes(b"different")
            with patch.object(prune, "WHEEL", wheel), \
                 patch.object(prune, "SYSTEM", system), \
                 patch.object(prune, "PAIRS", (("a.so", "a.so"),)), \
                 patch.object(prune, "EXPECTED_CUDA_BYTES", 4):
                with self.assertRaises(ValueError):
                    prune.cuda()
            self.assertFalse((wheel / "a.so").is_symlink())
            self.assertEqual((wheel / "a.so").read_bytes(), b"same")

    def test_cuda_replaces_verified_wheel_copy_with_relative_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wheel = root / "wheel"
            system = root / "system"
            wheel.mkdir()
            system.mkdir()
            (wheel / "a.so").write_bytes(b"same")
            (system / "a.so").write_bytes(b"same")
            with patch.object(prune, "WHEEL", wheel), \
                 patch.object(prune, "SYSTEM", system), \
                 patch.object(prune, "PAIRS", (("a.so", "a.so"),)), \
                 patch.object(prune, "EXPECTED_CUDA_BYTES", 4):
                prune.cuda()
            self.assertTrue((wheel / "a.so").is_symlink())
            self.assertEqual((wheel / "a.so").resolve(), system / "a.so")
            self.assertEqual((wheel / "a.so").read_bytes(), b"same")


if __name__ == "__main__":
    unittest.main()
