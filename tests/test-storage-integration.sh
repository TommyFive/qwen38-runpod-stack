#!/usr/bin/env bash
# Offline launcher / template smoke: partial Pod ENV overlays the template.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/home"
export QWEN38_TEST_REAL_PYTHON="$(command -v python3)"
cat > "$TMP/bin/python3" <<'PY_WRAPPER'
#!/usr/bin/env bash
if [[ "${1:-}" == */images/sglang-qwen38/tools/check-public.py ]]; then exit 0; fi
exec "$QWEN38_TEST_REAL_PYTHON" "$@"
PY_WRAPPER
chmod +x "$TMP/bin/python3"
export MOCK_OUTPUT_FILE="$TMP/env.jsonl"
cat > "$TMP/bin/runpodctl" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == pod && "${2:-}" == list ]]; then echo '[]'; exit; fi
if [[ "${1:-}" == pod && "${2:-}" == create && "${3:-}" == --help ]]; then
  echo '      --name string'; exit
fi
if [[ "${1:-}" == registry && "${2:-}" == list ]]; then
  echo '[{"id":"mock-ghcr","name":"ghcr.io"}]'; exit
fi
if [[ "${1:-}" == template && "${2:-}" == create ]]; then
  shift 2
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == --name ]]; then
      echo "{\"id\":\"mock-template\",\"name\":\"$2\"}"
      exit
    fi
    shift
  done
  exit 1
fi
if [[ "${1:-}" == template && "${2:-}" == get ]]; then
  python3 - "$3" <<'PY_GET'
import json,sys,os
rows=[json.loads(v) for v in open(os.environ["MOCK_OUTPUT_FILE"])]
tid=sys.argv[1]; lean=tid=="mock-pi"
env=rows[1 if lean else 0]
print(json.dumps({"id":tid,"imageName":"ghcr.io/tommyfive/qwen38-sglang@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7",
                  "env":env,"containerDiskInGb":30,
                  "ports":["8000/http"] if lean else ["8000/http","8080/http"]}))
PY_GET
  exit
fi
if [[ "${1:-}" == pod && "${2:-}" == create ]]; then
  shift 2
  python3 - "$@" <<'PY_POD'
import json,sys,os
args=sys.argv[1:]
rows=[json.loads(v) for v in open(os.environ["MOCK_OUTPUT_FILE"])]
tid=args[args.index("--template-id")+1]
env=dict(rows[1 if tid=="mock-pi" else 0])
if "--env" in args:env.update(json.loads(args[args.index("--env")+1]))
with open(os.environ["MOCK_OUTPUT_FILE"],"a") as out:out.write(json.dumps(env)+"\n")
print(json.dumps({"error":"test deliberately blocks deployment"}))
PY_POD
  exit
fi
if [[ "${1:-}" == template && "${2:-}" == update ]]; then
  action=$1; shift 2
  id="mock-template"
  if [[ "$action" == template ]]; then id="$1"; shift; fi
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == --env ]]; then
      printf '%s\n' "$2" >> "$MOCK_OUTPUT_FILE"
      if [[ "$action" == template ]]; then
        printf '{"id":"%s","env":%s}\n' "$id" "$2"
      else
        echo '{"error":"test deliberately blocks deployment"}'
      fi
      exit
    fi
    shift
  done
  exit 1
fi
echo "unexpected runpodctl operation: $*" >&2
exit 1
MOCK
cat > "$TMP/bin/ports-helper" <<'MOCK_PORTS'
#!/usr/bin/env python3
import sys
if sys.argv[1] == "preflight":
    assert len(sys.argv) == 2
    sys.exit(0)
assert len(sys.argv) == 4
assert sys.argv[1] == "repair"
assert sys.argv[2]
assert sys.argv[3] == "--delete-on-failure"
print("PASS: mocked zero-port verification", file=sys.stderr)
MOCK_PORTS
chmod +x "$TMP/bin/ports-helper"
export QWEN38_PORTS_HELPER="$TMP/bin/ports-helper"
chmod +x "$TMP/bin/runpodctl"
export HOME="$TMP/home" PATH="$ROOT/bin:$TMP/bin:$PATH" \
       RUNPODCTL_BIN="$TMP/bin/runpodctl" \
       QWEN38_TEMPLATE_RESOLVER="$ROOT/scripts/resolve-template-launch.py" \
       QWEN38_COLDSTART_TRACE=0

bash "$ROOT/create-templates.sh" > "$TMP/templates.out"
# Test benchmark/storage ENV independently of RunPod template-discovery code.
export QWEN38_TEMPLATE=mock-full QWEN38_TEMPLATE_PI=mock-pi
if QWEN38_MODEL_STORAGE=ram QWEN38_RAM_PEAK_FACTOR=1.75 qwen38fast --pi > "$TMP/pi.out" 2>&1; then
  echo 'ERROR: mock pod should never be deployed (pi)' >&2; exit 1
fi
if QWEN38_MODEL_STORAGE=ram QWEN38_MODEL_RAM_RELEASE_AFTER_LOAD=1 qwen38fast --pi > "$TMP/release.out" 2>&1; then
  echo 'ERROR: mock pod should never be deployed (release)' >&2; exit 1
fi
if QWEN38_MODEL_STORAGE=ssd qwen38fast --storage ssd > "$TMP/full.out" 2>&1; then
  echo 'ERROR: mock pod should never be deployed (full)' >&2; exit 1
fi
if QWEN38_MODEL_STORAGE=INVALID qwen38fast --pi > "$TMP/invalid.out" 2>&1; then
  echo 'ERROR: invalid storage mode accepted' >&2; exit 1
fi

grep -q 'MODEL_STORAGE must be ram or ssd' "$TMP/invalid.out"
# Safe diagnostics for mock-only failures (no runtime credentials).
if ! grep -q 'Starting qwen38pi' "$TMP/pi.out"; then
  echo "mock launcher was blocked before create:" >&2
  sed -n '1,14p' "$TMP/pi.out" >&2
fi
# Mock outputs below contain only nonsecret test data and launcher warnings.
if [[ $(wc -l < "$MOCK_OUTPUT_FILE") -eq 4 ]]; then
  echo "launcher output for diagnosis:" >&2
  tail -n 16 "$TMP/pi.out" >&2
  tail -n 8 "$TMP/full.out" >&2
fi
python3 - "$MOCK_OUTPUT_FILE" "$ROOT" <<'PY'
import base64, gzip, json, pathlib, sys
lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
envs = [json.loads(line) for line in lines]
assert len(envs) >= 4, f"wanted template + launcher objects: {len(envs)}"
assert all(e.get("TS_HOSTNAME")=="llm" for e in envs), "all template and CLI envs inherit llm"
expected_b = (pathlib.Path(sys.argv[2]) / 'scripts/bootstrap-sglang-openwebui.sh').read_bytes()
expected_h = (pathlib.Path(sys.argv[2]) / 'scripts/model-storage.py').read_bytes()
for env in envs:
    assert gzip.decompress(base64.b64decode(env['BOOTSTRAP_B64'])) == expected_b
    assert gzip.decompress(base64.b64decode(env['STORAGE_HELPER_B64'])) == expected_h
    assert env['MODEL_STORAGE'] in ('ram', 'ssd')
    assert env['MODEL_RAM_DIR'] == '/dev/shm/qwen38-hf'
    assert env['MODEL_SSD_DIR'] == '/workspace/hf'
    assert env['SPEC'] == 'dflash2'
assert {e['SERVE_WEBUI'] for e in envs} == {'0', '1'}
assert {e['MODEL_STORAGE'] for e in envs} == {'ram', 'ssd'}, [(e['MODEL_STORAGE'],e.get('MODEL_RAM_PEAK_FACTOR')) for e in envs]
assert any(e.get('MODEL_RAM_PEAK_FACTOR') == '1.75' for e in envs if e['MODEL_STORAGE'] == 'ram')
assert all('MODEL_RAM_PEAK_FACTOR' not in e for e in envs if e['MODEL_STORAGE'] == 'ssd')
assert all(e.get('MODEL_RAM_RELEASE_AFTER_LOAD', '0') in ('0','1') for e in envs)
assert any(e.get('MODEL_RAM_RELEASE_AFTER_LOAD') == '1' for e in envs)
assert all(e.get('MODEL_RAM_RELEASE_AFTER_LOAD', '0') == '0'
           for e in envs if e['MODEL_STORAGE'] == 'ssd')
print(f'model-storage launcher/template env: {len(envs)} checked, both modes and paths')
PY
