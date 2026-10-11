#!/usr/bin/env bash
# Safe CPU-only pre-GPU smoke: original v1 versus ephemeral modified builder.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
V1="ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd"
B="local/qwen38-cpu-test:rust-cuda"
for item in baseline:$V1 modified:$B; do
  label="${item%%:*}"
  image="${item#*:}"
  echo "=== SMOKE $label $(date -u +%FT%TZ) ==="
  timeout 180 docker run --rm --pull never --read-only --network none \
    --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 \
    --tmpfs /tmp:rw,nosuid,size=128m \
    --tmpfs /root/.cache:rw,nosuid,size=256m \
    --entrypoint /opt/sglang/bin/python3 "$image" \
    -c 'import importlib,sys,time
for mod in ("torch","flashinfer","sglang","transformers"):
  begin=time.monotonic()
  x=importlib.import_module(mod)
  version=getattr(x,"__version__","unknown")
  print(f"IMPORT {mod}: OK in {time.monotonic()-begin:.2f}s; version={version}",flush=True)
print("PYTHON",sys.version.split()[0])' \
    > "$ROOT/smoke-$label.log" 2>&1 || {
      code="$?"
      echo "SMOKE $label FAILED exit=$code"
      tail -n 18 "$ROOT/smoke-$label.log"
      exit "$code"
    }
  tail -n 6 "$ROOT/smoke-$label.log"
done
echo "=== BASIC CPU IMPORT COMPARISON PASSED ==="
