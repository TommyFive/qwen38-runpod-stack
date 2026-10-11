#!/usr/bin/env bash
# Deadline checkpoint: publish two locally generated OCI images to GHCR.
# Execute only on the authorized disposable ECS with an ephemeral GHCR authfile.
# No builds, model access, GPU operations, deployments, or production tags.
set -Eeuo pipefail
umask 077
ROOT=/opt/qwen38-v2-build
AUTH="$ROOT/.ghcr-backup-auth.json"
REPO="ghcr.io/tommyfive/qwen38-minimal-v2-cpu"
test -s "$AUTH" || { echo "Missing temporary GHCR authentication"; exit 8; }
skopeo --version
for mode in rust rust-cuda; do
  src="$ROOT/minimal-v2-$mode.oci.tar"
  tag="cpu-$mode-20261012-4fb0b652"
  dst="$REPO:$tag"
  test -s "$src" || { echo "Missing immutable OCI archive: $src"; exit 9; }
  echo "=== BEGIN $mode $(date -u +%FT%TZ) destination=$dst ==="
  if skopeo inspect --authfile "$AUTH" "docker://$dst" >/dev/null 2>&1; then
    echo "Remote tag already exists. Refusing overwrite: $dst"
    exit 10
  fi
  # Skopeo copies existing compressed blobs and OCI config without Docker load.
  # Retry network errors; keep a complete copy log for audit.
  if ! skopeo copy --all --retry-times 5 --authfile "$AUTH" \
     "oci-archive:$src" "docker://$dst" > "$ROOT/ghcr-copy-$mode.log" 2>&1; then
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
