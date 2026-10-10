"""Offline regression tests. No Docker, downloads, GPUs, or RunPod required."""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "prepare-source.py"
spec = importlib.util.spec_from_file_location("prepare_source", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

PYPROJECT = """[project]
name = "sglang"
dependencies = [
  "torch==2.13.0",
  "flashinfer_python[cu13]==0.6.17",
  "sglang-kernel==0.4.6.post1",
]
[project.optional-dependencies]
diffusion = ["diffusers"]
all = ["sglang[diffusion]"]
"""


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


class PrepareSourceTests(unittest.TestCase):
    def test_minimal_extra_does_not_change_base_or_other_extras(self):
        result = mod.inject_empty_extra(PYPROJECT)
        self.assertIn("qwen38-minimal = []", result)
        self.assertIn('all = ["sglang[diffusion]"]', result)
        self.assertEqual(result.count(mod.MARKER), 1)
        self.assertEqual(result.count("qwen38-minimal"), 1)

    def test_reject_missing_extra_section(self):
        with self.assertRaises(ValueError):
            mod.inject_empty_extra(PYPROJECT.replace(mod.MARKER, ""))

    def test_reject_missing_required_dependency(self):
        with self.assertRaises(ValueError):
            mod.inject_empty_extra(PYPROJECT.replace("torch==2.13.0", "torch==2.12.0"))

    def test_reject_repeated_overlay(self):
        with self.assertRaises(ValueError):
            mod.inject_empty_extra(mod.inject_empty_extra(PYPROJECT))

    def test_pinned_upstream_commit_and_clean_worktree_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "upstream"
            (src / "python").mkdir(parents=True)
            (src / "docker").mkdir()
            (src / "python/pyproject.toml").write_text(PYPROJECT)
            (src / "docker/Dockerfile").write_text("FROM scratch\n")
            run("git", "init", "-q", str(src))
            run("git", "add", ".", cwd=src)
            run(
                "git", "-c", "user.name=Image Test",
                "-c", "user.email=image-test@example.invalid",
                "commit", "-q", "-m", "fake upstream", cwd=src,
            )
            lock = {
                "target": "runtime",
                "build_type": "qwen38-minimal",
                "upstream_commit": run("git", "rev-parse", "HEAD", cwd=src),
                "upstream_pyproject_blob": run(
                    "git", "rev-parse", "HEAD:python/pyproject.toml", cwd=src
                ),
                "upstream_dockerfile_blob": run(
                    "git", "rev-parse", "HEAD:docker/Dockerfile", cwd=src
                ),
            }
            lock_path = base / "lock.json"
            lock_path.write_text(json.dumps(lock))
            mod.prepare(src, lock_path)
            self.assertIn("qwen38-minimal = []", (src / "python/pyproject.toml").read_text())
            with self.assertRaises(ValueError):
                mod.prepare(src, lock_path)  # Fail closed on dirty/reused checkout.
            (src / "python/pyproject.toml").write_text(PYPROJECT)
            wrong = dict(lock, upstream_commit="0" * 40)
            lock_path.write_text(json.dumps(wrong))
            with self.assertRaises(ValueError):
                mod.prepare(src, lock_path)
            self.assertEqual((src / "python/pyproject.toml").read_text(), PYPROJECT)


class BuildContractTests(unittest.TestCase):
    def test_lock_and_builder_keep_validated_stack_components(self):
        root = MODULE.parent
        lock = json.loads((root / "upstream.lock.json").read_text())
        build = (root / "build-image.sh").read_text()
        self.assertEqual(lock["upstream_commit"], "5f55db35e926d50676f75b812640ea2410b0fe0e")
        self.assertEqual(lock["target"], "runtime")
        self.assertEqual(lock["cuda_version"], "13.0.3")
        self.assertEqual(lock["flashinfer_version"], "0.6.17")
        self.assertTrue(lock["flashinfer_jit_cache"])
        self.assertEqual(lock["baseline_amd64_compressed_gb_rounded"], 14.676)
        self.assertIn("--target \"$TARGET\"", build)
        self.assertIn("--build-arg \"BUILD_TYPE=$BUILD_TYPE\"", build)
        self.assertIn("--build-arg \"INSTALL_FLASHINFER_JIT_CACHE=$JIT_CACHE\"", build)
        self.assertIn('QWEN38_IMAGE_PUBLISH:-', build)
        self.assertNotIn("runpodctl", build)


if __name__ == "__main__":
    unittest.main()
