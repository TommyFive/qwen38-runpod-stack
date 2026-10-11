#!/usr/bin/env bash
# CPU-only, opt-in, READ-ONLY inventory of the immutable v1 image.
# Never starts GPU, builds containers, installs packages, publishes artifacts,
# removes files or communicates with RunPod. No runtime image code is imported.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd"
docker image inspect "$IMAGE" >/dev/null
test -f "$ROOT/collect.py"
test -f "$ROOT/analyze.py"
for mode in files python dpkg; do
  echo "=== INVENTORY $mode: $(date -u +%FT%TZ) ==="
  docker run --rm --pull never --read-only --network none \
    --cap-drop ALL --security-opt no-new-privileges --pids-limit=256 \
    --mount "type=bind,src=$ROOT/collect.py,dst=/tmp/qwen38-collect.py,readonly" \
    --entrypoint /opt/sglang/bin/python3 "$IMAGE" \
    -I -S /tmp/qwen38-collect.py --mode "$mode" > "$ROOT/$mode.jsonl"
  wc -cl "$ROOT/$mode.jsonl"
done
echo "=== INVENTORY ANALYZE ==="
python3 "$ROOT/analyze.py" --folder "$ROOT"
echo "=== BASIC RUNTIME PROBES ==="
docker run --rm --pull never --read-only --network none \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit=256 \
  --entrypoint /bin/bash "$IMAGE" \
  -lc 'set -u; echo CUDA; nvcc --version 2>&1 | tail -n 5; echo TOOLPATHS; for x in readelf cuobjdump ptxas nsys ncu gcc g++ git make cmake pip py-spy; do command -v "$x" || true; done; echo DEPENDENCIES; /opt/sglang/bin/python -m pip check || true; echo LIBCACHE; ldconfig -p | wc -l' > "$ROOT/probes.txt" 2>&1
sha256sum "$ROOT/files.jsonl" "$ROOT/python.jsonl" "$ROOT/dpkg.jsonl" "$ROOT/summary.json" > "$ROOT/checksums.sha256"
echo "=== COMPLETE $(date -u +%FT%TZ) ==="
