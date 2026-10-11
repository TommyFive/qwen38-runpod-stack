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
RESUME=0
[[ -z "${QWEN38_IMAGE_VARIANT+x}" ]] || IMAGE_SWITCH_EXPLICIT=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --resume) RESUME=1; shift ;;
    --image)
      [[ $# -ge 2 ]] || { echo "Usage: ./create-templates.sh --image custom|official" >&2; exit 64; }
      IMAGE_VARIANT="$2"; IMAGE_SWITCH_EXPLICIT=1; shift 2 ;;
    --help|-h)
      echo "Usage: ./create-templates.sh [--image custom|official] [--resume]"
      echo "Default: custom (immutable, GPU-tested GHCR minimal-v1)."
      echo "official: upstream lmsysorg/sglang:dev-qwen38-27b-dflash2."
      echo "--resume safely reuses matching templates, repairs tailnet ports, and creates missing ones."
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
# RAM-first models and the DFlash2 draft download to /dev/shm, not SSD.
# User-requested default: ALL four templates (Full/Lean × Public/Tailnet) 20 GiB.
# Only Custom Lean has been live-tested at 20 GiB so far; Full and official
# at this smaller capacity still need validation.
DEFAULT_DISK_GB=20
if [[ "$MODEL_STORAGE" == ssd ]]; then
  # Main/draft weights (~24 GiB) and caches need significantly more disk.
  # Switching to SSD at template creation automatically chooses 100 GiB.
  DEFAULT_DISK_GB=100
fi
FULL_DISK_GB="${QWEN38_FULL_DISK_GB:-$DEFAULT_DISK_GB}"
LEAN_DISK_GB="${QWEN38_LEAN_DISK_GB:-$DEFAULT_DISK_GB}"
for disk in "$FULL_DISK_GB" "$LEAN_DISK_GB"; do
  [[ "$disk" =~ ^[0-9]+$ ]] && ((10#$disk >= 20 && 10#$disk <= 500)) || {
    echo "Container disk must be between 20 and 500 GiB" >&2; exit 64;
  }
  if [[ "$MODEL_STORAGE" == ssd ]] && ((10#$disk < 50)); then
    echo "MODEL_STORAGE=ssd requires at least 50 GiB for BOTH Full and Lean; set QWEN38_FULL_DISK_GB and QWEN38_LEAN_DISK_GB (100 GiB default)." >&2
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
  python3 "$HERE/images/sglang-qwen38/check-public.py" --quiet || {
    echo "GHCR custom image is not yet anonymously pullable. Change Package settings -> Danger Zone -> Change visibility -> Public, then retry." >&2
    exit 1
  }
fi

# Fail before any remote mutation. An owned native config with mode 0644 is
# safely tightened to 0600; owner/type/symlink mismatches fail closed.
python3 "$PORTS_HELPER" preflight >&2 || {
  echo "RunPod port-hardening preflight failed; no templates created." >&2
  exit 1
}

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

  if [[ "$RESUME" == 1 ]]; then
    # List only user-owned templates. Never silently adopt a name collision or
    # overwrite stale/modified templates. Credentials were checked above.
    local existing_id existing_details
    existing_id=$(runpodctl template list --type user -o json 2>/dev/null | python3 -c 'import sys,json,re
name=sys.argv[1]
items=json.load(sys.stdin)
if not isinstance(items,list):
    sys.exit("Unexpected RunPod template list shape")
ids=[x.get("id") for x in items if isinstance(x,dict) and x.get("name")==name]
if len(ids)>1 or (ids and (not isinstance(ids[0],str) or not re.fullmatch(r"[A-Za-z0-9_.-]{5,100}",ids[0]))):
    sys.exit("Duplicate/invalid existing template IDs; resolve manually: "+name)
print(ids[0] if ids else "")
' "$1") || {
      echo "Could not safely list existing templates; stopped without creating $1." >&2
      return 1
    }
    if [[ -n "$existing_id" ]]; then
      existing_details=$(runpodctl template get "$existing_id" -o json 2>/dev/null) || {
        echo "Could not read existing template $existing_id; stopped." >&2
        return 1
      }
      # A stale template cannot be reused as a new configuration. Exact env
      # comparison includes embedded helper versions without printing secrets.
      if ! printf '%s' "$existing_details" | python3 -c 'import json,sys
tid,name,image,disk,env,mode,public_ports=sys.argv[1:]
try:
    d=json.load(sys.stdin)
    ports=d.get("ports",[])
    valid=(isinstance(d,dict) and d.get("id")==tid and d.get("name")==name
       and d.get("imageName")==image and d.get("containerDiskInGb")==int(disk)
       and d.get("env")==json.loads(env)
       and isinstance(ports,list))
    if mode=="runpod":
        valid=valid and ports==public_ports.split(",")
    if not valid:
        raise ValueError()
except (ValueError,TypeError,KeyError):
    sys.exit(1)
' "$existing_id" "$1" "$IMAGE" "$6" "$ENV" "$5" "$2"; then
        echo "Existing template $existing_id differs from requested image/disk/env/ports." >&2
        echo "Refusing to reuse or overwrite it. Inspect RunPod or use a different template name." >&2
        return 1
      fi
      if [[ "$5" == tailnet ]]; then
        # Also completes the previously interrupted repair, if needed.
        python3 "$PORTS_HELPER" repair "$existing_id" >&2 || {
          echo "Existing tailnet template $existing_id is NOT verified portless." >&2
          return 1
        }
      fi
      echo "Reusing verified template $existing_id ($1)" >&2
      printf '%s\n' "$existing_id"
      return 0
    fi
  fi

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
echo "No private GHCR registry credentials attached to new templates; public images pull anonymously."
echo "NOTE: 20 GiB defaults require MODEL_STORAGE=ram; SSD downloads need >=50 GiB, default 100 GiB."
echo "Switch source: ./create-templates.sh --image official|custom (creates distinct templates)."
echo "Recreate all four templates after each bootstrap/helper change."
