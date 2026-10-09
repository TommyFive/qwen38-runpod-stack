#!/usr/bin/env bash
# Offline privacy regression suite. Never starts a real pod or installs packages.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
RAM="$(mktemp -d /dev/shm/qwen38-privacy-ci.XXXXXXXX)"
trap 'rm -rf "$TMP" "$RAM"' EXIT
mkdir -p "$TMP"/{bin,home,mocks/sglang} "$RAM/workspace"
export HOME="$TMP/home" PATH="$TMP/bin:$PATH" PYTHONPATH="$TMP/mocks"
export QWEN38_WORKSPACE="$RAM/workspace" RUNTIME_LOG_DIR="$RAM/runtime"
export WEBUI_DATA_DIR="$RAM/data" TEST_WEBUI_FLAGS="$TMP/webui-flags.json"
export TEST_LAUNCH_FLAGS="$TMP/launch-flags.json"
export TEST_TEMPLATE_FLAGS="$TMP/template-flags.jsonl"
export MODEL_ID="example/test-model" SERVE_WEBUI=1
export SGLANG_API_KEY="SENTINEL_API_KEY_91e6f9"
export HF_TOKEN="SENTINEL_HF_TOKEN_8174bd"
export WEBUI_ADMIN_EMAIL="admin@example.invalid"
export WEBUI_ADMIN_PASSWORD="SENTINEL_WEBUI_PASSWORD_b54a5a42"
export TEST_HF_TOKEN="$HF_TOKEN"

cat > "$TMP/mocks/huggingface_hub.py" <<'PY'
import os
from pathlib import Path
def snapshot_download(repo_id, max_workers, token):
    assert token == os.environ["TEST_HF_TOKEN"]
    p = Path(os.environ["QWEN38_WORKSPACE"]) / "model"
    p.mkdir(parents=True, exist_ok=True)
    return str(p)
PY
touch "$TMP/mocks/hf_xet.py" "$TMP/mocks/sglang/__init__.py"
cat > "$TMP/mocks/sglang/launch_server.py" <<'PY'
import os, sys, json
args = sys.argv[1:]
assert "--api-key" in args and args[args.index("--api-key") + 1] == os.environ["SGLANG_API_KEY"]
assert "--log-requests" not in args
assert args[args.index("--host") + 1] == "0.0.0.0"
assert args[args.index("--log-level") + 1] == ("info" if os.getenv("DEBUG") == "1" else "warning")
print(os.environ["SGLANG_API_KEY"] + " " + os.environ["HF_TOKEN"], flush=True)
PY
cat > "$TMP/bin/nvidia-smi" <<'MOCK'
#!/usr/bin/env bash
echo 'Mock GPU, 98304 MiB, 12.0'
MOCK
cat > "$TMP/bin/curl" <<'MOCK'
#!/usr/bin/env bash
case "$*" in
  *"/v1/models"*) echo '{"data":[{"id":"qwen38-uncensored"}]}' ;;
  *"/api/config"*) echo '{"features":{"auth":true,"enable_signup":false}}' ;;
  *) echo '25000000' ;;
esac
MOCK
cat > "$TMP/bin/uv" <<'MOCK'
#!/usr/bin/env bash
set -e
if [[ "$1" == venv ]]; then
    dest="${@: -1}"
    mkdir -p "$dest/bin"
    cat > "$dest/bin/open-webui" <<'WEBUI'
#!/usr/bin/env bash
python3 - <<'PY'
import json, os
from pathlib import Path
v = {key: os.getenv(key) for key in ("WEBUI_AUTH","ENABLE_SIGNUP","ENABLE_PERSISTENT_CONFIG","WEBUI_SESSION_COOKIE_SECURE","DATA_DIR","DO_NOT_TRACK")}
Path(os.environ["TEST_WEBUI_FLAGS"]).write_text(json.dumps(v))
assert v["WEBUI_AUTH"] == "True"
assert v["ENABLE_SIGNUP"] == "False"
assert v["WEBUI_SESSION_COOKIE_SECURE"] == "True"
assert v["DATA_DIR"].startswith("/dev/shm/")
assert os.getenv("WEBUI_ADMIN_PASSWORD")
Path(v["DATA_DIR"], "private-db.sqlite").write_text("ephemeral")
print(os.environ["SGLANG_API_KEY"] + " " + os.environ["WEBUI_ADMIN_PASSWORD"], flush=True)
PY
WEBUI
    chmod +x "$dest/bin/open-webui"
fi
MOCK
cat > "$TMP/bin/runpodctl" <<'MOCK'
#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if args[:2] == ["pod", "list"]:
    print("[]")
elif args[:2] == ["template", "create"]:
    env = json.loads(args[args.index("--env") + 1])
    assert env["DEBUG"] == "0"
    assert env["RUNTIME_LOG_DIR"] == "/dev/shm/qwen38-runtime"
    assert env["ENABLE_SSH"] == "0"
    assert env["BOOTSTRAP_B64"] and env["MODEL_ID"]
    assert "SGLANG_API_KEY" not in env
    assert "WEBUI_ADMIN_PASSWORD" not in env
    with open(os.environ["TEST_TEMPLATE_FLAGS"], "a") as out:
        out.write(json.dumps({"ui":env["SERVE_WEBUI"],"ports":args[args.index("--ports")+1]})+"\n")
    print(json.dumps({"id":"template-ci-"+env["SERVE_WEBUI"]}))
else:
    raise SystemExit("unexpected mock runpodctl invocation")
MOCK
cat > "$TMP/bin/rp" <<'MOCK'
#!/usr/bin/env python3
import json, os, sys
args=sys.argv[1:]
env=json.loads(args[args.index("--env")+1])
from pathlib import Path
assert env["SGLANG_API_KEY"] == (Path.home() / ".runpod/qwen38.key").read_text().strip()
assert env["SGLANG_API_KEY"] != env["HF_TOKEN"]
assert env["WEBUI_ADMIN_PASSWORD"] == os.environ["WEBUI_ADMIN_PASSWORD"]
assert env["DEBUG"] == os.environ["QWEN38_DEBUG"]
assert env["HF_TOKEN"] == os.environ["TEST_EXPECTED_LAUNCH_HF"]
assert env["SERVE_WEBUI"] == "1"
with open(os.environ["TEST_LAUNCH_FLAGS"],"w") as f:
    json.dump({"hf_override": True, "webui_auth_supplied": True, "debug": env["DEBUG"]},f)
print('{"id":"privacy-test-pod"}')
MOCK
cat > "$TMP/bin/date" <<'MOCK'
#!/usr/bin/env bash
echo '12:00'
MOCK
cat > "$TMP/bin/sleep" <<'MOCK'
#!/usr/bin/env bash
if [[ "$1" == infinity ]]; then exit 0; fi
/bin/sleep 0.25
MOCK
cat > "$TMP/bin/open" <<'MOCK'
#!/usr/bin/env bash
exit 0
MOCK
chmod +x "$TMP/bin/"*

echo '=== fail-closed validation ==='
if DEBUG=bad bash "$ROOT/scripts/bootstrap-sglang-openwebui.sh" > "$TMP/bad-debug" 2>&1; then
    echo "invalid DEBUG was accepted" >&2; exit 1
fi
grep -Fq 'DEBUG must be 0 or 1' "$TMP/bad-debug"
if SGLANG_API_KEY='' bash "$ROOT/scripts/bootstrap-sglang-openwebui.sh" > "$TMP/no-api" 2>&1; then
    echo "unauthenticated API was accepted" >&2; exit 1
fi
grep -Fq 'SGLANG_API_KEY required' "$TMP/no-api"
set +e
NETWORK_MODE=tailnet bash "$ROOT/scripts/bootstrap-sglang-openwebui.sh" > "$TMP/no-ts" 2>&1
tailnet_rc=$?
set -e
if [[ "$tailnet_rc" != 70 ]]; then
    echo "tailnet without Tailscale did not fail closed with exit 70" >&2; exit 1
fi
if RUNTIME_LOG_DIR="$TMP/overlay" bash "$ROOT/scripts/bootstrap-sglang-openwebui.sh" > "$TMP/overlay-denied" 2>&1; then
    echo "persistent runtime logs allowed without opt-in" >&2; exit 1
fi
grep -Fq 'must be tmpfs' "$TMP/overlay-denied"

echo '=== default quiet mode with real script generation ==='
DEBUG=0 bash "$ROOT/scripts/bootstrap-sglang-openwebui.sh" > "$TMP/quiet" 2>&1
/bin/sleep 1
test -f "$RUNTIME_LOG_DIR/start-sglang.sh"
test -f "$RUNTIME_LOG_DIR/start-openwebui.sh"
test -f "$RUNTIME_LOG_DIR/snapshot.json"
test -f "$WEBUI_DATA_DIR/private-db.sqlite"
test ! -e "$RUNTIME_LOG_DIR/sglang.log"
test ! -e "$RUNTIME_LOG_DIR/openwebui.log"
python3 - "$RUNTIME_LOG_DIR" <<'PY'
import os, stat, sys
d=sys.argv[1]
for file in ("start-sglang.sh","start-openwebui.sh","bootstrap.log","snapshot.json","redact-log.py"):
    p=os.path.join(d,file)
    assert stat.S_IMODE(os.stat(p).st_mode) & 0o077 == 0, p
PY
if grep -ER "SENTINEL_(API_KEY|HF_TOKEN|WEBUI_PASSWORD)" "$RUNTIME_LOG_DIR" "$TMP/quiet"; then
    echo "secret leaked into quiet artifacts" >&2; exit 1
fi
if find "$QWEN38_WORKSPACE" -name '*.log' | grep -q .; then
    echo "/workspace contains a runtime log" >&2; exit 1
fi
grep -Fq 'WEBUI_AUTH=True' "$RUNTIME_LOG_DIR/start-openwebui.sh"
grep -Fq 'ENABLE_SIGNUP=False' "$RUNTIME_LOG_DIR/start-openwebui.sh"
grep -Fq 'exec python3 -m sglang.launch_server' "$RUNTIME_LOG_DIR/start-sglang.sh"

echo '=== opt-in DEBUG diagnostics are redacted ==='
rm -rf "$RUNTIME_LOG_DIR" "$WEBUI_DATA_DIR"
DEBUG=1 bash "$ROOT/scripts/bootstrap-sglang-openwebui.sh" > "$TMP/debug" 2>&1
/bin/sleep 1
test -f "$RUNTIME_LOG_DIR/sglang.log"
test -f "$RUNTIME_LOG_DIR/openwebui.log"
grep -Fq '[REDACTED]' "$RUNTIME_LOG_DIR/sglang.log"
grep -Fq '[REDACTED]' "$RUNTIME_LOG_DIR/openwebui.log"
if grep -ER "SENTINEL_(API_KEY|HF_TOKEN|WEBUI_PASSWORD)" "$RUNTIME_LOG_DIR" "$TMP/debug"; then
    echo "secret leaked into DEBUG artifacts" >&2; exit 1
fi

echo '=== fail-closed public OpenWebUI missing admin ==='
rm -rf "$RUNTIME_LOG_DIR" "$WEBUI_DATA_DIR"
WEBUI_ADMIN_PASSWORD='' DEBUG=0 bash "$ROOT/scripts/bootstrap-sglang-openwebui.sh" > "$TMP/no-admin" 2>&1
test ! -e "$RUNTIME_LOG_DIR/start-openwebui.sh"
grep -Fq 'OpenWebUI disabled' "$TMP/no-admin"

echo '=== direct RunPod template contract ==='
bash "$ROOT/create-templates.sh" > "$TMP/templates-out" 2>&1
grep -Fq 'QWEN38_TEMPLATE=' "$TMP/templates-out"
grep -Fq 'QWEN38_TEMPLATE_PI=' "$TMP/templates-out"
python3 - "$TEST_TEMPLATE_FLAGS" <<'PY'
import json, sys
data=[json.loads(line) for line in open(sys.argv[1])]
assert len(data)==2
assert data[0]["ui"]=="1" and "8080/http" in data[0]["ports"]
assert data[1]["ui"]=="0" and "8080/http" not in data[1]["ports"]
PY

echo '=== launcher HF_TOKEN precedence and password provision ==='
export QWEN38_BOOTSTRAP="$ROOT/scripts/bootstrap-sglang-openwebui.sh"
export QWEN38_DEBUG=1
export TEST_EXPECTED_LAUNCH_HF="$HF_TOKEN"
mkdir -p "$HOME/.cache/huggingface"
echo 'SENTINEL_STALE_HF_FILE_5b' > "$HOME/.cache/huggingface/token"
if ! bash "$ROOT/bin/qwen38fast" > "$TMP/launcher-output" 2>&1; then
    echo "Launcher mock failed; sanitized diagnostic output:" >&2
    sed -E 's/SENTINEL_[A-Za-z0-9_]+/[REDACTED]/g; s/sk-qwen38-[A-Za-z0-9_-]+/[REDACTED]/g' "$TMP/launcher-output" >&2
    exit 1
fi
test -f "$TEST_LAUNCH_FLAGS"
unset HF_TOKEN
export TEST_EXPECTED_LAUNCH_HF='SENTINEL_STALE_HF_FILE_5b'
if ! bash "$ROOT/bin/qwen38fast" > "$TMP/launcher-fallback-output" 2>&1; then
    echo 'Launcher token-file fallback failed' >&2
    exit 1
fi
if grep -E "SENTINEL_(API_KEY|HF_TOKEN|WEBUI_PASSWORD|STALE_HF_FILE)" "$TMP/launcher-output" "$TMP/launcher-fallback-output"; then
    echo "launcher leaked a secret" >&2; exit 1
fi
echo '=== proxy never logs request paths or credentials ==='
python3 - "$ROOT/bin/qwen38-proxy" <<'PY'
import contextlib, importlib.machinery, io, os, sys, types
mod=types.ModuleType("qwen38_proxy_privacy_test")
importlib.machinery.SourceFileLoader(mod.__name__, sys.argv[1]).exec_module(mod)
buffer=io.StringIO()
os.environ["QWEN38_PROXY_VERBOSE"]="1"
with contextlib.redirect_stderr(buffer):
    mod.Handler.log_message(None, "%s", "Authorization: Bearer SENTINEL_PROXY_SECRET")
assert "SENTINEL_PROXY_SECRET" not in buffer.getvalue()
assert "HTTP exchange" in buffer.getvalue()
os.environ.pop("QWEN38_PROXY_VERBOSE", None)
buffer=io.StringIO()
with contextlib.redirect_stderr(buffer):
    mod.Handler.log_message(None, "%s", "SENTINEL_PROXY_SECRET")
assert buffer.getvalue()==""
PY
echo 'privacy regression suite passed'
