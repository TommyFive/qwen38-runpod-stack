#!/usr/bin/env bash
# Offline Tailscale-native SSH contract tests: no GPU, pod or actual auth key.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'if [[ -f "$TMP/daemon.pid" ]]; then kill "$(cat "$TMP/daemon.pid")" 2>/dev/null || :; fi; rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/work"
export TS_RUNTIME_DIR="$TMP/work"
export TS_SECRET_DIR="$TMP/secrets"
export TEST_CALL_LOG="$TMP/calls"
export PATH="$TMP/bin:$PATH"

cat > "$TMP/bin/tailscaled" <<'MOCK'
#!/usr/bin/env python3
import os, socket, sys, time
args = sys.argv[1:]
socket_path = next(x.split("=", 1)[1] for x in args if x.startswith("--socket="))
with open(os.environ["TEST_CALL_LOG"], "a") as log:
    log.write("DAEMON " + " ".join(args) + "\n")
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.bind(socket_path)
sock.listen(4)
while True:
    time.sleep(1)
MOCK
cat > "$TMP/bin/tailscale" <<'MOCK'
#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if "up" in args:
    auth = next((x.split("=",1)[1] for x in args if x.startswith("--auth-key=")), "")
    if not auth.startswith("file:") or not os.path.isfile(auth[5:]):
        raise SystemExit(1)
    if open(auth[5:]).read().strip() != "tskey-auth-test-only":
        raise SystemExit(2)
    # Log arguments, never the credential value.
    with open(os.environ["TEST_CALL_LOG"], "a") as log:
        log.write("UP " + " ".join(args) + "\n")
elif "status" in args:
    print(json.dumps({"Self":{"DNSName":"qwen38-ci.tailc8dece.ts.net."}}))
elif "serve" in args:
    with open(os.environ["TEST_CALL_LOG"], "a") as log:
        log.write("SERVE " + " ".join(args) + "\n")
else:
    raise SystemExit(3)
MOCK
chmod +x "$TMP/bin/"*

# shellcheck source=scripts/tailscale-runtime.sh
source "$ROOT/scripts/tailscale-runtime.sh"

echo "=== no-key legacy skips Tailscale entirely ==="
unset TS_AUTHKEY || true
NETWORK_MODE=runpod
ts_start
[[ "$TS_ACTIVE" == 0 ]]
[[ ! -f "$TEST_CALL_LOG" ]]

echo "=== no-key tailnet must fail closed ==="
NETWORK_MODE=tailnet
if ts_start >/dev/null 2>&1; then echo "FAIL: tailnet accepted missing key" >&2; exit 1; fi

echo "=== invalid network mode and SSH flag ==="
NETWORK_MODE=invalid
if ts_start >/dev/null 2>&1; then echo "FAIL: unknown mode" >&2; exit 1; fi
NETWORK_MODE=runpod
TS_ENABLE_SSH=wat
if ts_start >/dev/null 2>&1; then echo "FAIL: invalid SSH flag" >&2; exit 1; fi
TS_ENABLE_SSH=1

echo "=== invalid hostname fails before daemon ==="
TS_HOSTNAME=Invalid.Host
TS_AUTHKEY=tskey-auth-test-only
if ts_start >/dev/null 2>&1; then echo "FAIL: invalid hostname" >&2; exit 1; fi
[[ ! -e "$TEST_CALL_LOG" ]]

echo "=== authenticated Tailscale userspace, native SSH and Serve ==="
TS_HOSTNAME=qwen38-ci
NETWORK_MODE=tailnet
TS_AUTHKEY=tskey-auth-test-only
SERVE_WEBUI=1
ts_start
printf '%s\n' "$TS_DAEMON_PID" > "$TMP/daemon.pid"
[[ "$TS_ACTIVE" == 1 ]]
[[ "$TS_DNS_NAME" == qwen38-ci.tailc8dece.ts.net ]]
[[ ! -e "$TS_SECRET_DIR/ts-authkey" ]]
[[ -z "${TS_AUTHKEY:-}" ]]
ts_serve
grep -Fq -- "--tun=userspace-networking --state=mem:" "$TEST_CALL_LOG"
grep -Fq -- "--ssh" "$TEST_CALL_LOG"
grep -Fq -- "--auth-key=file:$TS_SECRET_DIR/ts-authkey" "$TEST_CALL_LOG"
grep -Fq -- "--https=443 http://127.0.0.1:8000" "$TEST_CALL_LOG"
grep -Fq -- "--https=8443 http://127.0.0.1:8080" "$TEST_CALL_LOG"
if grep -Fq 'serve --tcp=22' "$TEST_CALL_LOG"; then echo "FAIL: legacy TCP/22 forwarding" >&2; exit 1; fi
if grep -Fq 'tskey-auth-test-only' "$TEST_CALL_LOG"; then echo "FAIL: auth key exposed to command arguments" >&2; exit 1; fi

echo "test-tailscale: ok"
