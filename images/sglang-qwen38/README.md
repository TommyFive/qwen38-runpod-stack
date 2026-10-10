# Qwen38 experimental minimal SGLang image

**Status: candidate only; not yet built, published, or GPU-tested.**
This module is intentionally independent of the Qwen38 launcher, Tailscale,
privacy, RAM storage, and the four existing RunPod templates.
Background: [cold-start issue #11](https://github.com/TommyFive/qwen38-runpod-stack/issues/11).

## Why

The Community Cloud reference is lmsysorg/sglang:dev-qwen38-27b-dflash2 at
index digest sha256:616a3e97f45191af975896cfa644279096cb31bd408a071c2e99ca7209c3cafe.
Its linux/amd64 manifest measures 14.676 GB compressed in 68 layers.
The observed image-preparation time was ~4m41s (2026-10-10).
Two dominant uncached layers are 3.960 GB (Python/ML dependencies)
and 2.555 GB (FlashInfer artifacts).

An unrelated v0.5.21 runtime image is 13.725 GB, but is NOT a drop-in
replacement; it also has a 7.533 GB single layer. Image size alone does
not predict cold-start wall-clock time.

## First experiment

- Hard-pin the exact upstream SGLang Git commit and two Git blob IDs
  in [upstream.lock.json](upstream.lock.json).
- Verify clean checkout, commit SHA and original pyproject/Dockerfile blobs;
  fail closed if anything differs.
- Add exactly one empty PEP 621 optional extra named qwen38-minimal. Select it
  with BUILD_TYPE=qwen38-minimal. This keeps **all base dependencies** while
  excluding the upstream all extras: diffusion, HTTP/2 and OpenTelemetry.
- Build upstream's existing runtime target on the same SGLang commit.
- Keep CUDA 13.0.3, FlashInfer 0.6.17, FlashInfer JIT cache ON and
  BRANCH_TYPE=local. Do not silently drop needed JIT kernels.
- Keep model weights, draft weights, keys and Tailscale credentials OUT
  of the container image. No RunPod configuration changes.

This is only source-code pinning, not a bit-for-bit reproducible build:
CUDA base image tags and external package indices can change over time.
Pin the resulting container digest before GPU validation.

## CI and approved build host

Image-path PR/push checks run Python unittest and Bash syntax verification
on ordinary GitHub runners without Docker, GPUs or cloud cost.

The heavyweight [image build workflow](../../.github/workflows/qwen38-image-build.yml)
is manual-only and requires a self-hosted Linux x64 runner specifically
labeled qwen38-build. Provision that runner ONLY on an approved dedicated
build host, NOT Salty/Rusty/Cloudzy or any VPN/Passwall production VPS.
Prepare Docker Buildx and significant fast SSD space (budget at least
200 GiB free; observe actual usage). Manual GitHub workflow_dispatch is
normally available after the workflow file is on the default branch.

On an approved Linux x86_64 build host only, the following runs a local
Docker build and does NOT launch a RunPod pod or push to GHCR:

    bash images/sglang-qwen38/build-image.sh --tag ghcr.io/tommyfive/qwen38-sglang:candidate-manual

The manual workflow has a separate publish=false default. To push, the
workflow input must explicitly be true. Direct script publishing also
requires both --push and QWEN38_IMAGE_PUBLISH=YES. GHCR visibility is
independently managed. Nothing changes the four RunPod templates.

## Required validation before rollout

1. Build on the dedicated AMD64 runner. Record actual image digest, size,
   layer count, kernel assets and build provenance.
2. Run identical source-image/candidate-image tests on RTX PRO 6000:
   same region, cloud class, storage, Qwen NVFP4 model + DFlash2 draft
   and network profile. Label host cache cold/warm honestly.
3. Verify SGLang/PyTorch, CUDA and FlashInfer JIT, NCCL/DeepEP, CUDA graph
   capture, 262K configuration, authenticated first inference, and logs.
4. Measure image pull and extraction, complete time-to-first-inference,
   VRAM usage, TTFT and steady-state tokens/s; reject meaningful regressions.
5. Revalidate portless Tailscale and mandatory Bearer, Full/Lean OpenWebUI,
   RAM/SSD and optional RAM release against the ongoing integration PRs.
6. Keep original upstream image as rollback. No template/launcher switch
   without explicit approval.
7. Aim for >=5 comparable starts per cohort before interpreting median/p95.

No GPU performance or cold-start gain has been measured for this candidate.
The first candidate changes both the build target and dependency extra;
an additional framework_final + minimal comparator can isolate those effects.

## Later experiments, not part of this candidate

FlashInfer 0.6.18 or 0.7 arch-specific caches, image registry mirrors,
and Secure-vs-Community host caching comparisons must be measured separately.
