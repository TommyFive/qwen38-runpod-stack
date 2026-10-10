#!/usr/bin/env bash
# Operator entrypoint on Mac mini: start only on a NEW approved Cloudzy VM.
# This script never creates, pays for, powers on, deletes or modifies a VPS
# other than the explicit host IP passed as its one argument.
set -Eeuo pipefail
umask 077
[[ $# == 1 ]] || { echo "Usage: bash images/sglang-qwen38/cloudzy/start-from-mac.sh <NEW_CLOUDZY_PUBLIC_IPV4>" >&2; exit 64; }
IP="$1"
# Require real IPv4; no hostname, command options or SSH command injection.
[[ "$IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || { echo "Expected IPv4 address" >&2; exit 64; }
IFS='.' read -r a b c d <<<"$IP"
for octet in "$a" "$b" "$c" "$d"; do
  ((10#$octet <= 255)) || { echo "IPv4 octet out of range" >&2; exit 64; }
done
[[ "$IP" != 127.* && "$IP" != 0.* ]] || { echo "Non-public destination refused" >&2; exit 64; }
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
[[ "$(git -C "$ROOT" branch --show-current)" == feature/qwen38-minimal-sglang-image ]] || {
  echo "Wrong Git feature branch" >&2; exit 1;
}
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] || {
  echo "Working tree is not clean; refusing uncommitted bootstrap" >&2; exit 1;
}
SHA="$(git -C "$ROOT" rev-parse HEAD)"
[[ "$SHA" =~ ^[a-f0-9]{40}$ ]] || exit 1
IDENTITY="$HOME/.ssh/id_ed25519"
[[ -r "$IDENTITY" ]] || { echo "No authorized SSH identity $IDENTITY" >&2; exit 1; }
echo "Approved new Cloudzy target: $IP"
echo "Pinned Qwen38 commit: $SHA"
echo "Starting preflight, Docker installation and 64GB-capped builder via SSH..."
ssh -i "$IDENTITY" -o IdentitiesOnly=yes -o BatchMode=yes \
  -o ConnectTimeout=15 -o ServerAliveInterval=15 -o StrictHostKeyChecking=accept-new \
  "root@$IP" 'bash -s --' "$SHA" < "$HERE/bootstrap-and-start.sh"
echo "Bootstrap finished. Build continues as a systemd job after SSH disconnect."
echo "Monitor via: ssh -i ~/.ssh/id_ed25519 root@$IP 'journalctl -u qwen38-cloudzy-image -n 20 --no-pager'"
echo "Do not delete the VM until image and logs have been saved externally."
