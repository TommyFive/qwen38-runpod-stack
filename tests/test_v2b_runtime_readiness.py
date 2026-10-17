"""CPU-only v2-B Lean/Full runtime readiness regression contracts."""
import ast
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
BOOT=ROOT/"scripts"/"bootstrap-sglang-openwebui.sh"

def uv_python_block():
    match=re.search(r"<<'PY_UV_RUNTIME'\n(?P<code>[\s\S]*?)\nPY_UV_RUNTIME\b",BOOT.read_text())
    if not match:
        raise AssertionError("Missing pinned uv installer heredoc")
    return match.group("code")

class V2BRuntimeReadiness(unittest.TestCase):
    def test_runtime_pinned_uv_download_validates_hash_and_origin(self):
        code=uv_python_block()
        ast.parse(code)
        self.assertIn("hashlib.sha256(raw).hexdigest() != expected",code)
        self.assertIn("parsed.hostname != 'files.pythonhosted.org'",code)
        self.assertIn("os.replace(tmp, target)",code)
        self.assertIn("uv-0.12.10-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",code)

    def test_pinned_uv_version_accepts_official_architecture_suffix(self):
        s=BOOT.read_text()
        self.assertEqual(s.count("grep -Eq '^uv 0[.]12[.]10([[:space:]]|$)'"),2)
        for sample,expected in (("uv 0.12.10 (x86_64-unknown-linux-gnu)",0),
                                ("uv 0.12.10",0),("uv 0.12.11",1)):
            result=subprocess.run(["grep","-Eq","^uv 0[.]12[.]10([[:space:]]|$)"],
                                   input=sample+"\n",capture_output=True,text=True)
            self.assertEqual(result.returncode,expected,sample)

    def test_source_has_no_unconditional_uv_or_webui_install(self):
        s=BOOT.read_text()
        self.assertLess(s.index('if [[ "$SERVE_WEBUI" == 1 ]]; then\n  # Admin credentials'),
                        s.index('if ! provision_uv_runtime; then'))
        self.assertIn('SERVE_WEBUI=0, skipping OpenWebUI, SGLang API only',s)

    def test_workspace_absence_no_longer_breaks_smoke_or_full_default(self):
        s=BOOT.read_text()
        self.assertNotIn('cat > /workspace/smoke-storage.sh',s)
        self.assertNotIn('chmod 700 /workspace/smoke-storage.sh',s)
        self.assertIn('cat > "$RUNTIME_LOG_DIR/smoke-storage.sh"',s)
        self.assertIn('WEBUI_VENV="${QWEN38_WORKSPACE:-/tmp/qwen38-webui}/openwebui-venv"',s)

    def test_missing_admin_and_install_fail_closed(self):
        s=BOOT.read_text()
        for phase in ("credentials","uv","install","readiness"):
            self.assertIn("QWEN38_WEBUI status=failed phase="+phase,s)
        self.assertIn('if ! wait_for_webui_ready; then',s)
        self.assertIn('timeout 900 "$UV_BIN" pip install',s)

    def test_install_logging_is_redacted_and_diagnostics_visible(self):
        s=BOOT.read_text()
        self.assertIn('env DEBUG=1 python3 -u "$RUNTIME_LOG_DIR/redact-log.py"',s)
        self.assertIn('tee -a "$RUNTIME_LOG_DIR/openwebui-install.log"',s)
        self.assertNotIn('"open-webui==$WEBUI_VERSION" >/dev/null 2>&1',s)
        self.assertIn('set -uo pipefail',s)

    def test_uv_python_rejects_unexpected_download_origin(self):
        code=uv_python_block().replace('urllib.request.urlopen(','__import__("fixture").urlopen(')
        fixtures="""import io,json
class Resp:
    def __init__(self,data): self.data=data
    def __enter__(self): return io.BytesIO(self.data)
    def __exit__(self,*a): pass
def urlopen(url,timeout=None):
    if 'pypi.org' in url:
        return Resp(json.dumps({'urls':[{
          'filename':'uv-0.12.10-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl',
          'url':'https://evil.example/uv.whl',
          'digests':{'sha256':'f7d6248ad9f2d282fea795f248da8fa666ab382df50d8385bd98e01049440a0c'}
        }]}).encode())
    raise AssertionError('attempt to download from unexpected host')
"""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d,"fixture.py").write_text(fixtures)
            import os
            p=subprocess.run([sys.executable,"-c",code,str(pathlib.Path(d,"uv"))],
                env=dict(os.environ,PYTHONPATH=d),capture_output=True,text=True,timeout=8)
            self.assertNotEqual(p.returncode,0)
            self.assertIn("unexpected uv wheel distribution host",p.stderr)
            self.assertFalse(pathlib.Path(d,"uv").exists())

if __name__=="__main__":
    unittest.main()
