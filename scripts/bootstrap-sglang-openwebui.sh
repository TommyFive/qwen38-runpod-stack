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
#   ENABLE_SSH      1 starts legacy OpenSSH; 0 disables it
#   NETWORK_MODE   runpod | tailnet (loopback and Tailscale Serve only)
#   TAILSCALE_RUNTIME_B64 optional bundled native SSH userspace helper
#   STORAGE_HELPER_B64 required bundled RAM/SSD cache helper
#   MODEL_STORAGE   ram (default), ssd opt-in
#   BENCHMARK       0 (default), 1 bounded authenticated offline benchmark
#   BENCHMARK_B64   bundled Python benchmark when enabled
#   COLDSTART_TRACE 1 (default), 0 disables timing milestones
set -uo pipefail
# Never trace inherited RunPod secrets, even if the caller invoked bash -x.
set +x
umask 077
DEBUG="${DEBUG:-0}"
[[ "$DEBUG" == 0 || "$DEBUG" == 1 ]] || { echo "ERROR: DEBUG must be 0 or 1" >&2; exit 64; }
SERVE_WEBUI="${SERVE_WEBUI:-1}"
[[ "$SERVE_WEBUI" == 0 || "$SERVE_WEBUI" == 1 ]] || { echo "ERROR: SERVE_WEBUI must be 0 or 1" >&2; exit 64; }
NETWORK_MODE="${NETWORK_MODE:-runpod}"
[[ "$NETWORK_MODE" == runpod || "$NETWORK_MODE" == tailnet ]] || { echo "ERROR: NETWORK_MODE must be runpod or tailnet" >&2; exit 64; }
# Issue #7 initializes Tailscale later, before the SSH and model phases.
# Validate its completed connection below rather than blocking startup here.
[[ -n "${SGLANG_API_KEY:-}" ]] || { echo "ERROR: SGLANG_API_KEY required (no unauthenticated public API)" >&2; exit 64; }
API_BIND_HOST=0.0.0.0
WEBUI_BIND_HOST=0.0.0.0
if [[ "$NETWORK_MODE" == tailnet ]]; then
    API_BIND_HOST=127.0.0.1
    WEBUI_BIND_HOST=127.0.0.1
fi
RUNTIME_LOG_DIR="${RUNTIME_LOG_DIR:-/dev/shm/qwen38-runtime}"
# Check the mounted filesystem after directory creation: /tmp and /workspace
# are often overlayfs and can survive pod/container restarts.
install -d -m 700 "$RUNTIME_LOG_DIR" || exit 70
chmod 700 "$RUNTIME_LOG_DIR"
if [[ "$(stat -f -c %T "$RUNTIME_LOG_DIR" 2>/dev/null)" != tmpfs &&
      "${ALLOW_PERSISTENT_RUNTIME_LOGS:-0}" != 1 ]]; then
    echo "ERROR: RUNTIME_LOG_DIR must be tmpfs unless ALLOW_PERSISTENT_RUNTIME_LOGS=1" >&2
    exit 70
fi
WEBUI_DATA_DIR="${WEBUI_DATA_DIR:-/dev/shm/qwen38-webui-data}"
install -d -m 700 "$WEBUI_DATA_DIR" || exit 70
chmod 700 "$WEBUI_DATA_DIR"
if [[ "$(stat -f -c %T "$WEBUI_DATA_DIR" 2>/dev/null)" != tmpfs &&
      "${ALLOW_PERSISTENT_WEBUI_DATA:-0}" != 1 ]]; then
    echo "ERROR: WEBUI_DATA_DIR must be tmpfs unless ALLOW_PERSISTENT_WEBUI_DATA=1" >&2
    exit 70
fi
export DEBUG RUNTIME_LOG_DIR WEBUI_DATA_DIR API_BIND_HOST WEBUI_BIND_HOST NETWORK_MODE SERVE_WEBUI
# One streaming redactor for console/bootstrap and opt-in child diagnostics.
# No raw stdout/stderr is written to disk before passing through this filter.
cat > "$RUNTIME_LOG_DIR/redact-log.py" <<'REDACTOR'
import os
import re
import sys

secrets = sorted({os.environ.get(k, "") for k in (
    "SGLANG_API_KEY", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN",
    "WEBUI_ADMIN_PASSWORD", "TS_AUTHKEY", "OPENAI_API_KEY"
) if os.environ.get(k, "")}, key=len, reverse=True)
allow = re.compile(r"^(===|---|ERROR:|WARNING:|SSH_READY|SSH disabled|TAILSCALE:|QWEN38_COLDSTART |QWEN38_STORAGE_METRIC|Benchmark |MODEL STORAGE ERROR:|Storage mode:|RAM mode verified:|model=|download probe:|GPU:|privacy:)")
for line in sys.stdin:
    for secret in secrets:
        line = line.replace(secret, "[REDACTED]")
    line = re.sub(r"(?i)(Authorization\s*:\s*Bearer\s+)\S+", r"\1[REDACTED]", line)
    line = re.sub(r"(?i)(token|api[_-]?key|password)=\S+", r"\1=[REDACTED]", line)
    if os.environ.get("DEBUG", "0") == "1" or allow.match(line):
        print(line, end="", flush=True)
REDACTOR
LOG="$RUNTIME_LOG_DIR/bootstrap.log"
exec > >(python3 -u "$RUNTIME_LOG_DIR/redact-log.py" | tee -a "$LOG") 2>&1

MODEL_ID="${MODEL_ID:?MODEL_ID missing}"
SERVED_NAME="${SERVED_NAME:-qwen38-uncensored}"
MAX_LEN="${MAX_LEN:-262144}"
SPEC="${SPEC:-dflash2}"
MEM_FRAC="${MEM_FRAC:-0.85}"
MAMBA_RATIO="${MAMBA_RATIO:-4.59}"
API_KEY="${SGLANG_API_KEY}"
ENABLE_SSH="${ENABLE_SSH:-0}"
BENCHMARK="${BENCHMARK:-0}"
COLDSTART_TRACE="${COLDSTART_TRACE:-1}"
[[ "$BENCHMARK" == 0 || "$BENCHMARK" == 1 ]] || { echo "ERROR: BENCHMARK must be 0 or 1" >&2; exit 64; }
[[ "$COLDSTART_TRACE" == 0 || "$COLDSTART_TRACE" == 1 ]] || { echo "ERROR: COLDSTART_TRACE must be 0 or 1" >&2; exit 64; }
cold_mark() {
    [[ "$COLDSTART_TRACE" == 1 ]] || return 0
    python3 - "$1" <<'PY_COLD'
import datetime, json, sys, time
print("QWEN38_COLDSTART " + json.dumps({"schema": 1, "event":sys.argv[1],
    "source":"pod","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z"),
    "mono":round(time.monotonic(),6)}, separators=(",",":")), flush=True)
PY_COLD
}
cold_mark bootstrap_start

echo "=== bootstrap $(date -u +%FT%TZ) ==="
echo "model=$MODEL_ID spec=$SPEC max_len=$MAX_LEN mem_frac=$MEM_FRAC"

# --- Optional native Tailscale SSH and HTTPS Serve (no TCP/22 forwarding) ----
if [[ -n "${TAILSCALE_RUNTIME_B64:-}" ]]; then
    if ! printf '%s' "$TAILSCALE_RUNTIME_B64" | base64 -d > "$RUNTIME_LOG_DIR/tailscale-runtime.sh"; then
        echo "ERROR: invalid TAILSCALE_RUNTIME_B64" >&2
        exit 70
    fi
    unset TAILSCALE_RUNTIME_B64
    # shellcheck source=tailscale-runtime.sh
    # Tailscale's userspace socket, binaries and diagnostic files remain on tmpfs.
    export TS_RUNTIME_DIR="$RUNTIME_LOG_DIR/tailscale"
    source "$RUNTIME_LOG_DIR/tailscale-runtime.sh"
    if ! ts_start; then
        if [[ "$NETWORK_MODE" == tailnet ]]; then
            echo "ERROR: Tailscale enrollment required for tailnet mode" >&2
            exit 70
        fi
        echo "WARNING: optional Tailscale unavailable; public RunPod mode unchanged" >&2
    fi
    if ! ts_serve; then
        if [[ "$NETWORK_MODE" == tailnet ]]; then
            echo "ERROR: tailnet-only mode requires Tailscale Serve" >&2
            exit 70
        fi
        echo "WARNING: Tailscale Serve unavailable" >&2
    fi
elif [[ "$NETWORK_MODE" == tailnet || -n "${TS_AUTHKEY:-}" ]]; then
    echo "ERROR: TAILSCALE_RUNTIME_B64 required with Tailscale" >&2
    exit 70
fi

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
    cat > "$RUNTIME_LOG_DIR/runpod-sshd.conf" <<'SSHD_CONFIG'
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
LogLevel ERROR
SSHD_CONFIG

    if [[ "$DEBUG" == 1 ]]; then sed -i 's/^LogLevel ERROR$/LogLevel VERBOSE/' "$RUNTIME_LOG_DIR/runpod-sshd.conf"; fi
    if ! "$sshd_bin" -t -f "$RUNTIME_LOG_DIR/runpod-sshd.conf"; then
        echo "ERROR: SSH daemon configuration is invalid"
        return 1
    fi
    if ! "$sshd_bin" -f "$RUNTIME_LOG_DIR/runpod-sshd.conf" -E "$RUNTIME_LOG_DIR/sshd.log"; then
        echo "ERROR: SSH daemon failed to start"
        return 1
    fi

    echo "SSH_READY $(date -u +%FT%TZ)"
    ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
}

if [[ "$ENABLE_SSH" == "1" ]]; then
    echo "--- early SSH initialization"
    if start_ssh; then cold_mark ssh_ready; else echo "WARNING: continuing bootstrap without SSH"; fi
else
    echo "--- SSH disabled (set ENABLE_SSH=1 to enable)"
fi

# Fail closed until #7's verified native Tailscale/Serve enrollment completes.
if [[ "$NETWORK_MODE" == tailnet && "${TS_ACTIVE:-0}" != 1 ]]; then
    echo "ERROR: tailnet-only networking requires active Tailscale (issue #7)" >&2
    exit 70
fi
# Preflight and select all model and temporary caches BEFORE Hugging Face imports.
[[ -n "${STORAGE_HELPER_B64:-}" ]] || { echo "ERROR: STORAGE_HELPER_B64 is required" >&2; exit 64; }
if ! printf '%s' "$STORAGE_HELPER_B64" | base64 -d > "$RUNTIME_LOG_DIR/model-storage.py"; then
    echo "ERROR: cannot decode storage helper" >&2
    exit 64
fi
unset STORAGE_HELPER_B64
chmod 600 "$RUNTIME_LOG_DIR/model-storage.py"
export QWEN38_STATE_DIR="$RUNTIME_LOG_DIR"
if ! python3 "$RUNTIME_LOG_DIR/model-storage.py" prepare > "$RUNTIME_LOG_DIR/model-storage-env.sh"; then
    echo "ERROR: model storage admission failed; no fallback to SSD" >&2
    exit 64
fi
# shellcheck source=/dev/null
source "$RUNTIME_LOG_DIR/model-storage-env.sh"
# RAM telemetry samples once per second, summarizing peak usage every 15 s.
# Only DEBUG=1; no HF tokens/API keys passed to the read-only monitor.
# Keep its stdout attached to the redacted bootstrap log for remote diagnosis.
if [[ "$DEBUG" == 1 && "$MODEL_STORAGE" == ram ]]; then
    env -u HF_TOKEN -u HUGGING_FACE_HUB_TOKEN -u SGLANG_API_KEY -u TS_AUTHKEY \
        python3 -u "$RUNTIME_LOG_DIR/model-storage.py" monitor &
    STORAGE_MONITOR_PID=$!
    echo "QWEN38_STORAGE_METRIC: read-only RAM monitor started"
fi
[[ -n "${HF_TOKEN:-}" ]] && export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"
cat > /workspace/smoke-storage.sh <<'SMOKE'
#!/usr/bin/env bash
set -euo pipefail
python3 /dev/shm/qwen38-runtime/model-storage.py audit
df -B1 "${HF_HOME}" /workspace
du -sh "${HF_HOME}" 2>/dev/null || true
curl -fsS --max-time 30 -H "Authorization: Bearer ${SGLANG_API_KEY:?}" http://127.0.0.1:8000/v1/models |
  python3 -c 'import json,sys; assert json.load(sys.stdin).get("data"); print("SGLang: ready")'
SMOKE
chmod 700 /workspace/smoke-storage.sh
[[ -n "${HF_TOKEN:-}" ]] && export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"

nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader || true

# Network sanity check. A broken host looks exactly like a config bug and
# costs hours at the wrong end. Anything under 10 MB/s means throw the pod away.
cold_mark network_probe_start
echo "--- network check"
SPEED=$(curl -s -o /dev/null -w '%{speed_download}' --max-time 20 \
    https://huggingface.co/Qwen/Qwen3.8-27B-FP8/resolve/main/config.json 2>/dev/null || echo 0)
echo "download probe: $(python3 -c "print(f'{float('${SPEED:-0}')/1e6:.1f} MB/s')" 2>/dev/null || echo '?')"

cold_mark network_probe_end

# Both packages are preinstalled in the SGLang image. Never use pip to change
# the live SGLang/PyTorch/NCCL environment during bootstrap.
if ! python3 -c 'import huggingface_hub, hf_xet'; then
  echo "ERROR: Hugging Face Hub/Xet missing from the SGLang image" >&2
  exit 1
fi

cold_mark main_download_start
echo "--- fetching main and speculative draft checkpoints"
export MODEL_ID SPEC
if ! python3 "$RUNTIME_LOG_DIR/model-storage.py" download; then
    cold_mark main_download_failed
    echo "ERROR: checkpoint download or storage verification failed" >&2
    exit 70
fi
cold_mark main_download_end
MODEL_PATH=$(cat "$RUNTIME_LOG_DIR/model_path")
DRAFT_PATH=""
[[ -f "$RUNTIME_LOG_DIR/draft_path" ]] && DRAFT_PATH=$(cat "$RUNTIME_LOG_DIR/draft_path")
export MODEL_PATH DRAFT_PATH SERVED_NAME MAX_LEN SPEC MEM_FRAC MAMBA_RATIO SGLANG_API_KEY
du -sh "$MODEL_PATH" >/dev/null 2>&1 || true

# Only allowlisted, non-secret details belong in this inventory.
python3 - <<'PY'
import json, os
from pathlib import Path
v = {k.lower(): os.environ.get(k, "") for k in
    ("MODEL_ID", "SERVED_NAME", "SPEC", "MAX_LEN", "NETWORK_MODE", "DEBUG", "SERVE_WEBUI")}
v["runtime_fs"] = "tmpfs" if os.path.realpath(os.environ["RUNTIME_LOG_DIR"]).startswith("/dev/shm/") else "explicit-opt-in"
# Fixed nvidia-smi query, with bounded/sanitized fields only; never dump env.
import re, subprocess
try:
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,compute_cap",
                          "--format=csv,noheader"], capture_output=True,
                         text=True, timeout=5, check=False).stdout
except (OSError, subprocess.TimeoutExpired):
    gpu = ""
v["gpu"] = []
for row in gpu.splitlines()[:8]:
    cols = [s.strip() for s in row.split(",")]
    if len(cols) < 3:
        continue
    name = re.sub(r"[^A-Za-z0-9 ._-]", "", cols[0])[:80]
    mem = re.search(r"^[0-9]+", cols[1])
    compute = re.fullmatch(r"[0-9]+\.[0-9]+", cols[2])
    if name and mem and compute:
        v["gpu"].append({"name": name, "memory_mib": int(mem.group()), "compute": compute.group()})
Path(os.environ["RUNTIME_LOG_DIR"], "snapshot.json").write_text(json.dumps(v, sort_keys=True) + "\n")
PY

# Secrets stay in the inherited process environment, NEVER in generated scripts.
# SGLang currently requires --api-key (visible to the pod owner in /proc/PID/cmdline).
# Auth remains mandatory; process argv risk is documented rather than hidden.
cat > "$RUNTIME_LOG_DIR/start-sglang.sh" <<'SGLANG_SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
# Restore the preflight-approved cache paths on independent SSH restarts.
source "$RUNTIME_LOG_DIR/model-storage-env.sh"
SPEC_FLAGS=()
case "$SPEC" in
  mtp) SPEC_FLAGS=(--speculative-algorithm EAGLE --speculative-num-steps 3 --speculative-eagle-topk 1 --speculative-num-draft-tokens 4) ;;
  dflash2) SPEC_FLAGS=(--speculative-algorithm DFLASH --speculative-draft-model-path "$DRAFT_PATH" --speculative-num-draft-tokens 8) ;;
  dspark) SPEC_FLAGS=(--speculative-algorithm DSPARK --speculative-draft-model-path "$DRAFT_PATH") ;;
  none) ;;
  *) echo "ERROR: invalid SPEC" >&2; exit 64 ;;
esac
LOG_LEVEL=warning
[[ "$DEBUG" == 1 ]] && LOG_LEVEL=info
exec python3 -m sglang.launch_server \
  --model-path "$MODEL_PATH" \
  --served-model-name "$SERVED_NAME" \
  --trust-remote-code \
  --context-length "$MAX_LEN" \
  --mem-fraction-static "$MEM_FRAC" \
  --attention-backend flashinfer \
  --chunked-prefill-size 2048 \
  --max-prefill-tokens 32768 \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder \
  --mamba-full-memory-ratio "$MAMBA_RATIO" \
  --mamba-radix-cache-strategy extra_buffer \
  --mamba-ssm-dtype float32 \
  "${SPEC_FLAGS[@]}" \
  --api-key "$SGLANG_API_KEY" \
  --log-level "$LOG_LEVEL" --log-level-http "$LOG_LEVEL" \
  --host "$API_BIND_HOST" --port 8000
SGLANG_SCRIPT
chmod 700 "$RUNTIME_LOG_DIR/start-sglang.sh"

launch_private() {
    local name="$1"; shift
    if [[ "$DEBUG" == 1 ]]; then
        setsid "$@" 2>&1 </dev/null |
          python3 -u "$RUNTIME_LOG_DIR/redact-log.py" >> "$RUNTIME_LOG_DIR/${name}.log" &
    else
        setsid "$@" >/dev/null 2>&1 </dev/null &
    fi
    disown || true
}
cold_mark sglang_start
echo "--- starting SGLang (authenticated API; DEBUG=$DEBUG)"
launch_private sglang env -u WEBUI_ADMIN_PASSWORD -u WEBUI_ADMIN_EMAIL bash "$RUNTIME_LOG_DIR/start-sglang.sh"
cold_mark sglang_process_started
if [[ "$COLDSTART_TRACE" == 1 ]]; then
    (
        for ((attempt=0; attempt<300; attempt++)); do
            if curl -fsS --max-time 3 -o /dev/null -H "Authorization: Bearer $SGLANG_API_KEY" \
                http://127.0.0.1:8000/health_generate 2>/dev/null; then
                cold_mark health_generate_ready
                exit 0
            fi
            sleep 2
        done
        cold_mark health_generate_timeout
    ) &
    disown || true
fi

if [[ "$SERVE_WEBUI" == 1 ]]; then
  # Public OpenWebUI must have a preprovisioned administrator. In particular,
  # allowing first-user signup on an internet-facing port is NOT acceptable.
  admin_pwd="${WEBUI_ADMIN_PASSWORD:-}"
  if [[ -z "${WEBUI_ADMIN_EMAIL:-}" || ${#admin_pwd} -lt 16 ]]; then
    echo "WARNING: OpenWebUI disabled: WEBUI_ADMIN_EMAIL and strong (>=16 chars) WEBUI_ADMIN_PASSWORD required"
  else
    WEBUI_VENV="${QWEN38_WORKSPACE:-/workspace}/openwebui-venv"
    WEBUI_VERSION="${OPENWEBUI_VERSION:-0.11.4}"
    export WEBUI_VENV WEBUI_ADMIN_EMAIL WEBUI_ADMIN_PASSWORD
    cat > "$RUNTIME_LOG_DIR/start-openwebui.sh" <<'WEBUI_SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
# Mandatory authentication on BOTH RunPod public and tailnet paths.
export WEBUI_AUTH=True
export ENABLE_SIGNUP=False
export ENABLE_PERSISTENT_CONFIG=False
export ENABLE_LOGIN_FORM=True
export WEBUI_SESSION_COOKIE_SECURE=True
export ENABLE_OLLAMA_API=False
export ENABLE_COMMUNITY_SHARING=False
export ANONYMIZED_TELEMETRY=False
export ENABLE_VERSION_UPDATE_CHECK=False
export DO_NOT_TRACK=1
export SCARF_NO_ANALYTICS=1
export DATA_DIR="$WEBUI_DATA_DIR"
source "$RUNTIME_LOG_DIR/model-storage-env.sh"
export OPENAI_API_BASE_URL=http://127.0.0.1:8000/v1
export OPENAI_API_KEY="$SGLANG_API_KEY"
export WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')}"
exec "$WEBUI_VENV/bin/open-webui" serve --host "$WEBUI_BIND_HOST" --port 8080
WEBUI_SCRIPT
    chmod 700 "$RUNTIME_LOG_DIR/start-openwebui.sh"
    # Separate venv: do NOT change SGLang/PyTorch/NCCL installed packages.
    cold_mark openwebui_install_start
    echo "--- installing isolated OpenWebUI"
    if ! command -v uv >/dev/null 2>&1; then
      echo "ERROR: uv missing; OpenWebUI disabled (SGLang unaffected)"
    elif uv venv --python /usr/bin/python3 "$WEBUI_VENV" >/dev/null 2>&1 &&
         uv pip install --python "$WEBUI_VENV/bin/python" "open-webui==$WEBUI_VERSION" >/dev/null 2>&1; then
      # Start only after the authenticated API reports the model. No SSH
      # restart, no inherited redirection to persistent /workspace logs.
      cat > "$RUNTIME_LOG_DIR/start-webui-when-ready.sh" <<'READY'
#!/usr/bin/env bash
set -euo pipefail
for ((attempt=0; attempt<180; attempt++)); do
  if curl -fsS --max-time 4 -H "Authorization: Bearer $SGLANG_API_KEY" \
    http://127.0.0.1:8000/v1/models 2>/dev/null | grep -q '"id"'; then
    exec bash "$RUNTIME_LOG_DIR/start-openwebui.sh"
  fi
  sleep 10
done
echo "ERROR: OpenWebUI readiness deadline expired" >&2
exit 1
READY
      chmod 700 "$RUNTIME_LOG_DIR/start-webui-when-ready.sh"
      launch_private openwebui bash "$RUNTIME_LOG_DIR/start-webui-when-ready.sh"
    else
      echo "ERROR: OpenWebUI installation failed; SGLang remains running"
    fi
    cold_mark openwebui_install_end
  fi
else
  echo "--- SERVE_WEBUI=0, skipping OpenWebUI, SGLang API only"
fi
BENCH_PID=""
if [[ "$BENCHMARK" == 1 ]]; then
    if [[ -z "${BENCHMARK_B64:-}" ]]; then
        echo "WARNING: benchmark requested without bundled worker"
    elif printf '%s' "$BENCHMARK_B64" | base64 -d > "$RUNTIME_LOG_DIR/benchmark_sglang.py"; then
        chmod 600 "$RUNTIME_LOG_DIR/benchmark_sglang.py"
        export MODEL_ID MODEL_PATH SERVED_NAME MAX_LEN SPEC MEM_FRAC MAMBA_RATIO
        export BENCHMARK_REPORT_PATH="${BENCHMARK_REPORT_PATH:-/dev/shm/qwen38-benchmark.json}"
        python3 "$RUNTIME_LOG_DIR/benchmark_sglang.py" > "$RUNTIME_LOG_DIR/benchmark.log" 2>&1 &
        BENCH_PID=$!
        echo "Benchmark scheduled (independent of SGLang)"
    else
        echo "WARNING: invalid BENCHMARK_B64; serving unaffected"
    fi
fi
unset BENCHMARK_B64
echo "=== bootstrap done; authenticated SGLang starting ==="
if [[ -n "$BENCH_PID" ]]; then
    trap 'kill "$BENCH_PID" 2>/dev/null || true; kill "$KEEPALIVE_PID" 2>/dev/null || true; exit 0' TERM INT
    sleep infinity &
    KEEPALIVE_PID=$!
    wait "$KEEPALIVE_PID"
else
    sleep infinity
fi
