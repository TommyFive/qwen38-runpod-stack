#!/usr/bin/env bash
# create-templates.sh - creates the two RunPod templates that qwen38fast needs.
# Afterwards set the printed ids:
#   export QWEN38_TEMPLATE=<full-id>
#   export QWEN38_TEMPLATE_PI=<pi-id>
# or hardcode them as defaults in bin/qwen38fast.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BOOTSTRAP="$HERE/scripts/bootstrap-sglang-openwebui.sh"
STORAGE_HELPER="$HERE/scripts/model-storage.py"
MODEL_STORAGE="${QWEN38_MODEL_STORAGE:-ram}"
MODEL_RAM_DIR="${QWEN38_MODEL_RAM_DIR:-/dev/shm/qwen38-hf}"
MODEL_SSD_DIR="${QWEN38_MODEL_SSD_DIR:-/workspace/hf}"
case "$MODEL_STORAGE" in
  ram|ssd) ;;
  *) echo "MODEL_STORAGE must be ram or ssd" >&2; exit 64 ;;
esac
IMAGE="lmsysorg/sglang:dev-qwen38-27b-dflash2"
MODEL="${QWEN38_MODEL:-sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4}"

mk() { # name  ports  port_labels  serve_webui
  local BS SH ENV
  BS=$(base64 -i "$BOOTSTRAP")
  SH=$(base64 -i "$STORAGE_HELPER")
  ENV=$(python3 -c "import json,sys;print(json.dumps({
    'BOOTSTRAP_B64': sys.argv[1], 'STORAGE_HELPER_B64': sys.argv[4],
    'MODEL_STORAGE': sys.argv[5], 'MODEL_RAM_DIR': sys.argv[6], 'MODEL_SSD_DIR': sys.argv[7],
    'MODEL_ID': sys.argv[2], 'SERVED_NAME': 'qwen38-uncensored',
    'MAX_LEN':'262144','SPEC':'dflash2','MEM_FRAC':'0.85','MAMBA_RATIO':'4.59','SERVE_WEBUI': sys.argv[3],'ENABLE_SSH':'0'}))" "$BS" "$MODEL" "$4" "$SH" "$MODEL_STORAGE" "$MODEL_RAM_DIR" "$MODEL_SSD_DIR")
  runpodctl template create --name "$1" --image "$IMAGE" \
    --container-disk-in-gb 150 --ports "$2" --port-labels "$3" \
    --docker-start-cmd 'bash,-c,echo "$BOOTSTRAP_B64" | base64 -d > /bootstrap.sh && bash /bootstrap.sh' \
    --env "$ENV" -o json | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('id') or d)"
}

echo "Full template (SGLang + OpenWebUI):"
echo "  QWEN38_TEMPLATE=$(mk qwen38-uncensored-sglang-nvfp4 \
  '8000/http,8080/http,22/tcp' '8000=SGLang API,8080=OpenWebUI,22=SSH' 1)"
echo "pi template (SGLang API only):"
echo "  QWEN38_TEMPLATE_PI=$(mk qwen38-uncensored-pi-sglang \
  '8000/http,22/tcp' '8000=SGLang API,22=SSH' 0)"
