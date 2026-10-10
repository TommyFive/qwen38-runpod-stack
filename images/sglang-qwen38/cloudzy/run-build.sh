#!/usr/bin/env bash
# systemd one-shot build on disposable Cloudzy CPU VM; LOCAL image only.
set -Eeuo pipefail
umask 077
ROOT=/opt/qwen38-cloudzy/repo
LOGDIR=/var/log/qwen38-cloudzy
SHA=$(cat /opt/qwen38-cloudzy/source.sha)
[[ "$SHA" =~ ^[a-f0-9]{40}$ ]] || exit 1
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$SHA" ]] || exit 1
docker buildx inspect qwen38-cloudzy >/dev/null
mkdir -p "$LOGDIR"
TAG="ghcr.io/tommyfive/qwen38-sglang:candidate-cloudzy-${SHA:0:12}"
printf '%s\n' "$TAG" >"$LOGDIR/image-tag.txt"
printf '%s\n' "$SHA" >"$LOGDIR/repo-commit.txt"
: >"$LOGDIR/buildkit.log"
: >"$LOGDIR/resource-samples.jsonl"
echo "Build start $(date -u -Is); tag=$TAG; publish=false"
setsid env -u GH_TOKEN -u GITHUB_TOKEN BUILDKIT_PROGRESS=plain \
  bash "$ROOT/images/sglang-qwen38/build-image.sh" --tag "$TAG" \
  >"$LOGDIR/buildkit.log" 2>&1 &
pid=$!
python3 -u "$ROOT/images/sglang-qwen38/cloudzy/observer.py" \
  --pid "$pid" --log "$LOGDIR/buildkit.log" \
  --output "$LOGDIR/resource-samples.jsonl" --interval 30 &
mon=$!
trap 'kill "$mon" 2>/dev/null || true' EXIT
set +e
wait "$pid"
status=$?
set -e
printf '%s\n' "$status" >"$LOGDIR/exit-code.txt"
echo "Build ended $(date -u -Is) status=$status"
tail -n 30 "$LOGDIR/buildkit.log" || true
if ((status == 0)); then
  docker image inspect "$TAG" --format 'ImageId={{.Id}} UncompressedBytes={{.Size}}' \
    | tee "$LOGDIR/image-inspect.txt"
  docker history --no-trunc "$TAG" >"$LOGDIR/image-history.txt"
  echo "Image is LOCAL ONLY: publish/export before destroying VM"
else
  echo "Build FAILED; inspect buildkit.log and resource-samples.jsonl"
fi
exit "$status"
