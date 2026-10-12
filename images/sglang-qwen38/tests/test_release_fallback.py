"""Offline contracts for the independent GitHub Release OCI fallback script."""
import json
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"cpu-audit"/"verify-release-fallback.sh"
EVIDENCE=ROOT/"MINIMAL_V2_EVIDENCE.json"


class ReleaseFallbackContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script=SCRIPT.read_text()
        cls.record=json.loads(EVIDENCE.read_text())
        cls.assets={a["name"]:a for a in cls.record["assets"]}

    def test_bash_syntax(self):
        subprocess.run(["bash","-n",str(SCRIPT)],check=True,capture_output=True)

    def test_immutable_digests_match_independent_evidence(self):
        for mode,info in self.record["candidates"].items():
            self.assertIn(info["remote_manifest_digest"][7:],self.script)
            checksum=self.assets[info["release_parts_checksum_asset"]]
            self.assertIn(checksum["digest"][7:],self.script)
            self.assertIn(str(info["release_part_count"]),self.script)

    def test_no_credentials_build_deployment_or_production_changes(self):
        for forbidden in ("docker build", "docker push", "gh auth", "runpodctl",
                          "kubectl", "git push", "sudo ", "ghcr.io/tommyfive/qwen38-sglang:v0.2.0"):
            self.assertNotIn(forbidden,self.script)
        self.assertIn("sha256sum -c",self.script)
        self.assertIn("release-recovery",self.script)
        self.assertIn("oci-split-$mode",self.script)
        self.assertIn("OCI blob SHA mismatch",self.script)


if __name__=="__main__":
    unittest.main()
