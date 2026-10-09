#!/usr/bin/env bash
# Offline launcher / template smoke: --env replaces every template variable.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/home"
export MOCK_OUTPUT_FILE="$TMP/env.jsonl"
cat > "$TMP/bin/runpodctl" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == pod && "${2:-}" == list ]]; then echo '[]'; exit; fi
if [[ "${1:-}" == pod && "${2:-}" == create && "${3:-}" == --help ]]; then
  echo '      --name string'; exit
fi
if [[ "${1:-}" == template && "${2:-}" == create ]] ||
   [[ "${1:-}" == pod && "${2:-}" == create ]]; then
  action=$1; shift 2
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == --env ]]; then
      printf '%s\n' "$2" >> "$MOCK_OUTPUT_FILE"
      break
    fi
    shift
  done
  if [[ "$action" == template ]]; then echo '{"id":"mock-template"}'; else
    echo '{"error":"test deliberately blocks deployment"}'
  fi
  exit
fi
echo "unexpected runpodctl operation: $*" >&2
exit 1
MOCK
chmod +x "$TMP/bin/runpodctl"
export HOME="$TMP/home" PATH="$ROOT/bin:$TMP/bin:$PATH" \
       RUNPODCTL_BIN="$TMP/bin/runpodctl" \
       QWEN38_BOOTSTRAP="$ROOT/scripts/bootstrap-sglang-openwebui.sh" \
       QWEN38_STORAGE_HELPER="$ROOT/scripts/model-storage.py"

bash "$ROOT/create-templates.sh" > "$TMP/templates.out"
if QWEN38_MODEL_STORAGE=ram qwen38fast --pi > "$TMP/pi.out" 2>&1; then
  echo 'ERROR: mock pod should never be deployed (pi)' >&2; exit 1
fi
if QWEN38_MODEL_STORAGE=ssd qwen38fast --storage ssd > "$TMP/full.out" 2>&1; then
  echo 'ERROR: mock pod should never be deployed (full)' >&2; exit 1
fi
if QWEN38_MODEL_STORAGE=INVALID qwen38fast --pi > "$TMP/invalid.out" 2>&1; then
  echo 'ERROR: invalid storage mode accepted' >&2; exit 1
fi

grep -q 'MODEL_STORAGE must be ram or ssd' "$TMP/invalid.out"
python3 - "$MOCK_OUTPUT_FILE" "$ROOT" <<'PY'
import base64, json, pathlib, sys
lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
envs = [json.loads(line) for line in lines]
assert len(envs) >= 4, f"wanted template + launcher objects: {len(envs)}"
expected_b = (pathlib.Path(sys.argv[2]) / 'scripts/bootstrap-sglang-openwebui.sh').read_bytes()
expected_h = (pathlib.Path(sys.argv[2]) / 'scripts/model-storage.py').read_bytes()
for env in envs:
    assert base64.b64decode(env['BOOTSTRAP_B64']) == expected_b
    assert base64.b64decode(env['STORAGE_HELPER_B64']) == expected_h
    assert env['MODEL_STORAGE'] in ('ram', 'ssd')
    assert env['MODEL_RAM_DIR'] == '/dev/shm/qwen38-hf'
    assert env['MODEL_SSD_DIR'] == '/workspace/hf'
    assert env['SPEC'] == 'dflash2'
assert {e['SERVE_WEBUI'] for e in envs} == {'0', '1'}
assert {e['MODEL_STORAGE'] for e in envs} == {'ram', 'ssd'}
print(f'model-storage launcher/template env: {len(envs)} checked, both modes and paths')
PY
