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
#   MODEL_STORAGE   ram (default) | ssd. RAM preflight fails closed.
#   MODEL_RAM_DIR   /dev/shm/qwen38-hf (must reside on tmpfs)
#   MODEL_SSD_DIR   /workspace/hf (persistent volume)
#   STORAGE_HELPER_B64  bundled scripts/model-storage.py
#   HF_TOKEN        optional, only needed for gated repos
#   SGLANG_API_KEY  optional, locks the public proxy endpoint down
#   SERVE_WEBUI     1 (default) also runs OpenWebUI on :8080; 0 = SGLang only,
#                   the lean path for a coding agent like pi that talks the API
#   ENABLE_SSH      1 starts sshd for debugging; 0 (default) leaves SSH disabled
set -uo pipefail

MODEL_ID="${MODEL_ID:?MODEL_ID missing}"
SERVED_NAME="${SERVED_NAME:-qwen38-uncensored}"
MAX_LEN="${MAX_LEN:-262144}"
SPEC="${SPEC:-dflash2}"
MEM_FRAC="${MEM_FRAC:-0.85}"
MAMBA_RATIO="${MAMBA_RATIO:-4.59}"
API_KEY="${SGLANG_API_KEY:-}"
SERVE_WEBUI="${SERVE_WEBUI:-1}"
ENABLE_SSH="${ENABLE_SSH:-0}"

mkdir -p /workspace
LOG=/workspace/bootstrap.log
exec > >(tee -a "$LOG") 2>&1
echo "=== bootstrap $(date -u +%FT%TZ) ==="
echo "model=$MODEL_ID spec=$SPEC max_len=$MAX_LEN mem_frac=$MEM_FRAC"

# --- Early SSH access -----------------------------------------------------
# RunPod injects the account's registered SSH keys through PUBLIC_KEY.  The
# SGLang image does not start sshd itself, so bring it up before downloads and
# model initialization.  Keep the workload running if SSH setup fails; the
# reason remains visible in the bootstrap log and RunPod console.
start_ssh() {
    local sshd_bin

    if [[ -z "${PUBLIC_KEY:-}" ]]; then
        echo "WARNING: PUBLIC_KEY is empty; SSH will not be enabled"
        return 1
    fi

    sshd_bin=$(command -v sshd 2>/dev/null || true)
    [[ -z "$sshd_bin" && -x /usr/sbin/sshd ]] && sshd_bin=/usr/sbin/sshd
    if [[ -z "$sshd_bin" ]]; then
        echo "Installing openssh-server"
        if ! command -v apt-get >/dev/null 2>&1; then
            echo "ERROR: sshd is missing and apt-get is unavailable"
            return 1
        fi
        if ! apt-get update -qq || \
           ! DEBIAN_FRONTEND=noninteractive apt-get install \
               -y -qq --no-install-recommends openssh-server; then
            echo "ERROR: openssh-server installation failed"
            return 1
        fi
        hash -r
        sshd_bin=$(command -v sshd 2>/dev/null || true)
        [[ -z "$sshd_bin" && -x /usr/sbin/sshd ]] && sshd_bin=/usr/sbin/sshd
    fi

    if [[ -z "$sshd_bin" ]]; then
        echo "ERROR: sshd is still unavailable after installation"
        return 1
    fi

    install -d -m 700 /root/.ssh
    install -d -m 755 /run/sshd
    printf '%s\n' "$PUBLIC_KEY" | tr -d '\r' > /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys

    if [[ ! -s /root/.ssh/authorized_keys ]]; then
        echo "ERROR: authorized_keys is empty"
        return 1
    fi

    ssh-keygen -A
    cat > /tmp/runpod-sshd.conf <<'SSHD_CONFIG'
Port 22
ListenAddress 0.0.0.0
HostKey /etc/ssh/ssh_host_ed25519_key
HostKey /etc/ssh/ssh_host_rsa_key
AuthorizedKeysFile /root/.ssh/authorized_keys
PermitRootLogin prohibit-password
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
UsePAM no
PidFile /run/sshd.pid
LogLevel VERBOSE
SSHD_CONFIG

    if ! "$sshd_bin" -t -f /tmp/runpod-sshd.conf; then
        echo "ERROR: SSH daemon configuration is invalid"
        return 1
    fi
    if ! "$sshd_bin" -f /tmp/runpod-sshd.conf -E /workspace/sshd.log; then
        echo "ERROR: SSH daemon failed to start"
        return 1
    fi

    echo "SSH_READY $(date -u +%FT%TZ)"
    ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
}

if [[ "$ENABLE_SSH" == "1" ]]; then
    echo "--- early SSH initialization"
    start_ssh || echo "WARNING: continuing bootstrap without SSH"
else
    echo "--- SSH disabled (set ENABLE_SSH=1 to enable)"
fi

# A separate, version-matched storage helper is embedded by BOTH launch paths.
# Only small bootstrap logs/scripts live on /workspace; model weights, all HF
# caches and HF/Xet temporary files live on the verified selected filesystem.
if [[ -z "${STORAGE_HELPER_B64:-}" ]]; then
  echo "ERROR: STORAGE_HELPER_B64 is required; recreate the RunPod template or update the launcher" >&2
  exit 64
fi
if ! printf '%s' "$STORAGE_HELPER_B64" | base64 -d > /workspace/model-storage.py; then
  echo "ERROR: unable to unpack storage helper" >&2
  exit 64
fi
chmod 600 /workspace/model-storage.py
if ! python3 /workspace/model-storage.py prepare > /workspace/model-storage-env.sh; then
  echo "ERROR: storage preflight failed before downloading any checkpoint" >&2
  exit 64
fi
# shellcheck source=/dev/null
source /workspace/model-storage-env.sh
rm -f /workspace/model-storage-env.sh
[[ -n "${HF_TOKEN:-}" ]] && export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"
echo "model_storage=${MODEL_STORAGE:-ram} hf_home=$HF_HOME"

# Local-only GPU smoke/audit; no network changes and no credentials printed.
cat > /workspace/smoke-storage.sh <<'SMOKE'
#!/usr/bin/env bash
set -euo pipefail
storage="${MODEL_STORAGE:-ram}"
if [[ "$storage" == ram ]]; then
  root="${MODEL_RAM_DIR:-/dev/shm/qwen38-hf}"
else
  root="${MODEL_SSD_DIR:-/workspace/hf}"
fi
echo '=== STORAGE AUDIT (all snapshots and symlinks) ==='
python3 /workspace/model-storage.py audit
echo '=== MOUNT NAMESPACE ==='
cat /proc/self/mountinfo
echo '=== FREE SPACE / CACHE SIZE ==='
df -B1 "$root" /workspace
du -sh "$root" "$root"/hub "$root"/xet 2>/dev/null || true
echo '=== PROCESS RSS (KiB) ==='
ps -eo pid,rss,comm,args | grep -E 'PID|sglang|python3' | head -n 30 || true
echo '=== SGLANG READINESS ==='
headers=()
[[ -n "${SGLANG_API_KEY:-}" ]] && headers=(-H "Authorization: Bearer ${SGLANG_API_KEY}")
curl --fail --silent --show-error --max-time 30 "${headers[@]}" http://127.0.0.1:8000/v1/models |
  python3 -c 'import json,sys; d=json.load(sys.stdin); models=[x["id"] for x in d["data"]]; print("ready:",models); assert models'
SMOKE
chmod 700 /workspace/smoke-storage.sh

nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader || true

# Network sanity check. A broken host looks exactly like a config bug and
# costs hours at the wrong end. Anything under 10 MB/s means throw the pod away.
echo "--- network check"
SPEED=$(curl -s -o /dev/null -w '%{speed_download}' --max-time 20 \
    https://huggingface.co/Qwen/Qwen3.8-27B-FP8/resolve/main/config.json 2>/dev/null || echo 0)
echo "download probe: $(python3 -c "print(f'{float('${SPEED:-0}')/1e6:.1f} MB/s')" 2>/dev/null || echo '?')"

# Both packages are preinstalled in the SGLang image. Never use pip to change
# the live SGLang/PyTorch/NCCL environment during bootstrap.
if ! python3 -c 'import huggingface_hub, hf_xet'; then
  echo "ERROR: Hugging Face Hub/Xet missing from the SGLang image" >&2
  exit 1
fi

echo "--- fetching main and any speculative draft checkpoints"
if ! python3 /workspace/model-storage.py download; then
  echo "ERROR: checkpoint download or storage verification failed" >&2
  exit 64
fi
MODEL_PATH=$(cat /workspace/model_path)
DRAFT_PATH=""
[[ -f /workspace/draft_path ]] && DRAFT_PATH=$(cat /workspace/draft_path)
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
                    --speculative-draft-model-path "$DRAFT_PATH"
                    --speculative-num-draft-tokens 8)
        ;;
    dspark)
        SPEC_FLAGS=(--speculative-algorithm DSPARK
                    --speculative-draft-model-path "$DRAFT_PATH")
        ;;
    none)
        SPEC_FLAGS=()
        ;;
    *)
        echo "ERROR: unknown SPEC=$SPEC" >&2
        exit 64
        ;;
esac

# Generated runtime scripts must retain the same cache paths even when
# restarted from SSH (outside the bootstrap's environment).
RUNTIME_STORAGE_ENV=$(for name in HF_HOME HF_HUB_CACHE HF_XET_CACHE HF_ASSETS_CACHE HF_DATASETS_CACHE XDG_CACHE_HOME TORCH_HOME TMPDIR HF_XET_HIGH_PERFORMANCE; do
  printf 'export %s=%q\\n' "$name" "${!name}"
done)
cat > /workspace/start-sglang.sh <<EOF
#!/usr/bin/env bash
$RUNTIME_STORAGE_ENV
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
  WEBUI_VENV=/workspace/openwebui-venv
  WEBUI_VERSION="${OPENWEBUI_VERSION:-0.11.4}"
  cat > /workspace/start-openwebui.sh <<EOF
#!/usr/bin/env bash
$RUNTIME_STORAGE_ENV
export DATA_DIR=/workspace/openwebui
export OPENAI_API_BASE_URL=http://127.0.0.1:8000/v1
export OPENAI_API_KEY=${API_KEY:-EMPTY}
export WEBUI_AUTH=False
export ENABLE_OLLAMA_API=False
exec "$WEBUI_VENV/bin/open-webui" serve --host 0.0.0.0 --port 8080
EOF
  chmod +x /workspace/start-openwebui.sh
  # Use a separate Python environment: an unpinned pip install into the
  # running SGLang environment can replace its PyTorch/NCCL shared libraries
  # while the scheduler imports DeepEP, leading to a '(deleted)' NCCL crash.
  # uv ships with the SGLang image and does not require ensurepip in the venv.
  echo "--- installing OpenWebUI ${WEBUI_VERSION} in isolated environment"
  if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv missing; OpenWebUI disabled (SGLang unaffected)" >&2
  elif uv venv --python /usr/bin/python3 "$WEBUI_VENV" &&
       uv pip install --python "$WEBUI_VENV/bin/python" "open-webui==$WEBUI_VERSION"; then
    setsid /workspace/start-openwebui.sh > /workspace/openwebui.log 2>&1 < /dev/null &
    disown
  else
    echo "ERROR: OpenWebUI installation failed; SGLang remains running" >&2
  fi
else
  echo "--- SERVE_WEBUI=0, skipping OpenWebUI, SGLang API only"
fi

echo "=== bootstrap done, SGLang is loading weights ==="
sleep infinity
