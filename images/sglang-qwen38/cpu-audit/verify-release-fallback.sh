#!/usr/bin/env bash
# Independently verify/reconstruct both complete OCI layouts from GitHub Release.
# CPU-only, no Docker builds, no pushes, no registry credential, no GPU and
# no production changes. Execute only on an approved disposable AMD64 host.
set -Eeuo pipefail
umask 077

ROOT="${1:-/opt/qwen38-verify}"
REL="minimal-v2-cpu-checkpoint-20261012"
BASE="https://github.com/TommyFive/qwen38-runpod-stack/releases/download/$REL"
OUT="$ROOT/release-recovery"
mkdir -p "$OUT"

for mode in rust-cuda rust; do
  printf '\n=== BACKUP CHECK %s %s ===\n' "$mode" "$(date -u +%FT%TZ)"
  if [[ "$mode" == rust ]]; then
    manifest_sha="101d0e21ab45a18a64cf330e5772ce9802b4e34a0f596bcbbcecf819d6d65cf9"
    registry_sha="ec013c2e20528a92d61b6a7a0352ba081e166ef99025a5fbb4be06572381bb1e"
    count=13
  else
    manifest_sha="99271b1e267d20c946a42a7a4fafac58a09df4cf5d2636feb0b65030a0eec8a3"
    registry_sha="820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7"
    count=12
  fi

  cp "$ROOT/release-$mode.parts.sha256" "$OUT/release-$mode.parts.sha256"
  cd "$OUT"
  printf '%s  %s\n' "$manifest_sha" "release-$mode.parts.sha256" | sha256sum -c
  actual_count="$(wc -l < "release-$mode.parts.sha256" | tr -d ' ')"
  [[ "$actual_count" == "$count" ]] || { echo "Bad $mode part count $actual_count" >&2; exit 30; }

  while read -r expected name <&3; do
    [[ "$expected" =~ ^[0-9a-f]{64}$ ]] || { echo "Unsafe digest" >&2; exit 31; }
    [[ "$name" =~ ^release-${mode}\.part-[a-z]{2}$ ]] || { echo "Unsafe part name" >&2; exit 31; }
    if [[ -s "$name" ]] && printf '%s  %s\n' "$expected" "$name" | sha256sum --check --status; then
      echo "ALREADY_VERIFIED $name"
      continue
    fi
    success=0
    for attempt in 1 2; do
      echo "DOWNLOAD $name attempt=$attempt $(date -u +%FT%TZ)"
      # Direct public GitHub Release HTTP does not require a GH CLI login.
      if curl -fLSs --retry 5 --retry-delay 3 --retry-all-errors \
          --connect-timeout 30 --max-time 2000 \
          -o "$name" "$BASE/$name" \
          && printf '%s  %s\n' "$expected" "$name" | sha256sum -c; then
        success=1
        break
      fi
      rm -f "$name"
    done
    [[ "$success" == 1 ]] || { echo "Cannot verify $name" >&2; exit 32; }
    echo "ASSET_VERIFIED $name SHA256:$expected"
  done 3< "release-$mode.parts.sha256"

  sha256sum -c "release-$mode.parts.sha256"
  [[ "$(ls release-"$mode".part-?? | wc -l | tr -d ' ')" == "$count" ]] || exit 33
  printf '=== ALL %s %s ASSETS INDEPENDENTLY VERIFIED ===\n' "$count" "$mode"

  dst="$OUT/restored-$mode"
  if [[ ! -e "$dst" ]]; then
    mkdir -p "$dst"
    cat release-"$mode".part-?? | tar -xf - -C "$dst"
  fi
  image_root="$dst/oci-split-$mode"
  [[ -s "$image_root/index.json" ]] || { echo "Missing OCI index" >&2; exit 34; }

  python3 - "$image_root" "$registry_sha" <<'PY'
import hashlib, json, pathlib, sys
root=pathlib.Path(sys.argv[1])
expected=sys.argv[2]
idx=json.loads((root/"index.json").read_bytes())
if len(idx["manifests"])!=1:
    raise ValueError("Not a single-index OCI image")
desc=idx["manifests"][0]
if desc["digest"]!="sha256:"+expected:
    raise ValueError("OCI index does not reference expected published digest")
manpath=root/"blobs"/"sha256"/expected
manifest_bytes=manpath.read_bytes()
if hashlib.sha256(manifest_bytes).hexdigest()!=expected:
    raise ValueError("OCI manifest SHA does not match GHCR")
manifest=json.loads(manifest_bytes)
total=0
for part in [manifest["config"], *manifest["layers"]]:
    hexhash=part["digest"].split("sha256:",1)[-1]
    if len(hexhash)!=64:
        raise ValueError("Unexpected OCI descriptor digest")
    filename=root/"blobs"/"sha256"/hexhash
    if filename.stat().st_size!=part["size"]:
        raise ValueError("OCI blob wrong length "+hexhash)
    h=hashlib.sha256()
    with filename.open("rb") as file:
        for chunk in iter(lambda:file.read(4*1024*1024),b""):
            h.update(chunk)
    if h.hexdigest()!=hexhash:
        raise ValueError("OCI blob SHA mismatch "+hexhash)
    if part in manifest["layers"]:
        total+=part["size"]
print(json.dumps({"status":"PASS","manifest":"sha256:"+expected,
     "layer_count":len(manifest["layers"]), "compressed_layer_bytes":total,
     "verified_blob_count":1+len(manifest["layers"])}),flush=True)
PY
  echo "=== OCI_RESTORED_AND_BLOBS_VERIFIED $mode $(date -u +%FT%TZ) ==="
done

echo "=== BOTH RELEASE BACKUPS INDEPENDENTLY RESTORED AND VERIFIED ==="
