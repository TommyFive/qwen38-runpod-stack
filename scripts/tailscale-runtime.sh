#!/usr/bin/env bash
# Shell helper sourced by bootstrap-sglang-openwebui.sh.
# Always use Tailscale native SSH. Userspace mode is required on RunPod:
# the tested pod has neither /dev/net/tun nor CAP_NET_ADMIN.
#
# Contract: no TS_AUTHKEY -> do nothing in runpod mode; fail closed in
# tailnet-only mode. No auth key in command arguments, generated scripts or logs.
ts_start() {
    TS_ACTIVE=0
    TS_SOCKET=""
    TS_DNS_NAME=""
    TS_HOSTNAME="${TS_HOSTNAME:-}"
    TS_ENABLE_SSH="${TS_ENABLE_SSH:-1}"
    NETWORK_MODE="${NETWORK_MODE:-runpod}"
    if [[ "$NETWORK_MODE" != runpod && "$NETWORK_MODE" != tailnet ]]; then
        echo "ERROR: NETWORK_MODE must be runpod or tailnet" >&2; return 64
    fi
    if [[ "$TS_ENABLE_SSH" != 0 && "$TS_ENABLE_SSH" != 1 ]]; then
        echo "ERROR: TS_ENABLE_SSH must be 0 or 1" >&2; return 64
    fi
    if [[ -z "${TS_AUTHKEY:-}" ]]; then
        if [[ "$NETWORK_MODE" == tailnet ]]; then
            echo "ERROR: NETWORK_MODE=tailnet requires a nonempty TS_AUTHKEY" >&2; return 64
        fi
        echo "TAILSCALE: disabled (TS_AUTHKEY empty)"
        return 0
    fi

    local prefix
    prefix="${HOSTNAME:-$(hostname)}"
    TS_HOSTNAME="${TS_HOSTNAME:-qwen38-${prefix:0:12}}"
    if [[ ! "$TS_HOSTNAME" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; then
        echo "ERROR: TS_HOSTNAME must be a 1-63 character lowercase DNS label" >&2
        return 64
    fi

    # The auth key is injected by RunPod as an env secret. Move it into a
    # 0600 tmpfs file; tailscale up reads file: rather than putting it in argv.
    # Never print the value or use shell tracing.
    set +x
    umask 077
    local secret_dir="${TS_SECRET_DIR:-/dev/shm/qwen38-secrets}"
    if [[ "$(stat -f -c %T /dev/shm 2>/dev/null)" != tmpfs ]]; then
        echo "ERROR: /dev/shm must be tmpfs for TS_AUTHKEY" >&2; return 70
    fi
    install -d -m 700 "$secret_dir" || return 70
    local auth_file="$secret_dir/ts-authkey"
    ( umask 077; printf '%s\n' "$TS_AUTHKEY" > "$auth_file" ) || return 70
    chmod 600 "$auth_file"
    unset TS_AUTHKEY
    export -n TS_AUTHKEY 2>/dev/null || true

    local work="${TS_RUNTIME_DIR:-/tmp/qwen38-tailscale}"
    install -d -m 700 "$work" || { rm -f "$auth_file"; return 70; }
    local cli daemon
    if command -v tailscale >/dev/null 2>&1 && command -v tailscaled >/dev/null 2>&1; then
        cli="$(command -v tailscale)"
        daemon="$(command -v tailscaled)"
    else
        local version="${TS_VERSION:-1.102.3}"
        # Production deployments are intentionally pinned to the version
        # already verified against the RunPod SGLang container.
        [[ "$version" == 1.102.3 ]] || {
            echo "ERROR: unsupported TS_VERSION (update pin and tests first)" >&2
            rm -f "$auth_file"; return 64
        }
        echo "TAILSCALE: installing verified static binary ${version}"
        local url="https://pkgs.tailscale.com/stable/tailscale_${version}_amd64.tgz"
        if ! curl -fsSL --retry 2 --max-time 120 "$url" -o "$work/tailscale.tar.gz" ||
           ! curl -fsSL --retry 2 --max-time 30 "${url}.sha256" -o "$work/tailscale.sha256"; then
            echo "ERROR: Tailscale download failed" >&2
            rm -f "$auth_file"; return 70
        fi
        local expected actual
        expected="$(tr -cd 'a-fA-F0-9' < "$work/tailscale.sha256")"
        actual="$(sha256sum "$work/tailscale.tar.gz" | cut -d' ' -f1)"
        if [[ ! "$expected" =~ ^[0-9a-fA-F]{64}$ || "${expected,,}" != "${actual,,}" ]]; then
            echo "ERROR: Tailscale archive SHA-256 verification failed" >&2
            rm -f "$auth_file"; return 70
        fi
        if ! tar -xzf "$work/tailscale.tar.gz" -C "$work"; then
            echo "ERROR: invalid Tailscale archive" >&2
            rm -f "$auth_file"; return 70
        fi
        cli="$work/tailscale_${version}_amd64/tailscale"
        daemon="$work/tailscale_${version}_amd64/tailscaled"
        [[ -x "$cli" && -x "$daemon" ]] || {
            echo "ERROR: Tailscale binaries missing" >&2
            rm -f "$auth_file"; return 70
        }
    fi

    TS_SOCKET="$work/tailscaled.sock"
    echo "TAILSCALE: starting userspace daemon"
    "$daemon" --tun=userspace-networking --state=mem: --socket="$TS_SOCKET" \
        --no-logs-no-support --port=0 > "$work/tailscaled.log" 2>&1 &
    TS_DAEMON_PID=$!
    local i
    for ((i=0; i<100; i++)); do
        [[ -S "$TS_SOCKET" ]] && break
        if ! kill -0 "$TS_DAEMON_PID" 2>/dev/null; then break; fi
        sleep 0.2
    done
    if [[ ! -S "$TS_SOCKET" ]]; then
        echo "ERROR: tailscaled socket unavailable" >&2
        rm -f "$auth_file"; return 70
    fi
    local args=(--auth-key="file:$auth_file" --hostname="$TS_HOSTNAME"
        --accept-dns=false --accept-routes=false --timeout=45s)
    [[ "$TS_ENABLE_SSH" == 1 ]] && args+=(--ssh)
    if ! "$cli" --socket="$TS_SOCKET" up "${args[@]}" > "$work/up.log" 2>&1; then
        echo "ERROR: Tailscale login failed (see private daemon log)" >&2
        rm -f "$auth_file"
        return 70
    fi
    rm -f "$auth_file"
    TS_CLI="$cli"
    TS_ACTIVE=1
    export TS_ACTIVE TS_SOCKET TS_HOSTNAME
    # No auth token is present in this status response.
    TS_DNS_NAME="$("$cli" --socket="$TS_SOCKET" status --json | python3 -c 'import json,sys; print((json.load(sys.stdin).get("Self") or {}).get("DNSName","").rstrip("."))' 2>/dev/null)"
    if [[ -z "$TS_DNS_NAME" ]]; then
        echo "ERROR: Tailscale failed to report a MagicDNS name" >&2; return 70
    fi
    echo "TAILSCALE: connected hostname=$TS_DNS_NAME native_ssh=$TS_ENABLE_SSH"
}

ts_serve() {
    [[ "${TS_ACTIVE:-0}" == 1 ]] || return 0
    local mode="${NETWORK_MODE:-runpod}"
    # API on 443; optional OpenWebUI on 8443. Never forward TCP/22:
    # native Tailscale SSH is handled inside tailscaled.
    if ! "$TS_CLI" --socket="$TS_SOCKET" serve --yes --bg --https=443 \
        http://127.0.0.1:8000 >/dev/null 2>&1; then
        echo "ERROR: Tailscale Serve API configuration failed" >&2
        [[ "$mode" != tailnet ]]; return
    fi
    if [[ "${SERVE_WEBUI:-1}" == 1 ]]; then
        if ! "$TS_CLI" --socket="$TS_SOCKET" serve --yes --bg --https=8443 \
            http://127.0.0.1:8080 >/dev/null 2>&1; then
            echo "ERROR: Tailscale Serve WebUI configuration failed" >&2
            [[ "$mode" != tailnet ]]; return
        fi
    fi
    echo "TAILSCALE: Serve configured for HTTPS API :443 and optional UI :8443"
}
