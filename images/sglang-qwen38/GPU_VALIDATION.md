# Candidate GPU validation plan — Qwen38 SGLang image

**PREPARATION ONLY. No GPU Pod, new paid instance, new template, registry credential, or public package is created by this document.**

Candidate (built and pushed on 2026-10-10):

`ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd`

Candidate tag:
`ghcr.io/tommyfive/qwen38-sglang:candidate-cloudzy-4ad22cd0b56b`

Baseline:
`lmsysorg/sglang:dev-qwen38-27b-dflash2`
(index digest `sha256:616a3e97f45191af975896cfa644279096cb31bd408a071c2e99ca7209c3cafe`).

See [BUILD_RESULTS_2026-10-10.md](BUILD_RESULTS_2026-10-10.md) for verified build output and archived logs.

## Gate A: Registry access and image size (no GPU spend)

1. Package is **private**. Keep it private; register GHCR credentials in the **RunPod private container registry feature**, separate from application secrets and outside GitHub repository source. A registry credential needs permission to **read** the GHCR package; do not expose a personal token in environment variables, PR comments, logs or a template's public metadata.
2. RunPod CLI documents `--registry-auth-id` on `pod create` and `runpodctl registry list`. Confirm that the required credentials appear as a registry ID before using any paid GPU. If a user profile lacks registry support, do not flip the package public just to work around it.
3. On an authenticated existing machine with Docker Buildx, inspect the registry manifest (this does **not** download image layers):

       docker buildx imagetools inspect ghcr.io/tommyfive/qwen38-sglang:candidate-cloudzy-4ad22cd0b56b
       docker buildx imagetools inspect --raw ghcr.io/tommyfive/qwen38-sglang:candidate-cloudzy-4ad22cd0b56b | python3 images/sglang-qwen38/manifest-size.py

   If `imagetools --raw` returns a multi-platform index, select the `linux/amd64` manifest digest and inspect that digest instead. Record compressed decimal GB and largest layers. Compare with baseline **14.676 GB compressed**, not the candidate's 41.69 GB **uncompressed**.

4. Verify the registry tag's digest equals the pushed digest. An authenticated manifest read is sufficient; a full local Docker pull is optional and costly in network/disk.

**Non-deploying preparation now implemented:** The script
`images/sglang-qwen38/create-candidate-template.sh` is a **dry-run by default**,
pinned to the published manifest digest. It discovers the existing RunPod
`ghcr.io` registry-auth entry and (only with explicit
`QWEN38_CREATE_CANDIDATE_TEMPLATE=YES`) creates an **isolated** lean
candidate template, no Pod or GPU. The template includes the existing
bootstrap and a fail-closed guard that refuses to start SGLang with no
`SGLANG_API_KEY`. The user's existing `qwen38fast` launcher can then use the
returned test template ID through `QWEN38_TEMPLATE_PI`, injecting its normal
authenticated environment. No `create-templates.sh` or production template
change is required.

The authenticated RunPod CLI available on Mac mini currently lists **one**
registry credential entry named `ghcr.io`. Its ability to pull this particular
private GHCR package is still **untested**; no token contents were inspected.
Do not create a Pod before confirming these constraints and obtaining explicit
paid-GPU approval.

## Gate B: Isolated test template, no production changes

- Start with an **isolated test template** / Pod configured with the candidate **by pinned digest**, not with a mutable tag.
- Use a single **RTX PRO 6000 Blackwell 96-GB** GPU and the same cloud tier, region/data center, network volume and container disk size for both baseline/candidate when feasible.
- Use the **existing tested Qwen38 bootstrap** from `scripts/bootstrap-sglang-openwebui.sh` without changing the model startup flags. Minimal test initially: `SERVE_WEBUI=0`; do not install OpenWebUI or update Python runtime dependencies in the serving environment.
- Model: `sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4`; DFlash2 draft: `incoai/Qwen3.8-27B-DFlash2`; context 262144; CUDA 13.0.3, FlashInfer 0.6.17.
- Preserve Bearer authentication with `SGLANG_API_KEY`; never use unauthenticated public SGLang APIs. Keep SSH disabled unless an approved debug investigation explicitly needs it. Default 150 GB container disk capacity unless model storage requirements demonstrate otherwise.
- The RunPod CLI reference accepts `--registry-auth-id` for private pulls. It also documents `--terminate-after`. Require an independent cost time limit and verify it applies to the actual Pod created; avoid treating a local reaper on a sleeping Mac as the sole protection.
- Existing production RunPod templates and launchers **must not** be edited or overwritten to perform this experiment.

## Gate C: Runtime compatibility before any performance claim

On a **user-approved running test Pod**, record (with no secrets in output):

1. Image digest, time to image prepared, and whether local image cache is warm or unknown. Record Pod ID, data-center ID, region, GPU, cloud type (Community/Secure), start UTC and Docker image source.
2. `nvidia-smi` GPU type/VRAM; Python imports of `sglang`, `torch`, `flashinfer`; `torch.cuda.is_available()` and GPU capability. Do not change installed packages.
3. SGLang startup with the unmodified Qwen NVFP4 target and DFlash2 draft. Check FlashInfer attention backend, JIT imports/kernel requirements, CUDA graph capture, no NCCL/DeepEP/cuda errors, no silent unquantized fallback.
4. Authenticated `GET /v1/models` and short `/v1/chat/completions`; verify token authentication is **rejected** when missing/wrong and accepts correct key.
5. Short warmup, then **five** identical runs using the existing `qwen38bench` benchmark procedure (TTFT, output tok/s, speculation accepted length when available), alongside model VRAM use. Compare with baseline median **150.7 tok/s** from the older report, but do not treat different host cache/GPU load as equivalent conditions.
6. Measure full **time-to-first-inference** in phases (image pull/extract, model/draft weight downloads, model load into VRAM, CUDA warmup, first successful authorized output); cold/warm cache labels matter more than aggregate wall-clock alone.
7. Only then test Full OpenWebUI and the remaining Qwen38 stack features; never merge image PR or replace prod images solely on successful imports.

## Gate D: Acceptance and rollback

**Accept** if there are no loss-of-function regressions relative to the reference, no critical CUDA/FlashInfer errors, no auth regression, and observed cold-start time and/or image bytes measurably improve with comparable host/cache conditions.

**Reject / rollback** if the candidate fails model startup, lacks JIT cubins, loads NVFP4 unquantized, breaks DFlash2/CUDA graphs, makes startup materially slower or leaks unauthenticated API access. Terminate the paid test Pod after collecting logs. Maintain old reference template unchanged.

If the GHCR manifest size is equal or larger than baseline, prioritize investigating optional extras/large unchanged CUDA/Python dependencies *before* spending on GPU cold-start A/B measurements, while allowing a limited compatibility smoke test if separately authorized.

## Future-run measurement schema (fill in per run)

| Field | Value |
|---|---|
| Run ID / Pod ID | To measure |
| UTC Pod create/start/end | To measure |
| Image reference (immutable digest) | To measure |
| Cloud tier (Community / Secure) | To measure |
| Region / DC / GPU type | To measure |
| Image prepare start/end | To measure |
| Image source pull cache state | cold / warm / unknown |
| Model download start/end & bytes | To measure |
| VRAM load start/end | To measure |
| First authenticated inference | To measure |
| VRAM peak & context | To measure |
| TTFT p50, tokens/sec p50 (5 warmed runs) | To measure |
| Full logs archive path and SHA256 | To measure |

Cross-reference [cold-start issue #11](https://github.com/TommyFive/qwen38-runpod-stack/issues/11) and draft [PR #21](https://github.com/TommyFive/qwen38-runpod-stack/pull/21).

RunPod Pod CLI reference: https://docs.runpod.io/runpodctl/reference/runpodctl-remove-pods
