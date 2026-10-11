#!/usr/bin/env bash
# Separate candidate template. Dry-run by default: NO GPU POD is created.
# Actual (cost-free) template creation requires QWEN38_CREATE_CANDIDATE_TEMPLATE=YES.
set -Eeuo pipefail
umask 077
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
BOOTSTRAP="$ROOT/scripts/bootstrap-sglang-openwebui.sh"
IMAGE='ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd'
NAME='qwen38-candidate-isolated-4ad22cd0b56b'

if [[ "$(printenv QWEN38_CREATE_CANDIDATE_TEMPLATE 2>/dev/null || echo NO)" != YES ]]; then
  echo 'DRY RUN ONLY. No RunPod API change or paid GPU Pod.'
  echo "Candidate image: $IMAGE"
  echo "Isolated template: $NAME"
  echo 'Uses public GHCR and 20 GiB RAM-first disk; SGLang API key is required when deployed.'
  echo 'To create only the template: QWEN38_CREATE_CANDIDATE_TEMPLATE=YES bash images/sglang-qwen38/create-candidate-template.sh'
  exit 0
fi
[[ -r "$BOOTSTRAP" ]] || { echo "Missing existing Qwen38 bootstrap" >&2; exit 1; }
command -v runpodctl >/dev/null || { echo "Missing runpodctl" >&2; exit 1; }
command -v python3 >/dev/null || { echo "Missing python3" >&2; exit 1; }

# The pinned production GHCR digest is public: verify anonymous access.
python3 "$HERE/check-public.py" --quiet || {
  echo "Pinned GHCR digest is not anonymously pullable; refusing candidate template." >&2
  exit 1
}

# Default template cannot start an unauthenticated API: key is required.
# Actual launch via existing qwen38fast passes bootstrap+key in env override.
ENV_JSON="$(python3 - "$BOOTSTRAP" <<'PY'
import base64,json,pathlib,sys
bootstrap=pathlib.Path(sys.argv[1]).read_bytes()
guard=(b"#!/usr/bin/env bash\n"
       b"if [ -z \"$SGLANG_API_KEY\" ]; then\n"
       b"  echo 'ERROR: missing SGLANG_API_KEY; refusing public API' >&2\n"
       b"  exit 64\n"
       b"fi\n")
values={
  "BOOTSTRAP_B64":base64.b64encode(guard+b"\n"+bootstrap).decode(),
  "MODEL_ID":"sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4",
  "SERVED_NAME":"qwen38-uncensored",
  "MAX_LEN":"262144",
  "SPEC":"dflash2",
  "MEM_FRAC":"0.85",
  "MAMBA_RATIO":"4.59",
  "SERVE_WEBUI":"0",
  "ENABLE_SSH":"0",
}
print(json.dumps(values,separators=(",",":")))
PY
)"
echo "Creating isolated private-image RunPod template $NAME (no paid Pod)..."
runpodctl template create \
  --name "$NAME" \
  --image "$IMAGE" \
  --container-disk-in-gb 20 \
  --ports '8000/http' \
  --port-labels '8000=SGLang API' \
  --docker-start-cmd 'bash,-c,echo "$BOOTSTRAP_B64" | base64 -d > /bootstrap.sh && bash /bootstrap.sh' \
  --env "$ENV_JSON" -o json
echo 'RAM-first candidate template submitted (20 GiB); no paid GPU Pod started.'
echo 'After separate paid-Pod approval: QWEN38_TEMPLATE_PI=<new-template-id> qwen38fast --pi'
