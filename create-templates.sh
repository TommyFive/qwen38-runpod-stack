#!/usr/bin/env bash
# create-templates.sh - legt die zwei RunPod-Templates an, die qwen38fast braucht.
# Danach die ausgegebenen IDs setzen:
#   export QWEN38_TEMPLATE=<voll-id>
#   export QWEN38_TEMPLATE_PI=<pi-id>
# oder direkt in bin/qwen38fast als Default eintragen.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BOOTSTRAP="$HERE/scripts/bootstrap-sglang-openwebui.sh"
IMAGE="lmsysorg/sglang:dev-qwen38-27b-dflash2"
MODEL="${QWEN38_MODEL:-sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4}"

mk() { # name  ports  serve_webui
  local BS ENV
  BS=$(base64 -i "$BOOTSTRAP")
  ENV=$(python3 -c "import json,sys;print(json.dumps({
    'BOOTSTRAP_B64': sys.argv[1], 'MODEL_ID': sys.argv[2], 'SERVED_NAME': 'qwen38-uncensored',
    'MAX_LEN':'262144','SPEC':'dflash2','MEM_FRAC':'0.85','MAMBA_RATIO':'4.59','SERVE_WEBUI': sys.argv[3]}))" "$BS" "$MODEL" "$3")
  runpodctl template create --name "$1" --image "$IMAGE" \
    --container-disk-in-gb 150 --ports "$2" \
    --docker-start-cmd 'bash,-c,echo "$BOOTSTRAP_B64" | base64 -d > /bootstrap.sh && bash /bootstrap.sh' \
    --env "$ENV" -o json | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('id') or d)"
}

echo "Voll-Template (SGLang + OpenWebUI):"
echo "  QWEN38_TEMPLATE=$(mk qwen38-uncensored-sglang-nvfp4 '8000/http,8080/http,22/tcp' 1)"
echo "pi-Template (nur SGLang API):"
echo "  QWEN38_TEMPLATE_PI=$(mk qwen38-uncensored-pi-sglang '8000/http,22/tcp' 0)"
