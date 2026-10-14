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
      echo "Default: custom (GPU-tested GHCR minimal-v2 B v0.2.2)."
      echo "official: upstream lmsysorg/sglang:dev-qwen38-27b-dflash2."
      echo "Also supports QWEN38_IMAGE_VARIANT and legacy QWEN38_IMAGE_REF."
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 64 ;;
  esac
done
MODEL_STORAGE="${QWEN38_MODEL_STORAGE:-ram}"
WEBUI_PASSWORD_SECRET_NAME="${QWEN38_WEBUI_PASSWORD_SECRET_NAME:-QWEN38_WEBUI_ADMIN_PASSWORD}"
WEBUI_ADMIN_EMAIL="${QWEN38_WEBUI_ADMIN_EMAIL:-admin@qwen38.example.com}"
[[ "$WEBUI_PASSWORD_SECRET_NAME" =~ ^[A-Za-z][A-Za-z0-9_]*$ ]] || { echo "Invalid WEBUI password secret name" >&2; exit 64; }
[[ "$WEBUI_ADMIN_EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]] || { echo "Invalid WEBUI admin email" >&2; exit 64; }
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
CUSTOM_IMAGE="ghcr.io/tommyfive/qwen38-sglang@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7"
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
  custom) IMAGE="$CUSTOM_IMAGE"; TEMPLATE_PREFIX="qwen38-v0.2.2" ;;
  official) IMAGE="$OFFICIAL_IMAGE"; TEMPLATE_PREFIX="qwen38-official" ;;
  *) echo "Image must be custom or official" >&2; exit 64 ;;
esac
MODEL="${QWEN38_MODEL:-sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4}"
# RAM-first models and the DFlash2 draft download to /dev/shm, not SSD.
# 30 GiB GPU-tested for minimal-v2 B Full and Lean (official keeps 20 GiB).
DEFAULT_DISK_GB=20
[[ "$IMAGE_VARIANT" == custom ]] && DEFAULT_DISK_GB=30
if [[ "$MODEL_STORAGE" == ssd ]]; then
  # Main/draft weights (~24 GiB) and caches need significantly more disk.
  # Switching to SSD at template creation automatically chooses 150 GiB.
  DEFAULT_DISK_GB=150
fi
FULL_DISK_GB="${QWEN38_FULL_DISK_GB:-$DEFAULT_DISK_GB}"
LEAN_DISK_GB="${QWEN38_LEAN_DISK_GB:-$DEFAULT_DISK_GB}"
for disk in "$FULL_DISK_GB" "$LEAN_DISK_GB"; do
  [[ "$disk" =~ ^[0-9]+$ ]] && ((10#$disk >= 20 && 10#$disk <= 500)) || {
    echo "Container disk must be between 20 and 500 GiB" >&2; exit 64;
  }
  if [[ "$MODEL_STORAGE" == ssd ]] && ((10#$disk < 50)); then
    echo "MODEL_STORAGE=ssd requires at least 50 GiB for BOTH Full and Lean; set QWEN38_FULL_DISK_GB and QWEN38_LEAN_DISK_GB (150 GiB recommended)." >&2
    exit 64
  fi
done
if [[ "$MODEL_STORAGE" == ssd ]]; then
  echo "SSD model download enabled: $FULL_DISK_GB GiB Full / $LEAN_DISK_GB GiB Lean (20 GiB is RAM-first only)." >&2
fi

# The released Custom image is intended for PUBLIC GHCR access.
# New templates never embed an account-specific registry-auth ID. Existing
# older private-registry templates are intentionally not touched here.
# If GHCR is still private, stop before creating unusable test templates.
if [[ "$IMAGE_VARIANT" == custom ]]; then
  python3 "$HERE/images/sglang-qwen38/tools/check-public.py" --quiet || {
    echo "GHCR custom image is not yet anonymously pullable. Change Package settings -> Danger Zone -> Change visibility -> Public, then retry." >&2
    exit 1
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
    "TS_HOSTNAME":"llm",  # Default Tailscale hostname for generated templates, not the RunPod Pod name.
    "STORAGE_HELPER_B64":sys.argv[6], "BENCHMARK_B64":sys.argv[7],
    "MODEL_STORAGE":sys.argv[8], "MODEL_RAM_DIR":sys.argv[9],
    "MODEL_SSD_DIR":sys.argv[10], "BENCHMARK":"0",
    "MODEL_RAM_RELEASE_AFTER_LOAD":"0",
    "DEBUG":"0", "COLDSTART_TRACE":"1",
    "RUNTIME_LOG_DIR":"/dev/shm/qwen38-runtime",
    "SGLANG_API_KEY":"{{ RUNPOD_SECRET_"+sys.argv[12]+" }}",
    **({"WEBUI_ADMIN_EMAIL":sys.argv[13], "WEBUI_ADMIN_PASSWORD":"{{ RUNPOD_SECRET_"+sys.argv[14]+" }}"} if sys.argv[4]=="1" else {}),
    **({"TS_AUTHKEY":"{{ RUNPOD_SECRET_TS_AUTHKEY }}"} if sys.argv[5]=="tailnet" else {}),
    **({"HF_TOKEN":"{{ RUNPOD_SECRET_"+sys.argv[11]+" }}"} if sys.argv[11] else {})
  }))' "$BS" "$TS" "$MODEL" "$4" "$5" "$SH" "$BENCH" "$MODEL_STORAGE" "$MODEL_RAM_DIR" "$MODEL_SSD_DIR" "$HF_SECRET_NAME" "$API_SECRET_NAME" "$WEBUI_ADMIN_EMAIL" "$WEBUI_PASSWORD_SECRET_NAME")

  # CLI/backend may reject large --env on CREATE (observed HTTP 500).
  # Provision no-secret skeleton then UPDATE only that new template.
  # The bootstrap command fails closed until BOOTSTRAP_B64 is installed.
  local args=(template create --name "$1" --image "$IMAGE" --container-disk-in-gb "$6")
  # Both official upstream and public Custom image pull anonymously.
  # No per-account ghcr.io registry credentials in newly shared templates.
  if [[ "$5" == runpod ]]; then
    args+=(--ports "$2" --port-labels "$3")
  fi
  args+=(--docker-start-cmd 'bash,-c,umask 077; echo "$BOOTSTRAP_B64" | base64 -d > /bootstrap.sh && bash /bootstrap.sh' -o json)
  local template_id="" attempt
  # Provider CREATE can fail transiently. Retry only when the name is absent.
  for attempt in 1 2 3; do
    if template_id=$(runpodctl "${args[@]}" 2>/dev/null | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
    assert d.get("id") and d.get("name")==sys.argv[1]
    print(d["id"])
except (ValueError,KeyError,TypeError,AssertionError):
    sys.exit("RunPod skeleton creation failed (response suppressed)")
' "$1"); then
      break
    fi
    template_id=""
    if ! runpodctl template list --type user -o json | python3 -c 'import json,sys
items=json.load(sys.stdin)
name=sys.argv[1]
sys.exit(1 if any(x.get("name")==name for x in items) else 0)
' "$1"; then
      echo "Template $1 may already exist after a provider error; refusing duplicate creation" >&2
      return 1
    fi
    if [[ "$attempt" == 3 ]]; then
      echo "Template creation failed after 3 verified no-duplicate attempts" >&2
      return 1
    fi
    sleep 2
  done
  [[ -n "$template_id" ]] || return 1

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
  '8000/http,8080/http' '8000=SGLang API,8080=OpenWebUI' 1 runpod "$FULL_DISK_GB")
echo "  QWEN38_TEMPLATE=$id"
echo "Lean $IMAGE_VARIANT template (SGLang API, PUBLIC RunPod ports):"
id=$(mk ${TEMPLATE_PREFIX}-lean-public \
  '8000/http' '8000=SGLang API' 0 runpod "$LEAN_DISK_GB")
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
echo "Full templates use RunPod Secret $WEBUI_PASSWORD_SECRET_NAME and WEBUI_ADMIN_EMAIL."
echo "Resolved admin passwords must be >=16 characters; otherwise Full fails closed."
echo "With no credentials, the bootstrap fails closed instead of exposing an open API."
echo "Image variant: $IMAGE_VARIANT; image: $IMAGE; disk Full=$FULL_DISK_GB GiB / Lean=$LEAN_DISK_GB GiB."
echo "No private GHCR registry credentials attached to new templates; public images pull anonymously."
echo "NOTE: Custom RAM-first defaults to 30 GiB; SSD downloads need >=50 GiB, default 150 GiB."
echo "Switch source: ./create-templates.sh --image official|custom (creates distinct templates)."
echo "Recreate all four templates after each bootstrap/helper change."
