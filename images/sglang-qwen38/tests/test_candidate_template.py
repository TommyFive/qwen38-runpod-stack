"""Candidate template dry-run is strictly non-deploying and does not need RunPod CLI."""
import os
import subprocess
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "create-candidate-template.sh"


class CandidateTemplateTests(unittest.TestCase):
    def test_default_dry_run_never_calls_runpod(self):
        env = os.environ.copy()
        env["QWEN38_CREATE_CANDIDATE_TEMPLATE"] = "NO"
        run = subprocess.run(["bash", str(SRC)], env=env, capture_output=True,
                             text=True, timeout=5, check=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("DRY RUN ONLY", run.stdout)
        self.assertIn("No RunPod API change", run.stdout)
        self.assertIn("sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd",
                      run.stdout)

    def test_pinned_image_and_registry_auth(self):
        text = SRC.read_text()
        self.assertIn("--registry-auth-id", text)
        self.assertIn("ghcr.io", text)
        self.assertIn("SGLANG_API_KEY", text)
        self.assertIn("--container-disk-in-gb 150", text)
        self.assertNotIn("pod create", text)
        self.assertNotIn("pod delete", text)


if __name__ == "__main__":
    unittest.main()
