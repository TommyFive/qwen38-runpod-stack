#!/usr/bin/env bash
# Offline regression for RunPod noexec /dev/shm: verified, public binaries must
# execute from ephemeral /tmp; credentials, daemon state, socket remain tmpfs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d /tmp/qwen38-ts-test.XXXXXXXX)"
SECRET="$(mktemp -d /dev/shm/qwen38-ts-test.XXXXXXXX)"
daemon_pid=""
trap '[[ -z "$daemon_pid" ]] || kill "$daemon_pid" 2>/dev/null || :; rm -rf "$TMP" "$SECRET"' EXIT
mkdir -p "$TMP/bin" "$TMP/source/tailscale_1.102.3_amd64" "$SECRET/runtime"
export TS_BIN_DIR="$TMP/exec" TS_RUNTIME_DIR="$SECRET/runtime" TS_SECRET_DIR="$SECRET/keys"
export TEST_TAILSCALE_ARCHIVE="$TMP/tailscale.tgz" TEST_TAILSCALE_SHA="$TMP/tailscale.sha256"
export PATH="$TMP/bin:$PATH"

cat > "$TMP/source/tailscale_1.102.3_amd64/tailscaled" <<'DAEMON'
#!/usr/bin/env python3
import socket, sys, time
p=next(x.split("=",1)[1] for x in sys.argv if x.startswith("--socket="))
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
s.bind(p);s.listen(2)
while True: time.sleep(1)
DAEMON
cat > "$TMP/source/tailscale_1.102.3_amd64/tailscale" <<'CLI'
#!/usr/bin/env python3
import json, os, sys
args=sys.argv[1:]
if "up" in args:
    p=next((v.split("=",1)[1][5:] for v in args if v.startswith("--auth-key=file:")),None)
    assert p and open(p).read().strip()==os.environ["TEST_EXPECTED_AUTH"]
elif "status" in args:
    print(json.dumps({"Self":{"DNSName":"qwen38-test.tailc8dece.ts.net."}}))
elif "serve" in args:
    pass
else:
    raise SystemExit("unexpected Tailscale invocation")
CLI
chmod 700 "$TMP/source/tailscale_1.102.3_amd64/"{tailscale,tailscaled}
tar -czf "$TEST_TAILSCALE_ARCHIVE" -C "$TMP/source" tailscale_1.102.3_amd64
sha256sum "$TEST_TAILSCALE_ARCHIVE" | cut -d' ' -f1 > "$TEST_TAILSCALE_SHA"
cat > "$TMP/bin/curl" <<'CURL'
#!/usr/bin/env bash
set -euo pipefail
url="" out=""
while (($#)); do
  case "$1" in
    -o) out="$2";shift 2;;
    http*) url="$1";shift;;
    *) shift;;
  esac
done
[[ "$url" == https://pkgs.tailscale.com/stable/tailscale_1.102.3_amd64.tgz* ]]
[[ -n "$out" ]]
if [[ "$url" == *.sha256 ]]; then cp "$TEST_TAILSCALE_SHA" "$out"; else cp "$TEST_TAILSCALE_ARCHIVE" "$out"; fi
CURL
chmod 700 "$TMP/bin/curl"

# Force missing system Tailscale binaries even if the CI runner has them.
command() {
    if [[ "${1:-}" == -v && ( "${2:-}" == tailscale || "${2:-}" == tailscaled ) ]]; then return 1; fi
    builtin command "$@"
}
source "$ROOT/scripts/tailscale-runtime.sh"

export NETWORK_MODE=tailnet TS_HOSTNAME=qwen38-test TS_ENABLE_SSH=1
export TEST_EXPECTED_AUTH=tskey-auth-ci-fixture
export TS_AUTHKEY="$TEST_EXPECTED_AUTH"
ts_start
daemon_pid="$TS_DAEMON_PID"
[[ "$TS_ACTIVE" == 1 ]]
[[ "$TS_CLI" == "$TS_BIN_DIR/tailscale_1.102.3_amd64/tailscale" ]]
[[ "$TS_SOCKET" == "$TS_RUNTIME_DIR/tailscaled.sock" ]]
[[ -S "$TS_SOCKET" ]]
[[ "$TS_DNS_NAME" == "qwen38-test.tailc8dece.ts.net" ]]
[[ ! -e "$TS_BIN_DIR/tailscale.tar.gz" ]]
[[ ! -e "$TS_BIN_DIR/tailscale.sha256" ]]
[[ -z "${TS_AUTHKEY:-}" ]]
if [[ -d "$TS_SECRET_DIR" ]] && find "$TS_SECRET_DIR" -type f | grep -q .; then
  echo "FAIL: Tailscale auth key persisted" >&2; exit 1
fi
if grep -R -Fq 'tskey-auth-ci-fixture' "$TS_BIN_DIR"; then
  echo "FAIL: plaintext secret in executable stage" >&2; exit 1
fi
kill "$daemon_pid" 2>/dev/null || :
daemon_pid=""
echo "Tailscale executable staging regression passed"
