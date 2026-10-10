#!/usr/bin/env bash
# Explicit opt-in image build: run ONLY on an approved dedicated Linux x86_64 build host.
# No RunPod API calls, no pod launches, no production-VPS compilation.
set -Eeuo pipefail
umask 077

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK="$HERE/upstream.lock.json"

usage() {
  echo "Usage: bash images/sglang-qwen38/build-image.sh --tag ghcr.io/tommyfive/qwen38-sglang:candidate-XYZ [--push]" >&2
  echo "Default: build locally with --load. --push requires QWEN38_IMAGE_PUBLISH=YES." >&2
  exit 64
}

TAG=""
OUTPUT="--load"
while (($#)); do
  case "$1" in
    --tag) (($# >= 2)) || usage; TAG="$2"; shift 2 ;;
    --push) OUTPUT="--push"; shift ;;
    *) usage ;;
  esac
done
[[ "$TAG" =~ ^ghcr\.io/tommyfive/qwen38-sglang:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]] || usage
if [[ "$OUTPUT" == "--push" && "${QWEN38_IMAGE_PUBLISH:-}" != "YES" ]]; then
  echo "Refusing to publish without QWEN38_IMAGE_PUBLISH=YES" >&2
  exit 64
fi
[[ "$(uname -s)" == "Linux" && "$(uname -m)" == "x86_64" ]] || {
  echo "This heavyweight build requires an approved Linux x86_64 build host" >&2; exit 1;
}
for tool in git docker python3; do command -v "$tool" >/dev/null || {
  echo "Missing: $tool" >&2; exit 1;
}; done
docker buildx version >/dev/null

lock_value() {
  python3 - "$LOCK" "$1" <<'PY'
import json,sys
with open(sys.argv[1],encoding="utf-8") as f: lock=json.load(f)
value=lock[sys.argv[2]]
if not isinstance(value,str): raise SystemExit("Expected string in lock")
print(value)
PY
}
REPOSITORY="$(lock_value upstream_repository)"
COMMIT="$(lock_value upstream_commit)"
CUDA="$(lock_value cuda_version)"
FLASHINFER="$(lock_value flashinfer_version)"
TARGET="$(lock_value target)"
BUILD_TYPE="$(lock_value build_type)"
BRANCH_TYPE="$(lock_value branch_type)"
PLATFORM="$(lock_value platform)"
JIT_CACHE="$(python3 - "$LOCK" <<'PY'
import json,sys
with open(sys.argv[1],encoding="utf-8") as f: data=json.load(f)
print("1" if data["flashinfer_jit_cache"] is True else "0")
PY
)"
[[ "$REPOSITORY" == "https://github.com/sgl-project/sglang.git" ]] || exit 1
[[ "$COMMIT" =~ ^[a-f0-9]{40}$ && "$TARGET" == runtime &&
   "$BUILD_TYPE" == qwen38-minimal && "$BRANCH_TYPE" == local &&
   "$PLATFORM" == linux/amd64 && "$CUDA" == 13.0.3 &&
   "$FLASHINFER" == 0.6.17 && "$JIT_CACHE" == 1 ]] || {
  echo "Unexpected lock values: review required" >&2; exit 1;
}
WORK="$(mktemp -d "${TMPDIR:-/tmp}/qwen38-image-build.XXXXXXXX")"
trap 'rm -rf "$WORK"' EXIT
SOURCE="$WORK/sglang"
mkdir -p "$SOURCE"
git -C "$SOURCE" init -q
git -C "$SOURCE" remote add origin "$REPOSITORY"
git -C "$SOURCE" -c protocol.version=2 fetch --quiet --filter=blob:none --depth=1 origin "$COMMIT"
git -C "$SOURCE" checkout --quiet --detach FETCH_HEAD
python3 "$HERE/prepare-source.py" --source "$SOURCE" --lock "$LOCK"
echo "Building pinned SGLang ${COMMIT:0:12} -> $TAG ($OUTPUT)"
echo "Target: runtime; base dependencies only; FlashInfer 0.6.17 JIT cache retained."
# A full source build can be large and slow; never run on VPN/Passwall production VPS.
docker buildx build \
  --platform "$PLATFORM" \
  --file "$SOURCE/docker/Dockerfile" \
  --target "$TARGET" \
  --build-arg "BRANCH_TYPE=$BRANCH_TYPE" \
  --build-arg "BUILD_TYPE=$BUILD_TYPE" \
  --build-arg "CUDA_VERSION=$CUDA" \
  --build-arg "FLASHINFER_VERSION=$FLASHINFER" \
  --build-arg "INSTALL_FLASHINFER_JIT_CACHE=$JIT_CACHE" \
  --build-arg "SGLANG_BUILD_COMMIT=$COMMIT" \
  --build-arg "SGLANG_IMAGE_TAG=$TAG" \
  --tag "$TAG" \
  "$OUTPUT" \
  "$SOURCE"
echo "Build completed: $TAG ($OUTPUT)"
