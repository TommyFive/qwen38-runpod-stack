#!/usr/bin/env bash
# Persistent mac-mini-target registration and detached Ubuntu bootstrap.
set -Eeuo pipefail
umask 077
[[ $# == 1 ]] || { echo "Usage: bash start-from-mac.sh NEW_PUBLIC_IPV4" >&2; exit 64; }
IP="$1"
[[ "$IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || { echo "Public IPv4 required" >&2; exit 64; }
IFS='.' read -r A B C D <<<"$IP"
for octet in "$A" "$B" "$C" "$D"; do ((10#$octet <= 255)) || exit 64; done
[[ "$IP" != 127.* && "$IP" != 0.* && "$IP" != 169.254.* && "$IP" != 10.* && "$IP" != 192.168.* ]] || {
  echo "Private/reserved IP refused" >&2; exit 64;
}
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
[[ "$(git -C "$ROOT" branch --show-current)" == feature/qwen38-minimal-sglang-image ]] || {
  echo "Wrong Git branch" >&2; exit 1;
}
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] || {
  echo "Dirty repository; refusing uncommitted bootstrap" >&2; exit 1;
}
SHA="$(git -C "$ROOT" rev-parse HEAD)"
[[ "$SHA" =~ ^[a-f0-9]{40}$ ]] || exit 1
KEY="$HOME/.ssh/id_ed25519"
[[ -r "$KEY" ]] || { echo "Mac mini SSH key missing" >&2; exit 1; }
STATE="$HOME/.local/state/qwen38-cloudzy-builder"
mkdir -p "$STATE"; chmod 700 "$STATE"
if [[ -e "$STATE/current-ip" || -e "$STATE/current-sha" ]]; then
  echo "Existing registered Cloudzy VM found; inspect first with monitor-from-mac.sh" >&2
  exit 1
fi
SSH=(ssh -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15
     -o ConnectionAttempts=1 -o StrictHostKeyChecking=accept-new
     -o UserKnownHostsFile="$STATE/known_hosts" -o UpdateHostKeys=no
     -o RequestTTY=no -o ServerAliveInterval=15 -o ServerAliveCountMax=2 "root@$IP")
echo "Read-only SSH preflight to the newly provisioned Cloudzy VM: $IP"
"${SSH[@]}" 'bash -s' <<'REMOTE'
set -eu
test "$(uname -m)" = x86_64
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
test ! -e /opt/qwen38-cloudzy/.started
test ! -e /opt/qwen38-cloudzy-bootstrap/bootstrap.sh
echo "PASS: SSH authenticated to fresh Ubuntu 24.04"
REMOTE
[[ -s "$STATE/known_hosts" ]] || { echo "Host key not recorded" >&2; exit 1; }
chmod 600 "$STATE/known_hosts"
echo "Pinned server SSH host-key fingerprint (compare to Cloudzy console if available):"
ssh-keygen -lf "$STATE/known_hosts" -E sha256
# Persist even if a later bootstrap step fails, enabling status/troubleshooting.
printf '%s\n' "$IP" > "$STATE/current-ip.tmp"
printf '%s\n' "$SHA" > "$STATE/current-sha.tmp"
chmod 600 "$STATE/current-ip.tmp" "$STATE/current-sha.tmp"
mv "$STATE/current-ip.tmp" "$STATE/current-ip"
mv "$STATE/current-sha.tmp" "$STATE/current-sha"
echo "Registered Cloudzy target: $IP / pinned repo commit $SHA"
# Remote only receives this repository's reviewed bootstrap script; no token.
# systemd-run returns immediately, so SSH MCP timeouts cannot stop apt/Docker.
"${SSH[@]}" "set -eu; test ! -e /opt/qwen38-cloudzy-bootstrap/bootstrap.sh; test ! -e /opt/qwen38-cloudzy/.started; install -m 0700 -d /opt/qwen38-cloudzy-bootstrap; cat > /opt/qwen38-cloudzy-bootstrap/bootstrap.sh; chmod 0700 /opt/qwen38-cloudzy-bootstrap/bootstrap.sh; systemd-run --unit=qwen38-cloudzy-bootstrap --property=RuntimeMaxSec=3600 /usr/bin/bash /opt/qwen38-cloudzy-bootstrap/bootstrap.sh '$SHA'" < "$HERE/bootstrap-and-start.sh"
echo "BOOTSTRAP SCHEDULED (not proof of success)."
echo "Use mac-mini-admin to run: bash $HERE/monitor-from-mac.sh status"
echo "Logs and monitoring remain available after SSH disconnect / new ChatGPT chat."
