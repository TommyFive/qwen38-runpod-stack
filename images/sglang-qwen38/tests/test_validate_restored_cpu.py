"""No-Docker offline unit tests for restored-image CPU acceptance contracts."""
import importlib.util
import unittest
from pathlib import Path

PATH=Path(__file__).resolve().parents[1]/"tools/audit"/"validate-restored-cpu.py"
spec=importlib.util.spec_from_file_location("qwen38_restored_cpu",PATH)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def config(mode=None):
    return {"Architecture":"amd64","Os":"linux","Config":{
        "Env":["X=1"],"Entrypoint":["/boot"],"Cmd":["serve"],
        "WorkingDir":"/opt","User":"","ExposedPorts":None,
        "Volumes":None,"StopSignal":None,
        "Labels":{"original":"same",**({"ai.qwen38.experimental-repack":mode} if mode else {})}
    }}


def result(mode):
    return {"mode":mode,"rust_intermediates":0,"imports":{
        x:{"version":"1.2","duration_seconds":0.1}
        for x in ("torch","flashinfer","sglang","transformers")},
        "cuda":{f"lib{i}":{"wheel_sha256":"a"*64,
                    "system_sha256":"a"*64,"is_symlink":mode=="rust-cuda"}
                    for i in range(11)}}


class RestoredCpuContractTests(unittest.TestCase):
    def test_metadata_preserves_original_runtime_config(self):
        self.assertTrue(module.assert_metadata(config(),config("rust"),"rust"))

    def test_metadata_fails_on_original_setting_drift(self):
        candidate=config("rust")
        candidate["Config"]["Entrypoint"]=["/other"]
        with self.assertRaisesRegex(ValueError,"runtime config"):
            module.assert_metadata(config(),candidate,"rust")

    def test_metadata_fails_on_original_label_drift(self):
        candidate=config("rust-cuda")
        candidate["Config"]["Labels"]["original"]="changed"
        with self.assertRaisesRegex(ValueError,"original labels"):
            module.assert_metadata(config(),candidate,"rust-cuda")

    def test_metadata_fails_if_experiment_label_absent(self):
        with self.assertRaisesRegex(ValueError,"experiment label"):
            module.assert_metadata(config(),config(),"rust")

    def test_cuda_baseline_parity(self):
        self.assertTrue(module.compare_results({"baseline":result("baseline"),
                          "rust":result("rust"),"rust-cuda":result("rust-cuda")}))

    def test_cuda_hash_mismatch_fails_closed(self):
        values={"baseline":result("baseline"),"rust":result("rust"),
                "rust-cuda":result("rust-cuda")}
        values["rust-cuda"]["cuda"]["lib2"]["wheel_sha256"]="b"*64
        with self.assertRaisesRegex(ValueError,"CUDA library bytes"):
            module.compare_results(values)

    def test_module_version_mismatch_fails_closed(self):
        values={"baseline":result("baseline"),"rust":result("rust"),
                "rust-cuda":result("rust-cuda")}
        values["rust"]["imports"]["sglang"]["version"]="other"
        with self.assertRaisesRegex(ValueError,"Version mismatch"):
            module.compare_results(values)


if __name__=="__main__":
    unittest.main()
