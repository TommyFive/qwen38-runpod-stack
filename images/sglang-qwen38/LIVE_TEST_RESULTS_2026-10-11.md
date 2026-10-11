# RTX PRO 6000 candidate: live cold-start, package footprint and disk measurement (2026-10-11)

**Status:** Isolated paid RunPod test **STOPPED** at 2026-10-11T06:32:56Z. CPU/SSD analyses and user-approved GPU function/Cold-Start measurements were captured on the Mac mini. **This is one trial on an unhealthy provider host; do not treat its timings as a clean general baseline or proof of reliability.** The production RunPod templates were not changed.

## Provenance

| Parameter | Observed |
|---|---|
| Pod | `ynuxxmshzbu35k` |
| Host | US-NE-1, Secure Cloud, RTX PRO 6000 Blackwell Server Edition (96 GB), 16 vCPU, 251 GB RAM |
| Published candidate | `ghcr.io/tommyfive/qwen38-sglang:candidate-cloudzy-4ad22cd0b56b` |
| Verified image digest from GHCR publish | `sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd` |
| Compressed image size | **12.907436335 GB**, 31 layers, **12.1% smaller** than reference 14.676 GB |
| Runtime | SGLang; torch 2.13.0+cu130; NVIDIA CUDA compute capability (12, 0); NVFP4 main model with DFlash2 draft |
| Model storage | RAM-first `/dev/shm/qwen38-hf` |
| Configured container SSD | 150 GB (RunPod UI); 161061273600 bytes reported by `df` |
| GPU hourly price | $2.49/hour displayed; stop occurred after approximately 32 minutes. Billing is determined by RunPod, not calculated here. |
| Pod initially created | 2026-10-11T06:00:57.611Z |
| RunPod stopped (API verified) | 2026-10-11T06:32:56Z |
| Pod after stop | `runtimeStatus=stopped`, `desiredStatus=EXITED`; not deleted |
| GPU time protection | Dedicated 55-minute local watchdog was started and then disabled after the user's explicit stop request, so it cannot later delete the stopped Pod |

## Cold-start timeline (first, before provider host restart)

Times are UTC; China time = UTC+8.

| Event | UTC | Since create |
|---|---|---:|
| Pod created / RunPod provisioning | 06:00:57.611 | 0 s |
| First registry image-download evidence | 06:01:00 | 2.4 s |
| First image extraction evidence | 06:01:13 | 15.4 s |
| Container and Bootstrap begin | 06:04:03.094 | 185.5 s |
| Main + draft model downloads start | 06:04:03.952 | 186.3 s |
| Main + draft model downloads complete | 06:08:16.911 | 439.3 s |
| SGLang process start | 06:08:17.001 | 439.4 s |
| First internal generation-healthcheck succeeds | **06:09:36.310** | **518.7 s (8m39s)** |

Measured phases: **~3m05s** for provisioning/image fetch/extract; **4m13s** for model/download path in RAM; **~1m19s** from SGLang launch to internal successful generation.

**Critical qualification:** The first RunPod pull logged 15 image blobs as `Already exists`. It was **partially cached**, not a guaranteed wholly cold container pull.

## Provider host/container restart and second readiness

- The RunPod console displayed a **critical machine error warning** for the physical host in US-NE-1. Provider recommended backing up and redeploying.
- System events reported `stop container` at 06:12:20Z, `start container` ~06:12:23Z and another `restart container` ~06:12:50Z. This occurred **after first successfully generating at 06:09:36Z**.
- Bootstrap restarted again at **06:12:23Z** and **06:12:50Z**; the RAM model directory was reset so main/draft weights were re-fetched from 06:12:51Z through 06:16:06.792Z.
- The SGLang healthcheck succeeded again at **06:17:24.138Z** (16m27s after original create).
- Recorded authenticated chat API test first confirmed at **06:17:43Z** (16m46s after original create). **This is not first model inference** because internal generation succeeded at 06:09:36Z.
- A host failure is a **plausible**, but not technically proven, root cause of the restarts. Do not attribute this unambiguously to the Docker candidate; similarly do not label the candidate fully production-stable based on this affected trial.
- The numeric image cold-start result cannot be fairly compared with a new run in another host/region/cache state without marking the differences.

## GPU and authenticated API smoke

The saved `auth-smoke.jsonl` reports:

- CUDA available, device RTX PRO 6000 Blackwell Server Edition, capability 12.0.
- `torch==2.13.0+cu130`, and successful imports of SGLang and FlashInfer.
- `GET /v1/models` with correct Bearer key: HTTP **200**.
- No Bearer key: HTTP **401**.
- An authenticated chat completion succeeded.
- Five short warmed output traces: median **142.91 output tokens/s**, **0.050 s TTFT**, and **0.232 s total**, each with 27 completion tokens. These are **short functional smoke tests, not standardized 256/512-token DFlash2 production speed benchmarks**. Earlier baseline ~150.7 tokens/s was measured in a different run/setup and is not a rigorously controlled comparison.

## Read-only package footprint for further image size optimization

Full raw inventory saved as `site-packages.json` (~41KB) using `inspect-site-packages.py`. Python `site-packages` contains approximately **16.85 GB logical files**. Largest directories observed:

| Package/directory | Logical size, decimal GB (rounded) |
|---|---:|
| `flashinfer_cubin` | **4.69** |
| `nvidia` | **3.35** |
| `flashinfer_jit_cache` | **2.06** |
| `sgl_kernel` | **1.20** |
| `torch` | **1.09** |
| `triton` | **0.72** |
| `nvidia_cutlass_dsl` | **0.46** |

This measured footprint explains the archived ~17.1GB uncompressed `site-packages` COPY layer, which is the ~6.981GB **compressed** largest GHCR blob. The combined FlashInfer cubin + JIT entries (~6.75 GB logical) are the highest-leverage next inspection candidates **but are GPU startup/runtime-sensitive**. **Do not remove them without SM120 kernel compatibility profiling, CUDA/JIT testing and cold-start A/B verification**.

Deletion *after* final image COPY does not reclaim existing registry bytes due to Docker whiteouts: a test v2 must prune in the builder stage **before** the runtime `COPY` of the Python directory.

Remaining separate candidates from archived image history:
- ~2.08GB uncompressed `/sgl-workspace` copy; verify actual import paths/binary assets before pruning.
- Optional Python development tooling installed upstream, subject to dependency/reference and package-size verification.
- Changing CUDA devel base or NVIDIA libraries is high-risk (NVCC/JIT, FlashInfer/Triton) and not currently advised.

This is a **measured inventory**, not a complete runtime import-trace, comprehensive CUDA kernel usage map, or proof any package can be removed. A second smaller candidate must be built and validated separately.

## Container SSD sizing

Root overlay `df` reported **161,061,273,600 bytes total (150 GiB)**, peak recorded writable occupancy **~281 MB** during the smoke test. `/dev/shm` was independent RAM-backed tmpfs, **125,000,003,584 bytes total**, with ~**24.45 GB** occupied by main/draft checkpoints.

- The ~12.91GB compressed image / ~41.69GB uncompressed Docker layers were managed by RunPod's image storage outside the small observed writable root usage; the `df` result alone cannot prove RunPod will provision an arbitrarily small configured container disk.
- **Next controlled test recommendation: 20 GiB** container disk for the lean `SERVE_WEBUI=0, MODEL_STORAGE=ram` configuration. Consider 30 GiB if enabling OpenWebUI, SSD model fallback, debug builds, large logs, or changed model storage.
- This recommendation **is provisional** until a fresh 20-GiB Pod successfully pulls the image and reaches authenticated generation. Never reduce to 1 GiB merely because the observed writable layer is small.
- Because `/dev/shm` relies on host/container RAM, do not infer it can be reduced from these disk measurements.

## Preservation / next steps

All raw data and scripts needed for the next image optimization are on Mac mini:
`/Users/rentamac/.local/share/qwen38-coldstart-tests/qwen38-imgtest-20261011-060057/`.

The full pre-stop snapshot (private mode 0600):
`/Users/rentamac/.local/share/qwen38-coldstart-tests/qwen38-imgtest-20261011-060057-prestop.tar.gz`.

SHA256: `bb2f9caaca8391bdb4c9d19668d3589b5f74591866e6763428d15bafb2812028`.

Source files include `creation.json`, `plan.json`, `first-cold-summary.json`, `summary.json`, `diagnostic-phase.json`, `pod-events.jsonl`, `pod-status.jsonl`, `container-stream.jsonl`, `site-packages.json`, `auth-smoke.jsonl`, and watchdog logs. **The archive is local to the Mac mini; no independent external backup has been confirmed**. It is compressed, not the 12.9-GB container itself.

The host was reported unhealthy. For a fair cold-start A/B comparison, use the same GPU SKU, cloud tier, region/DC, container disk and model/draft settings and explicitly record `Already exists` layer caching. Avoid redeployment until a new paid GPU test is separately approved. A test using 20-GiB disk, a fresh healthy host and authenticated 256/512-token throughput should follow the size-optimization work.
