#!/usr/bin/env bash
# bootstrap-sglang-openwebui.sh
#
# Runs INSIDE a RunPod pod that already uses an SGLang image.
# Brings up SGLang (OpenAI API on :8000) plus OpenWebUI (:8080) for a
# Blackwell-class GPU serving an NVFP4 checkpoint with speculative decoding.
#
# Env contract (all set by the pod template / launcher):
#   MODEL_ID        HF repo of the target checkpoint (NVFP4, uniform pack-quantized)
#   SERVED_NAME     name the OpenAI API reports
#   MAX_LEN         context length
#   SPEC            none | mtp | dflash2 | dspark
#   MEM_FRAC        --mem-fraction-static
#   MAMBA_RATIO     --mamba-full-memory-ratio
#   HF_TOKEN        optional, only needed for gated repos
#   SGLANG_API_KEY  optional, locks the public proxy endpoint down
#   SERVE_WEBUI     1 (default) also runs OpenWebUI on :8080; 0 = SGLang only,
#                   the lean path for a coding agent like pi that talks the API
set -uo pipefail

MODEL_ID="${MODEL_ID:?MODEL_ID missing}"
SERVED_NAME="${SERVED_NAME:-qwen38-uncensored}"
MAX_LEN="${MAX_LEN:-262144}"
SPEC="${SPEC:-dflash2}"
MEM_FRAC="${MEM_FRAC:-0.85}"
MAMBA_RATIO="${MAMBA_RATIO:-4.59}"
API_KEY="${SGLANG_API_KEY:-}"
SERVE_WEBUI="${SERVE_WEBUI:-1}"

LOG=/workspace/bootstrap.log
exec > >(tee -a "$LOG") 2>&1
echo "=== bootstrap $(date -u +%FT%TZ) ==="
echo "model=$MODEL_ID spec=$SPEC max_len=$MAX_LEN mem_frac=$MEM_FRAC"

export HF_HOME=/workspace/hf
export HF_HUB_ENABLE_HF_TRANSFER=1
mkdir -p "$HF_HOME" /workspace
[[ -n "${HF_TOKEN:-}" ]] && export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"

nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader || true

# Network sanity check. A broken host looks exactly like a config bug and
# costs hours at the wrong end. Anything under 10 MB/s means throw the pod away.
echo "--- network check"
SPEED=$(curl -s -o /dev/null -w '%{speed_download}' --max-time 20 \
    https://huggingface.co/Qwen/Qwen3.8-27B-FP8/resolve/main/config.json 2>/dev/null || echo 0)
echo "download probe: $(python3 -c "print(f'{float('${SPEED:-0}')/1e6:.1f} MB/s')" 2>/dev/null || echo '?')"

# hf_transfer gives multi-connection downloads, worth ~3x on a 20 GB checkpoint.
pip install -q hf_transfer huggingface_hub 2>&1 | tail -2

echo "--- fetching weights"
python3 - <<PY
import os
from huggingface_hub import snapshot_download
p = snapshot_download(
    "${MODEL_ID}",
    max_workers=16,
    token=os.environ.get("HUGGING_FACE_HUB_TOKEN"),
)
open("/workspace/model_path", "w").write(p)
print("downloaded to", p)
PY
MODEL_PATH=$(cat /workspace/model_path)
du -sh "$MODEL_PATH" || true

# --- speculative decoding flags -------------------------------------------
# MTP rides in the checkpoint itself. DFlash2 and DSpark need a separate
# trained draft checkpoint; both are Apache 2.0 and public.
case "$SPEC" in
    mtp)
        SPEC_FLAGS=(--speculative-algorithm EAGLE
                    --speculative-num-steps 3
                    --speculative-eagle-topk 1
                    --speculative-num-draft-tokens 4)
        ;;
    dflash2)
        SPEC_FLAGS=(--speculative-algorithm DFLASH
                    --speculative-draft-model-path incoai/Qwen3.8-27B-DFlash2
                    --speculative-num-draft-tokens 8)
        ;;
    dspark)
        SPEC_FLAGS=(--speculative-algorithm DSPARK
                    --speculative-draft-model-path RadixArk/Qwen3.8-27B-DSpark)
        ;;
    none|*)
        SPEC_FLAGS=()
        ;;
esac

cat > /workspace/start-sglang.sh <<EOF
#!/usr/bin/env bash
export HF_HOME=/workspace/hf
export HF_HUB_ENABLE_HF_TRANSFER=1
${HF_TOKEN:+export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"}
exec python3 -m sglang.launch_server \\
  --model-path "$MODEL_PATH" \\
  --served-model-name "$SERVED_NAME" \\
  --trust-remote-code \\
  --context-length $MAX_LEN \\
  --mem-fraction-static $MEM_FRAC \\
  --attention-backend flashinfer \\
  --chunked-prefill-size 2048 \\
  --max-prefill-tokens 32768 \\
  --reasoning-parser qwen3 \\
  --tool-call-parser qwen3_coder \\
  --mamba-full-memory-ratio $MAMBA_RATIO \\
  --mamba-radix-cache-strategy extra_buffer \\
  --mamba-ssm-dtype float32 \\
  ${SPEC_FLAGS[@]+"${SPEC_FLAGS[@]}"} \\
  ${API_KEY:+--api-key "$API_KEY"} \\
  --host 0.0.0.0 --port 8000
EOF
chmod +x /workspace/start-sglang.sh

echo "--- starting SGLang"
setsid /workspace/start-sglang.sh > /workspace/sglang.log 2>&1 < /dev/null &
disown

if [[ "$SERVE_WEBUI" == "1" ]]; then
  # OpenWebUI caches its model list at startup, so it has to come up AFTER
  # the API answers. The launcher restarts it anyway once the model is live.
  cat > /workspace/start-openwebui.sh <<EOF
#!/usr/bin/env bash
export DATA_DIR=/workspace/openwebui
export OPENAI_API_BASE_URL=http://127.0.0.1:8000/v1
export OPENAI_API_KEY=${API_KEY:-EMPTY}
export WEBUI_AUTH=False
export ENABLE_OLLAMA_API=False
exec open-webui serve --host 0.0.0.0 --port 8080
EOF
  chmod +x /workspace/start-openwebui.sh
  pip install -q open-webui 2>&1 | tail -2
  setsid /workspace/start-openwebui.sh > /workspace/openwebui.log 2>&1 < /dev/null &
  disown
else
  echo "--- SERVE_WEBUI=0, skipping OpenWebUI, SGLang API only"
fi

echo "=== bootstrap done, SGLang is loading weights ==="
sleep infinity
