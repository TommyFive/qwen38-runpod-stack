"""Safety contracts for v0.2.2 RunPod template promotion (offline)."""
import pathlib,re,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
DIGEST="820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7"
class TemplatesV022(unittest.TestCase):
    def test_registry_verifier_pins_eight_layer_release(self):
        s=(ROOT/"images/sglang-qwen38/tools/check-public.py").read_text()
        self.assertIn(DIGEST,s)
        self.assertIn("len(layers) != 8",s)
    def test_launcher_and_generator_pinned_same_digest_and_version(self):
        for name in ("create-templates.sh","bin/qwen38fast"):
            s=(ROOT/name).read_text()
            self.assertIn(DIGEST,s)
            self.assertIn("qwen38-v0.2.2",s)
    def test_real_full_template_uses_secret_and_lean_does_not(self):
        s=(ROOT/"create-templates.sh").read_text()
        self.assertIn('if sys.argv[4]=="1" else {}',s)
        self.assertIn('WEBUI_PASSWORD_SECRET_NAME',s)
        self.assertIn('DEFAULT_DISK_GB=30',s)
        self.assertIn('\"TS_HOSTNAME\":\"llm\",',s)
        self.assertNotIn("'8000/http,8080/http,22/tcp'",s)
    def test_launcher_secret_mode_not_plaintext_admin_password(self):
        s=(ROOT/"bin/qwen38fast").read_text()
        resolver=(ROOT/"scripts/resolve-template-launch.py").read_text()
        self.assertIn('validate_secret("WEBUI_ADMIN_PASSWORD",env)',resolver)
        self.assertIn('QWEN38_WEBUI_ADMIN_PASSWORD',resolver)
        self.assertIn('Plaintext WebUI password forbidden',resolver)
        self.assertIn('template_disk=size(t.get("containerDiskInGb"))',resolver)
        self.assertIn('ENV_JSON="$(plan_get env_overrides)"',s)
if __name__=="__main__": unittest.main()
