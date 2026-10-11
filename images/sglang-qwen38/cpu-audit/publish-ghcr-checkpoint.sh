#!/usr/bin/env bash
# Deadline checkpoint: publish two locally generated OCI images to GHCR.
# Execute only on the authorized disposable ECS with an ephemeral GHCR authfile.
# No builds, model access, GPU operations, deployments, or production tags.
set -Eeuo pipefail
umask 077
ROOT=/opt/qwen38-v2-build
AUTH="$ROOT/.ghcr-backup-auth.json"
REPO="ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint"
test -s "$AUTH" || { echo "Missing temporary GHCR authentication"; exit 8; }
skopeo --version
for mode in rust rust-cuda; do
  src="$ROOT/oci-split-$mode"
  for attempt in $(seq 1 360); do
    if [[ -s "$src/index.json" ]]; then break; fi
    if (( attempt % 12 == 0 )); then echo "Waiting for GHCR-safe split OCI $mode $(date -u +%FT%TZ)"; fi
    sleep 15
  done
  test -s "$src/index.json" || { echo "Timeout waiting for split OCI $mode"; exit 9; }
  tag="cpu-$mode-20261012-4fb0b652"
  dst="$REPO:$tag"
  test -s "$src/split-report.json" || { echo "Missing split OCI report: $src"; exit 9; }
  skopeo inspect --raw "oci:$src:checkpoint" > "$ROOT/ghcr-$mode-local-manifest.json"
  echo "=== BEGIN $mode $(date -u +%FT%TZ) destination=$dst ==="
  if skopeo inspect --authfile "$AUTH" "docker://$dst" >/dev/null 2>&1; then
    echo "Remote tag already exists. Refusing overwrite: $dst"
    exit 10
  fi
  # Skopeo copies existing compressed blobs and OCI config without Docker load.
  # Retry network errors; keep a complete copy log for audit.
  if ! skopeo copy --all --retry-times 5 --authfile "$AUTH" \
     "oci:$src:checkpoint" "docker://$dst" > "$ROOT/ghcr-copy-$mode.log" 2>&1; then
     cat "$ROOT/ghcr-copy-$mode.log"
     echo "FAIL uploading $mode"
     exit 11
  fi
  cat "$ROOT/ghcr-copy-$mode.log"
  skopeo inspect --authfile "$AUTH" --raw "docker://$dst" > "$ROOT/ghcr-$mode-remote-manifest.json"
  skopeo inspect --authfile "$AUTH" "docker://$dst" > "$ROOT/ghcr-$mode-remote-inspect.json"
  sha256sum "$ROOT/ghcr-$mode-remote-manifest.json" > "$ROOT/ghcr-$mode-remote-manifest.sha256"
  echo "=== VERIFIED REMOTE $mode $dst $(date -u +%FT%TZ) ==="
  cat "$ROOT/ghcr-$mode-remote-manifest.sha256"
done
echo "=== BOTH GHCR UPLOADS AND REMOTE INSPECTIONS COMPLETE ==="
