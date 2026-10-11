#!/usr/bin/env bash
# Local-only, CPU-only validation after a fresh-scratch OCI export completed.
# NEVER pushes, runs a GPU, starts RunPod or mutates published images.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:?Usage: validate-oci.sh rust|rust-cuda}"
case "$MODE" in rust|rust-cuda) ;; *) exit 64 ;; esac
TAR="$ROOT/minimal-v2-$MODE.oci.tar"
if [[ ! -s "$TAR" ]]; then echo "ERROR missing OCI tar $TAR" >&2; exit 66; fi
FREE_GIB="$(df -BG "$ROOT" | awk 'NR==2 {gsub("G","",$4); print $4}')"
if (( FREE_GIB < 35 )); then
  echo "ERROR insufficient free space for CPU validation: ${FREE_GIB}GiB" >&2
  exit 73
fi
python3 "$ROOT/inspect-local-oci.py" "$TAR" > "$ROOT/$MODE-oci-result.json"
echo "OCI layer bytes, baseline delta:"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["compressed_layer_bytes"],d["delta_bytes"],round(d["saving_percent"],3))' "$ROOT/$MODE-oci-result.json"
echo "=== LOADING LOCAL ONLY $(date -u +%FT%TZ) ==="
docker load --input "$TAR" > "$ROOT/$MODE-load.log"
cat "$ROOT/$MODE-load.log"
CONFIG="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["config"])' "$ROOT/$MODE-oci-result.json")"
docker image inspect "$CONFIG" > /dev/null
NAME="local/qwen38-repacked:$MODE"
docker tag "$CONFIG" "$NAME"
python3 "$ROOT/verify-repack.py" --image "$NAME" --mode "$MODE" > "$ROOT/$MODE-verify.log"
echo "=== CPU IMPORT $MODE ==="
timeout 180 docker run --rm --pull never --read-only --network none \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 \
  --tmpfs /tmp:rw,nosuid,size=128m --tmpfs /root/.cache:rw,nosuid,size=256m \
  --entrypoint /opt/sglang/bin/python3 "$NAME" \
  -c 'import importlib; names=("torch","flashinfer","sglang","transformers"); [importlib.import_module(n) for n in names]; print("PASS:",names)' \
  > "$ROOT/$MODE-import.log" 2>&1
cat "$ROOT/$MODE-verify.log" "$ROOT/$MODE-import.log"
echo "=== VERIFIED LOCAL REPACK $MODE $(date -u +%FT%TZ) ==="
