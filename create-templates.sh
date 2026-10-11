#!/usr/bin/env bash
# Create separate public and tailnet-only RunPod templates for chosen SGLang image.
# Never silently replace private templates with public port mappings.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BOOTSTRAP="$HERE/scripts/bootstrap-sglang-openwebui.sh"
TS_RUNTIME="$HERE/scripts/tailscale-runtime.sh"
STORAGE_HELPER="$HERE/scripts/model-storage.py"
BENCH_SCRIPT="$HERE/scripts/benchmark_sglang.py"
PORTS_HELPER="${QWEN38_PORTS_HELPER:-$HERE/scripts/private-template-ports.py}"
# Image selection applies only to newly created templates. No Pod is launched.
# Use --image official (or QWEN38_IMAGE_VARIANT=official) to retain upstream.
IMAGE_VARIANT="${QWEN38_IMAGE_VARIANT:-custom}"
IMAGE_SWITCH_EXPLICIT=0
[[ -z "${QWEN38_IMAGE_VARIANT+x}" ]] || IMAGE_SWITCH_EXPLICIT=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      [[ $# -ge 2 ]] || { echo "Usage: ./create-templates.sh --image custom|official" >&2; exit 64; }
      IMAGE_VARIANT="$2"; IMAGE_SWITCH_EXPLICIT=1; shift 2 ;;
    --help|-h)
      echo "Usage: ./create-templates.sh [--image custom|official]"
      echo "Default: custom (immutable, GPU-tested GHCR minimal-v1)."
      echo "official: upstream lmsysorg/sglang:dev-qwen38-27b-dflash2."
      echo "Also supports QWEN38_IMAGE_VARIANT and legacy QWEN38_IMAGE_REF."
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 64 ;;
  esac
done
MODEL_STORAGE="${QWEN38_MODEL_STORAGE:-ram}"
HF_SECRET_NAME="${QWEN38_HF_SECRET_NAME-HF_TOKEN}"
# Engine-neutral RunPod Secret name. Reuse the old Secret during migration with
# QWEN38_API_SECRET_NAME=LLAMA_API_KEY (does NOT alter the A40 project).
API_SECRET_NAME="${QWEN38_API_SECRET_NAME:-LLM_API_KEY}"
if [[ ! "$API_SECRET_NAME" =~ ^[A-Za-z][A-Za-z0-9_]*$ ]]; then
  echo "QWEN38_API_SECRET_NAME must be a nonempty RunPod secret identifier" >&2; exit 64
fi
if [[ -n "$HF_SECRET_NAME" && ! "$HF_SECRET_NAME" =~ ^[A-Za-z][A-Za-z0-9_]*$ ]]; then
  echo "QWEN38_HF_SECRET_NAME must be a valid RunPod secret name" >&2; exit 64
fi
MODEL_RAM_DIR="${QWEN38_MODEL_RAM_DIR:-/dev/shm/qwen38-hf}"
MODEL_SSD_DIR="${QWEN38_MODEL_SSD_DIR:-/workspace/hf}"
case "$MODEL_STORAGE" in ram|ssd) ;; *) echo "MODEL_STORAGE must be ram or ssd" >&2; exit 64 ;; esac
# Both choices preserve the Qwen38 authentication, model and network configuration.
CUSTOM_IMAGE="ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd"
OFFICIAL_IMAGE="lmsysorg/sglang:dev-qwen38-27b-dflash2"
if [[ -n "${QWEN38_IMAGE_REF:-}" ]]; then
  case "$QWEN38_IMAGE_REF" in
    "$CUSTOM_IMAGE") ref_variant=custom ;;
    "$OFFICIAL_IMAGE") ref_variant=official ;;
    *) echo "QWEN38_IMAGE_REF must be the pinned custom digest or the approved upstream image" >&2; exit 64 ;;
  esac
  if [[ "$IMAGE_SWITCH_EXPLICIT" == 1 && "$IMAGE_VARIANT" != "$ref_variant" ]]; then
    echo "Conflicting image selectors: --image/QWEN38_IMAGE_VARIANT vs QWEN38_IMAGE_REF" >&2; exit 64
  fi
  IMAGE_VARIANT="$ref_variant"
fi
case "$IMAGE_VARIANT" in
  custom) IMAGE="$CUSTOM_IMAGE"; TEMPLATE_PREFIX="qwen38-v0.2.0" ;;
  official) IMAGE="$OFFICIAL_IMAGE"; TEMPLATE_PREFIX="qwen38-official" ;;
  *) echo "Image must be custom or official" >&2; exit 64 ;;
esac
MODEL="${QWEN38_MODEL:-sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4}"
FULL_DISK_GB="${QWEN38_FULL_DISK_GB:-150}"  # Full OpenWebUI not yet GPU validated at reduced disk
# Only the custom Lean image has completed a 20-GiB live test.
LEAN_DISK_DEFAULT=20
[[ "$IMAGE_VARIANT" != official ]] || LEAN_DISK_DEFAULT=150
LEAN_DISK_GB="${QWEN38_LEAN_DISK_GB:-$LEAN_DISK_DEFAULT}"
if [[ "$MODEL_STORAGE" == ssd && "$LEAN_DISK_GB" == 20 ]]; then
  LEAN_DISK_GB=150  # SSD checkpoint fallback must not silently use RAM-mode disk limit
fi
for disk in "$FULL_DISK_GB" "$LEAN_DISK_GB"; do
  [[ "$disk" =~ ^[0-9]+$ ]] && ((10#$disk >= 20 && 10#$disk <= 500)) || {
    echo "Container disk must be between 20 and 500 GiB" >&2; exit 64;
  }
done
if [[ "$MODEL_STORAGE" == ssd ]] && ((10#$LEAN_DISK_GB < 50)); then
  echo "SSD checkpoint mode needs at least 50 GiB container disk" >&2; exit 64
fi

REGISTRY_AUTH_ID=""
if [[ "$IMAGE_VARIANT" == custom ]]; then
  # Never expose GHCR credentials. Only the existing registry-auth ID is read.
  REGISTRY_AUTH_ID=$(runpodctl registry list -o json | python3 -c 'import sys,json
found=[x.get("id") for x in json.load(sys.stdin) if x.get("name")=="ghcr.io"]
if len(found)!=1 or not isinstance(found[0],str) or not found[0]:
    sys.exit("Expected one private ghcr.io registry credential")
print(found[0])') || {
    echo "GHCR registry credential unavailable; refusing private image template" >&2; exit 1;
  }
fi

mk() { # name ports labels serve_webui network_mode disk_gib
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
    "MODEL_RAM_RELEASE_AFTER_LOAD":"0",
    "DEBUG":"0", "COLDSTART_TRACE":"1",
    "RUNTIME_LOG_DIR":"/dev/shm/qwen38-runtime",
    "SGLANG_API_KEY":"{{ RUNPOD_SECRET_"+sys.argv[12]+" }}",
    **({"TS_AUTHKEY":"{{ RUNPOD_SECRET_TS_AUTHKEY }}"} if sys.argv[5]=="tailnet" else {}),
    **({"HF_TOKEN":"{{ RUNPOD_SECRET_"+sys.argv[11]+" }}"} if sys.argv[11] else {})
  }))' "$BS" "$TS" "$MODEL" "$4" "$5" "$SH" "$BENCH" "$MODEL_STORAGE" "$MODEL_RAM_DIR" "$MODEL_SSD_DIR" "$HF_SECRET_NAME" "$API_SECRET_NAME")

  # CLI/backend may reject large --env on CREATE (observed HTTP 500).
  # Provision no-secret skeleton then UPDATE only that new template.
  # The bootstrap command fails closed until BOOTSTRAP_B64 is installed.
  local args=(template create --name "$1" --image "$IMAGE" --container-disk-in-gb "$6")
  [[ -z "$REGISTRY_AUTH_ID" ]] || args+=(--registry-auth-id "$REGISTRY_AUTH_ID")
  if [[ "$5" == runpod ]]; then
    args+=(--ports "$2" --port-labels "$3")
  fi
  args+=(--docker-start-cmd 'bash,-c,umask 077; echo "$BOOTSTRAP_B64" | base64 -d > /bootstrap.sh && bash /bootstrap.sh' -o json)
  local template_id
  template_id=$(runpodctl "${args[@]}" 2>/dev/null | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
    assert d.get("id") and d.get("name")==sys.argv[1]
    print(d["id"])
except (ValueError,KeyError,TypeError,AssertionError):
    sys.exit("RunPod skeleton creation failed (response suppressed)")' "$1") || return 1

  local updated
  if ! updated=$(runpodctl template update "$template_id" --env "$ENV" -o json 2>/dev/null); then
    echo "Failed to configure new template; deleting partial template $template_id" >&2
    runpodctl template delete "$template_id" >/dev/null 2>&1 || true
    return 1
  fi
  if ! printf '%s' "$updated" | python3 -c 'import sys,json
d=json.load(sys.stdin)
if d.get("id")!=sys.argv[1] or d.get("env",{}).get("COLDSTART_TRACE")!="1" or d.get("env",{}).get("SGLANG_API_KEY","").startswith("{{ RUNPOD_SECRET_") is False:
    raise SystemExit(1)
' "$template_id"; then
    echo "Template env verification failed; deleting $template_id" >&2
    runpodctl template delete "$template_id" >/dev/null 2>&1 || true
    return 1
  fi
  if [[ "$5" == tailnet ]]; then
    # Omitted --ports may publish 8888/http + 22/tcp by provider default.
    # The existing helper PATCHes [] and independently verifies it.
    python3 "$PORTS_HELPER" repair "$template_id" --delete-on-failure >&2 || return 1
  fi
  printf '%s\n' "$template_id"
}

echo "Full $IMAGE_VARIANT template (SGLang + OpenWebUI, PUBLIC RunPod ports):"
id=$(mk ${TEMPLATE_PREFIX}-full-public \
  '8000/http,8080/http,22/tcp' '8000=SGLang API,8080=OpenWebUI,22=SSH' 1 runpod "$FULL_DISK_GB")
echo "  QWEN38_TEMPLATE=$id"
echo "Lean $IMAGE_VARIANT template (SGLang API, PUBLIC RunPod ports):"
id=$(mk ${TEMPLATE_PREFIX}-lean-public \
  '8000/http,22/tcp' '8000=SGLang API,22=SSH' 0 runpod "$LEAN_DISK_GB")
echo "  QWEN38_TEMPLATE_PI=$id"
echo "Full tailnet-only template (NO published RunPod ports):"
id=$(mk ${TEMPLATE_PREFIX}-full-tailnet \
  '' '' 1 tailnet "$FULL_DISK_GB")
echo "  QWEN38_TEMPLATE_TAILNET=$id"
echo "Lean tailnet-only template (NO published RunPod ports):"
id=$(mk ${TEMPLATE_PREFIX}-lean-tailnet \
  '' '' 0 tailnet "$LEAN_DISK_GB")
echo "  QWEN38_TEMPLATE_TAILNET_PI=$id"
echo "For tailnet-only templates, verify 'runpodctl template get <id>' has NO public ports."
echo "Private templates reference existing RunPod Secret TS_AUTHKEY; all templates reference $API_SECRET_NAME for SGLang."
echo "All templates reference RunPod Secret HF_TOKEN by default (override QWEN38_HF_SECRET_NAME)."
echo "Direct template-only launches require SGLANG_API_KEY and, for public OpenWebUI,"
echo "WEBUI_ADMIN_EMAIL plus WEBUI_ADMIN_PASSWORD (>=16 chars) in pod environment."
echo "With no credentials, the bootstrap fails closed instead of exposing an open API."
echo "Image variant: $IMAGE_VARIANT; image: $IMAGE; disk Full=$FULL_DISK_GB GiB / Lean=$LEAN_DISK_GB GiB."
echo "Switch source: ./create-templates.sh --image official|custom (creates distinct templates)."
echo "Recreate all four templates after each bootstrap/helper change."
