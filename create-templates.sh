#!/usr/bin/env bash
# Create separate public (legacy) and tailnet-only RunPod templates.
# Never silently replace private templates with public port mappings.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BOOTSTRAP="$HERE/scripts/bootstrap-sglang-openwebui.sh"
TS_RUNTIME="$HERE/scripts/tailscale-runtime.sh"
IMAGE="lmsysorg/sglang:dev-qwen38-27b-dflash2"
MODEL="${QWEN38_MODEL:-sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4}"

mk() { # name ports labels serve_webui network_mode
  local BS TS ENV
  BS=$(base64 -i "$BOOTSTRAP" | tr -d '\n')
  TS=$(base64 -i "$TS_RUNTIME" | tr -d '\n')
  ENV=$(python3 -c 'import json,sys; print(json.dumps({
    "BOOTSTRAP_B64":sys.argv[1], "TAILSCALE_RUNTIME_B64":sys.argv[2],
    "MODEL_ID":sys.argv[3], "SERVED_NAME":"qwen38-uncensored",
    "MAX_LEN":"262144", "SPEC":"dflash2", "MEM_FRAC":"0.85",
    "MAMBA_RATIO":"4.59", "SERVE_WEBUI":sys.argv[4],
    "ENABLE_SSH":"0", "NETWORK_MODE":sys.argv[5], "TS_ENABLE_SSH":"1"
  }))' "$BS" "$TS" "$MODEL" "$4" "$5")

  local args=(template create --name "$1" --image "$IMAGE" --container-disk-in-gb 150)
  # Tailnet-only: never publish container ports through the RunPod proxy.
  # Do not pass --ports or --port-labels to create private templates.
  if [[ "$5" == runpod ]]; then
    args+=(--ports "$2" --port-labels "$3")
  fi
  args+=(--docker-start-cmd 'bash,-c,umask 077; echo "$BOOTSTRAP_B64" | base64 -d > /bootstrap.sh && bash /bootstrap.sh' --env "$ENV" -o json)
  runpodctl "${args[@]}" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("id") or d)'
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
echo "Configure TS_AUTHKEY as a RunPod secret for template-only launches."
