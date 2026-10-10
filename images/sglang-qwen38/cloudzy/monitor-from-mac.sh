#!/usr/bin/env bash
# Stable, stateless reattachment: ChatGPT -> SSH MCP -> Mac mini -> Cloudzy.
set -Eeuo pipefail
umask 077
ACTION="${1:-status}"
case "$ACTION" in status|resources|errors|logs|bootstrap|docker|archive) ;; *) echo "Usage: $0 [status|resources|errors|logs|bootstrap|docker|archive]" >&2; exit 64;; esac
[[ $# -le 1 ]] || exit 64
STATE="$HOME/.local/state/qwen38-cloudzy-builder"
KEY="$HOME/.ssh/id_ed25519"
[[ -r "$STATE/current-ip" && -r "$STATE/current-sha" && -s "$STATE/known_hosts" && -r "$KEY" ]] || {
  echo "No registered VM: run start-from-mac.sh NEW_PUBLIC_IPV4 once" >&2
  exit 1
}
IP="$(cat "$STATE/current-ip")"
SHA="$(cat "$STATE/current-sha")"
[[ "$IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ && "$SHA" =~ ^[a-f0-9]{40}$ ]] || exit 1
IFS='.' read -r A B C D <<<"$IP"
for octet in "$A" "$B" "$C" "$D"; do ((10#$octet <= 255)) || exit 1; done
SSH=(ssh -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=12
     -o ConnectionAttempts=1 -o StrictHostKeyChecking=yes
     -o UserKnownHostsFile="$STATE/known_hosts" -o UpdateHostKeys=no
     -o RequestTTY=no -o ServerAliveInterval=15 -o ServerAliveCountMax=2
     "root@$IP")
echo "Qwen38 via Mac mini | target=$IP | commit=$SHA | action=$ACTION"
if [[ "$ACTION" == archive ]]; then
  ARCHIVES="$HOME/.local/share/qwen38-cloudzy-builder-archives"
  mkdir -p "$ARCHIVES"; chmod 700 "$ARCHIVES"
  FILE="$ARCHIVES/qwen38-cloudzy-$(date -u +%Y%m%dT%H%M%SZ)-${SHA:0:12}.tar.gz"
  TMP="$(mktemp "$ARCHIVES/.qwen38-transfer.XXXXXXXX")"
  trap 'rm -f "$TMP"' EXIT
  "${SSH[@]}" 'tar -C /var/log -czf - qwen38-cloudzy' >"$TMP"
  test -s "$TMP"; mv "$TMP" "$FILE"; chmod 600 "$FILE"; trap - EXIT
  echo "Archived private logs to Mac mini: $FILE"; shasum -a 256 "$FILE"
  exit 0
fi
case "$ACTION" in
  status)
    "${SSH[@]}" 'bash -s' <<'REMOTE'
set +e
echo '=== UTC / HOST ==='; date -u -Is; hostname; uptime
echo '=== BOOTSTRAP ==='; systemctl show qwen38-cloudzy-bootstrap -p ActiveState -p SubState -p Result --no-pager 2>/dev/null
echo '=== BUILD ==='; systemctl show qwen38-cloudzy-image -p ActiveState -p SubState -p Result -p ExecMainStatus --no-pager 2>/dev/null
echo '=== IMAGE / RESULT ==='
for name in source.sha; do test -r "/opt/qwen38-cloudzy/$name" && cat "/opt/qwen38-cloudzy/$name"; done
for name in exit-code.txt image-tag.txt image-inspect.txt; do
  if test -r "/var/log/qwen38-cloudzy/$name"; then echo "$name"; head -n 3 "/var/log/qwen38-cloudzy/$name"; fi
done
echo '=== LAST RESOURCE SAMPLE ==='; tail -n 1 /var/log/qwen38-cloudzy/resource-samples.jsonl 2>/dev/null
echo '=== CURRENT RAM / SSD ==='; free -h; df -h / /var/lib/docker 2>/dev/null || df -h /
echo '=== RECENT SERVICE MESSAGES ==='; journalctl -u qwen38-cloudzy-bootstrap -u qwen38-cloudzy-image -n 12 --no-pager -o short-iso 2>/dev/null
REMOTE
    ;;
  resources) "${SSH[@]}" 'tail -n 12 /var/log/qwen38-cloudzy/resource-samples.jsonl';;
  errors)
    "${SSH[@]}" 'bash -s' <<'REMOTE'
set +e
echo '=== SERVICE ERRORS ==='
journalctl -u qwen38-cloudzy-bootstrap -u qwen38-cloudzy-image -p err -n 30 --no-pager -o short-iso 2>/dev/null
echo '=== BUILDKIT ERRORS ==='
if test -r /var/log/qwen38-cloudzy/buildkit.log; then
  grep -iE '(^#.*(ERROR|FAILED)|error:|fatal:|oom|out of memory|no space left|killed|exit code [1-9])' /var/log/qwen38-cloudzy/buildkit.log | tail -n 35 | cut -c 1-360
else echo 'BuildKit log not created yet (bootstrap may still be running)'; fi
echo '=== KERNEL OOM ==='
journalctl -k --no-pager 2>/dev/null | grep -iE 'oom|out of memory|killed process' | tail -n 12 | cut -c 1-360
REMOTE
    ;;
  logs)
    "${SSH[@]}" 'bash -s' <<'REMOTE'
if test -r /var/log/qwen38-cloudzy/buildkit.log; then
  tail -n 65 /var/log/qwen38-cloudzy/buildkit.log | cut -c 1-700
else echo 'BuildKit log not created yet'; fi
REMOTE
    ;;
  bootstrap) "${SSH[@]}" 'journalctl -u qwen38-cloudzy-bootstrap -n 70 --no-pager -o short-iso';;
  docker)
    "${SSH[@]}" 'bash -s' <<'REMOTE'
set +e
docker info --format 'DockerRoot={{.DockerRootDir}} ServerVersion={{.ServerVersion}}'
docker buildx ls
docker system df
docker ps --filter 'name=buildx_buildkit_qwen38-cloudzy' --format '{{.Names}} | {{.Status}}'
REMOTE
    ;;
esac
