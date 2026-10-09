#!/usr/bin/env bash
# Create separate public (legacy) and tailnet-only RunPod templates.
# Never silently replace private templates with public port mappings.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BOOTSTRAP="$HERE/scripts/bootstrap-sglang-openwebui.sh"
TS_RUNTIME="$HERE/scripts/tailscale-runtime.sh"
STORAGE_HELPER="$HERE/scripts/model-storage.py"
BENCH_SCRIPT="$HERE/scripts/benchmark_sglang.py"
MODEL_STORAGE="${QWEN38_MODEL_STORAGE:-ram}"
MODEL_RAM_DIR="${QWEN38_MODEL_RAM_DIR:-/dev/shm/qwen38-hf}"
MODEL_SSD_DIR="${QWEN38_MODEL_SSD_DIR:-/workspace/hf}"
case "$MODEL_STORAGE" in ram|ssd) ;; *) echo "MODEL_STORAGE must be ram or ssd" >&2; exit 64 ;; esac
IMAGE="lmsysorg/sglang:dev-qwen38-27b-dflash2"
MODEL="${QWEN38_MODEL:-sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4}"

mk() { # name ports labels serve_webui network_mode
  local BS TS SH BENCH ENV
  BS=$(base64 -i "$BOOTSTRAP" | tr -d '\n')
  TS=$(base64 -i "$TS_RUNTIME" | tr -d '\n')
  SH=$(base64 -i "$STORAGE_HELPER" | tr -d '\n')
  BENCH=$(base64 -i "$BENCH_SCRIPT" | tr -d '\n')
  ENV=$(python3 -c 'import json,sys; print(json.dumps({
    "BOOTSTRAP_B64":sys.argv[1],
    "TAILSCALE_RUNTIME_B64":sys.argv[2],
    "MODEL_ID":sys.argv[3], "SERVED_NAME":"qwen38-uncensored",
    "MAX_LEN":"262144", "SPEC":"dflash2", "MEM_FRAC":"0.85",
    "MAMBA_RATIO":"4.59", "SERVE_WEBUI":sys.argv[4],
    "ENABLE_SSH":"0", "NETWORK_MODE":sys.argv[5], "TS_ENABLE_SSH":"1",
    "STORAGE_HELPER_B64":sys.argv[6], "BENCHMARK_B64":sys.argv[7],
    "MODEL_STORAGE":sys.argv[8], "MODEL_RAM_DIR":sys.argv[9],
    "MODEL_SSD_DIR":sys.argv[10], "BENCHMARK":"0",
    "DEBUG":"0", "COLDSTART_TRACE":"1",
    "RUNTIME_LOG_DIR":"/dev/shm/qwen38-runtime"
  }))' "$BS" "$TS" "$MODEL" "$4" "$5" "$SH" "$BENCH" "$MODEL_STORAGE" "$MODEL_RAM_DIR" "$MODEL_SSD_DIR")

  local args=(template create --name "$1" --image "$IMAGE" --container-disk-in-gb 150)
  # Tailnet-only: never publish container ports through the RunPod proxy.
  # Do not pass --ports or --port-labels to create private templates.
  if [[ "$5" == runpod ]]; then
    args+=(--ports "$2" --port-labels "$3")
  fi
  args+=(--docker-start-cmd 'bash,-c,umask 077; echo "$BOOTSTRAP_B64" | base64 -d > /bootstrap.sh && bash /bootstrap.sh' --env "$ENV" -o json)
  runpodctl "${args[@]}" 2>&1 | python3 -c 'import sys,json
raw=sys.stdin.read()
try:
    d=json.loads(raw[raw.index("{"):])
    if "id" not in d or "error" in d: raise ValueError()
    print(d["id"])
except (ValueError,KeyError,TypeError):
    print("ERROR: template create failed; raw output suppressed to protect credentials",file=sys.stderr)
    sys.exit(1)'
}

echo "Full legacy template (SGLang + OpenWebUI, PUBLIC RunPod ports):"
echo "  QWEN38_TEMPLATE=$(mk qwen38-uncensored-sglang-nvfp4 \
  '8000/http,8080/http,22/tcp' '8000=SGLang API,8080=OpenWebUI,22=SSH' 1 runpod)"
echo "Lean legacy template (SGLang API, PUBLIC RunPod ports):"
echo "  QWEN38_TEMPLATE_PI=$(mk qwen38-uncensored-pi-sglang \
  '8000/http,22/tcp' '8000=SGLang API,22=SSH' 0 runpod)"
echo "Full tailnet-only template (NO published RunPod ports):"
echo "  QWEN38_TEMPLATE_TAILNET=$(mk qwen38-uncensored-tailnet \
  '' '' 1 tailnet)"
echo "Lean tailnet-only template (NO published RunPod ports):"
echo "  QWEN38_TEMPLATE_TAILNET_PI=$(mk qwen38-uncensored-tailnet-pi \
  '' '' 0 tailnet)"
echo "For tailnet-only templates, verify 'runpodctl template get <id>' has NO public ports."
echo "Configure TS_AUTHKEY for private launches (never commit credentials)."
echo "Direct template-only launches require SGLANG_API_KEY and, for public OpenWebUI,"
echo "WEBUI_ADMIN_EMAIL plus WEBUI_ADMIN_PASSWORD (>=16 chars) in pod environment."
echo "With no credentials, the bootstrap fails closed instead of exposing an open API."
echo "Recreate all four templates after each bootstrap/helper change."
