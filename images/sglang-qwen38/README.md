# Qwen38 experimental minimal SGLang image

**Status (2026-10-11): candidate built on Alibaba ECS and successfully pushed to private GHCR; not yet GPU-tested or merged.** See [measured build results](BUILD_RESULTS_2026-10-10.md), [GPU validation plan](GPU_VALIDATION.md), and [compressed manifest-size tool](manifest-size.py).
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
uses a GitHub-hosted **ubuntu-24.04 (x86_64)** runner with Docker Buildx.
It does **not** run automatically on code pushes. To request another build
from draft PR #21, add the issue/PR label `run-qwen38-image-build`
(remove and re-add it for another explicit run). Alternatively, once the
workflow file exists on the default branch, use `workflow_dispatch`.
A runner performs an initial SDK cleanup and aborts before the build if
fewer than 100 GiB are free in the Docker root filesystem. The first
hosted runner reported a ~145 GB root filesystem with ~86 GB available
before cleanup; available disk space is verified on each fresh runner.

**First GitHub-hosted attempt:** [Actions run #38042274792](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38042274792)
ended in `failure` after ~58 minutes. Checkout, offline tests,
SDK cleanup and Docker-space preflight passed. The Docker-build step
was the last observed active step, but GitHub job metadata retains
its stale `in_progress` status despite the completed failed job.
The job log download currently fails with `404 BlobNotFound`, so the
actual root cause (OOM, disk, compiler, runner termination, etc.)
**has not been established**. Do not infer a successful container or
a memory root cause. Do not rerun blindly.

### Durable diagnostics before a second expensive attempt

The next build has added two independent diagnostic paths. After an
Actions API probe returned HTTP 403 despite declared `issues: write`,
an additional `pull-requests: write` scope was requested and the
**same PR-comment API operation succeeded (HTTP 201)** in isolated
[permission-check Actions run #38050861785](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38050861785).
A one-time successful test comment is visible on PR #21. The cause of
GitHub's unusual permission behavior is not otherwise proven.

Before a **future** heavy PR-triggered build, the workflow now creates a
status comment as a mandatory preflight; if this fails it stops **before**
clearing SDKs or compiling anything. The watchdog receives that comment ID
and updates it instead of creating another one. This preflight was added
*after* build #2 started and therefore does **not** repair its live monitor.

The next build has added two independent diagnostic paths:

- The BuildKit console output is saved to a local file with
  `BUILDKIT_PROGRESS=plain` and uploaded by
  `actions/upload-artifact` on normal success/failure. It is retained
  for 7 days and **never** copied into PR comments.
- An independent, restricted watchdog samples free disk, available RAM,
  cgroup `oom_kill`, build log byte count and numeric BuildKit stage ID,
  including **used/total/free SSD**, **used/total/available RAM**, and percentages.
  It writes one **sanitized** PR #21 comment and updates it every 120 seconds
  during the first 30 minutes, then **every 30 seconds from minute 30**.
  Actions stdout receives a sanitized resource sample every 30 seconds.
  PR comments use GitHub API `issues:write` permission. This
  survives loss of normal job logs if GitHub accepted an earlier checkpoint.
  Raw logs, environment, tokens and paths are not posted. The build child
  does not receive the GitHub API token.
- The watchdog interrupts its **isolated** build process group if free SSD
  falls below 12 GiB or available RAM is below 1.5 GiB for three consecutive
  30-second samples. These are safety limits, not predictions of build success.

A total runner disappearance can also prevent an artifact upload or the
*last* checkpoint. The last successfully written PR comment remains durable,
but an exact root cause may still require GitHub Support. An interrupted
build must not be treated as complete.

No automatic rerun was triggered when these diagnostics were added.
To authorize the next heavy build, explicitly add the PR label
`run-qwen38-image-build`; the label triggers the single-PR hosted build.

A direct build on an *approved* Linux x86_64 host remains possible,
but never compile on Salty, Rusty, Cloudzy or VPN/Passwall hosts:

    bash images/sglang-qwen38/build-image.sh --tag ghcr.io/tommyfive/qwen38-sglang:candidate-manual

Publishing is default-off. Only a workflow dispatch with `publish=true`
or an explicitly guarded `--push` invocation may publish a candidate.
GHCR visibility is managed independently. No action changes RunPod templates.

## Second hosted build: confirmed resource-pressure failure (2026-10-10)

[Actions #38049903745](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38049903745)
finished with `failure`. The runner's job log **became available after
completion**, although BuildKit's separate upload artifact was skipped.
The independent watchdog **did run**: its stdout includes 30-second samples.
PR-comment updates were denied `HTTP 403 Resource not accessible by
integration` under `issues:write` alone. A separate isolated CI check
later confirmed `HTTP 201` after requesting **both** `issues:write`
and `pull-requests:write` (current workflow includes both), and a
mandatory comment preflight was added for any future heavy PR build.

Last meaningful watchdog readings:

| Time UTC | RAM used / total | SSD free |
|---|---|---|
| 12:07:07 | 13.28 / 15.61 GiB | 60.08 GiB |
| 12:07:37 | 14.49 / 15.61 GiB | 60.07 GiB |
| 12:08:09 | **15.51 / 15.61 GiB (99.4%)** | **60.06 GiB** |

Then the runner reported exit code `143` and a shutdown signal around
12:08:55 UTC. RAM saturation was the most likely immediate trigger;
`cgroup_oom_kill` was unavailable and a kernel OOM kill is not proved.
**Disk space was not the bottleneck** when the runner shut down.

The previous watchdog required 3 consecutive RAM samples below 1.5 GiB,
too slow for the observed pressure increase. The new guard stops an isolated
build group immediately below 1.25 GiB available, or after 2 consecutive
30-second samples below 2.5 GiB. This can prevent some abrupt host shutdowns
and preserve logs, but does **not** fix the underlying high-memory build.
No third image build is authorized or running. Before retrying, reduce
BuildKit stage parallelism and/or select a host with substantially more RAM;
validate the actual peak footprint rather than assuming 16 GiB is sufficient.

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
