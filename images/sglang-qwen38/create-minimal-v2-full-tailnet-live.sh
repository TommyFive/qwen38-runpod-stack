#!/usr/bin/env bash
# Candidate-only, isolated Full Tailnet template. No paid pod is ever started.
set -Eeuo pipefail
set +x
umask 077
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CREATE=0
CANDIDATE=b
for arg in "$@"; do
  case "$arg" in
    --candidate=b) CANDIDATE=b ;;
    --candidate=a) CANDIDATE=a ;;
    --candidate=v1) CANDIDATE=v1 ;;
    --create) CREATE=1 ;;
    --help|-h) echo "Usage: $0 [--candidate=b|a|v1] [--create] (default dry-run; never starts a paid pod)"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 64 ;;
  esac
done
case "$CANDIDATE" in
  b) IMAGE="ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7" ;;
  a) IMAGE="ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint@sha256:ec013c2e20528a92d61b6a7a0352ba081e166ef99025a5fbb4be06572381bb1e" ;;
  v1) IMAGE="ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd" ;;
esac
NAME="qwen38-gpulive-20261012-$CANDIDATE-full-tailnet-bench5-debug"
DISK_GB="${QWEN38_LIVE_DISK_GB:-30}"
[[ "$DISK_GB" =~ ^[0-9]+$ ]] && ((10#$DISK_GB >= 20 && 10#$DISK_GB <= 150)) || {
  echo "QWEN38_LIVE_DISK_GB must be 20..150 GiB" >&2; exit 64;
}
API_SECRET="${QWEN38_API_SECRET_NAME:-LLAMA_API_KEY}"
WEBUI_SECRET="${QWEN38_LIVE_WEBUI_PASSWORD_SECRET:-QWEN38_WEBUI_ADMIN_PASSWORD}"
HF_SECRET="${QWEN38_HF_SECRET_NAME:-HF_TOKEN}"
for v in "$API_SECRET" "$WEBUI_SECRET" "$HF_SECRET"; do
  [[ "$v" =~ ^[A-Za-z][A-Za-z0-9_]*$ ]] || {
    echo "Invalid RunPod secret name" >&2; exit 64;
  }
done
[[ "$WEBUI_SECRET" != "$API_SECRET" && "$WEBUI_SECRET" != "$HF_SECRET" ]] || {
  echo "OpenWebUI password must be a separate RunPod Secret" >&2; exit 64;
}
ADMIN_EMAIL="${QWEN38_LIVE_WEBUI_ADMIN_EMAIL:-admin@qwen38.example.com}"
[[ "$ADMIN_EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || {
  echo "Invalid WebUI administrator email" >&2; exit 64;
}
BOOTSTRAP="$ROOT/scripts/bootstrap-sglang-openwebui.sh"
TS="$ROOT/scripts/tailscale-runtime.sh"
STORAGE="$ROOT/scripts/model-storage.py"
BENCH="$ROOT/scripts/benchmark_sglang.py"
PORTS="$ROOT/scripts/private-template-ports.py"
for path in "$BOOTSTRAP" "$TS" "$STORAGE" "$BENCH" "$PORTS"; do
  [[ -f "$path" && -r "$path" ]] || { echo "Missing input $path" >&2; exit 64; }
done
# All credentials are references to existing provider secrets, not values.
ENV_JSON="$(python3 - "$BOOTSTRAP" "$TS" "$STORAGE" "$BENCH" "$API_SECRET" "$WEBUI_SECRET" "$HF_SECRET" "$ADMIN_EMAIL" <<'PY'
import base64,json,pathlib,sys
bootstrap,ts,storage,bench,api,webui,hf,email=sys.argv[1:]
def b64(path):
    return base64.b64encode(pathlib.Path(path).read_bytes()).decode()
def ref(name):
    return "{{ RUNPOD_SECRET_"+name+" }}"
env={
 "BOOTSTRAP_B64":b64(bootstrap), "TAILSCALE_RUNTIME_B64":b64(ts),
 "STORAGE_HELPER_B64":b64(storage), "BENCHMARK_B64":b64(bench),
 "MODEL_ID":"sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4",
 "SERVED_NAME":"qwen38-uncensored","MAX_LEN":"262144","SPEC":"dflash2",
 "MEM_FRAC":"0.85","MAMBA_RATIO":"4.59","SERVE_WEBUI":"1",
 "ENABLE_SSH":"0","NETWORK_MODE":"tailnet","TS_ENABLE_SSH":"1",
 "MODEL_STORAGE":"ram","MODEL_RAM_DIR":"/dev/shm/qwen38-hf",
 "MODEL_SSD_DIR":"/workspace/hf","MODEL_RAM_RELEASE_AFTER_LOAD":"0",
 "RUNTIME_LOG_DIR":"/dev/shm/qwen38-runtime","COLDSTART_TRACE":"1",
 "BENCHMARK":"1","BENCHMARK_BLOCKING":"1",
 "BENCHMARK_RUNS":"5","BENCHMARK_MAX_TOKENS":"512",
 "BENCHMARK_TIMEOUT_SECONDS":"1800",
 "BENCHMARK_REPORT_PATH":"/dev/shm/qwen38-runtime/benchmark.json",
 "DEBUG":"1","SGLANG_API_KEY":ref(api),"TS_AUTHKEY":ref("TS_AUTHKEY"),
 "HF_TOKEN":ref(hf),"WEBUI_ADMIN_EMAIL":email,
 "WEBUI_ADMIN_PASSWORD":ref(webui)
}
print(json.dumps(env,separators=(",",":"),sort_keys=True))
PY
)"
echo "GPU live Full Tailnet template: $NAME"
echo "Image $IMAGE"
echo "No public ports; $DISK_GB GiB RAM-first; Full OpenWebUI"
echo "BENCHMARK=1 BENCHMARK_BLOCKING=1 DEBUG=1, 3 workloads x (1 warmup + 5 measured), 512 max tokens, timeout 1800s"
echo "RunPod secrets required BEFORE launching: $API_SECRET, TS_AUTHKEY, $HF_SECRET, $WEBUI_SECRET"
if [[ "$CREATE" != 1 ]]; then
  echo "DRY RUN: no RunPod API mutation and no paid pod."
  exit 0
fi
RUNPODCTL="${QWEN38_RUNPODCTL:-}"
if [[ -z "$RUNPODCTL" ]]; then RUNPODCTL="$(command -v runpodctl || true)"; fi
if [[ -z "$RUNPODCTL" && -x /opt/homebrew/bin/runpodctl ]]; then
  RUNPODCTL=/opt/homebrew/bin/runpodctl
fi
[[ -n "$RUNPODCTL" && -x "$RUNPODCTL" ]] || { echo "runpodctl unavailable" >&2; exit 64; }
python3 "$PORTS" preflight >&2 || { echo "API credentials failed preflight; no template made" >&2; exit 1; }
EXISTING="$("$RUNPODCTL" template list --type user -o json | python3 -c '
import json,sys
data=json.load(sys.stdin)
if not isinstance(data,list):raise SystemExit("Invalid template list")
hits=[x.get("id") for x in data if isinstance(x,dict) and x.get("name")==sys.argv[1]]
if any(not x for x in hits):raise SystemExit("Invalid existing ID")
print(" ".join(hits))
' "$NAME")" || exit 1
[[ -z "$EXISTING" ]] || { echo "Refusing name collision $NAME (nothing changed)" >&2; exit 1; }
# RunPod intermittently rejects large ENV payloads on CREATE. Create an isolated
# no-secret skeleton, then UPDATE its ID only. Defaults may expose RunPod ports;
# patch [] and validate BEFORE allowing a GPU launch.
ID="$("$RUNPODCTL" template create --name "$NAME" \
    --image "$IMAGE" --container-disk-in-gb "$DISK_GB" \
    --docker-start-cmd 'bash,-c,umask 077; echo "$BOOTSTRAP_B64" | base64 -d > /bootstrap.sh && bash /bootstrap.sh' \
    -o json 2>/dev/null | python3 -c '
import json,re,sys
d=json.load(sys.stdin)
v=d.get("id")
if not isinstance(v,str) or not re.fullmatch(r"[A-Za-z0-9_-]{5,64}",v):
    raise SystemExit("Invalid new template ID")
print(v)
')" || { echo "RunPod skeleton creation failed" >&2; exit 1; }
cleanup() {
  echo "Cleaning up ONLY incomplete new template $ID" >&2
  "$RUNPODCTL" template delete "$ID" >/dev/null 2>&1 || true
}
if ! "$RUNPODCTL" template update "$ID" --env "$ENV_JSON" -o json >/dev/null 2>&1; then
  cleanup; echo "Template env update failed" >&2; exit 1
fi
if ! python3 "$PORTS" repair "$ID" >&2; then
  cleanup; echo "Port hardening failed" >&2; exit 1
fi
if ! "$RUNPODCTL" template get "$ID" -o json | python3 -c '
import json,sys
tid,name,image,disk,expected=sys.argv[1:]
d=json.load(sys.stdin)
env=d.get("env")
assert d.get("id")==tid and d.get("name")==name
assert d.get("imageName")==image and d.get("containerDiskInGb")==int(disk)
assert isinstance(env,dict) and env==json.loads(expected)
assert d.get("ports",[])==[] and not d.get("portsConfig")
assert not d.get("containerRegistryAuthId")
' "$ID" "$NAME" "$IMAGE" "$DISK_GB" "$ENV_JSON"; then
  cleanup; echo "Final template verification failed" >&2; exit 1
fi
echo "ISOLATED_FULL_TAILNET_TEMPLATE_VERIFIED id=$ID candidate=$CANDIDATE"
echo "NO PAID POD CREATED. Paid GPU deployment requires separate approval."
