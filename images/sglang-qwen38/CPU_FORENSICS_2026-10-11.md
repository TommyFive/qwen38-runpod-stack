# Qwen38 SGLang minimal-v2 — completed CPU filesystem forensics (2026-10-11)

**Status:** Actual read-only inventory of the original published `minimal-v1` OCI image completed on a dedicated temporary Alibaba Frankfurt x86_64 ECS. No image was modified, built or published. No GPU, RunPod Pod, production VPN/VPS or production RunPod template was touched.

## Reproducibility and provenance

- **Unchanged image:** `ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd` (successful anonymous GHCR Docker pull and digest match).
- Compressed OCI baseline: **12,907,436,335 bytes (31 layers)**. Previous `docker image inspect` reported **41,686,416,816 bytes uncompressed layers**.
- The CPU scanner counted **155,634 regular files**, **1,444 symbolic links**, **365 installed dpkg packages**, **283 Python distributions**, **201 inspected large ELF dynamic objects**, and **27.971 GB summed logical bytes in the accessible merged filesystem**. The last quantity is **not** OCI registry bytes and **not** necessarily equivalent to Docker's virtual/aggregate layer size; historical layer data may include overwritten or deleted files, metadata, and differences in accounting.
- Examined exact file paths, logical bytes, Python dependency metadata, dpkg installed-size, ELF DT_NEEDED/RUNPATH, architecture names and SHA256 hashes. All image-container probes used `--read-only --network none --cap-drop ALL --security-opt no-new-privileges`; no CUDA code, external app runtime or GPU was executed.
- Analysis scripts: `cpu-audit/run-collect.sh`, `collect.py`, `analyze.py`, `native-deps.py`, `subtree-report.py`, `compare-cuda-copies.py`, `verify-duplicates.py` and `inspect-flashinfer-artifacts.py`.
- Original raw JSONL evidence, summary, logs and checksums backed up privately from ECS to the Mac mini. **Backup SHA256:** `9068c1ce0e590102eb5b466dbf7601b7d711e697f3b9c396cc62b0f09da13b69`; **2.4 MB gzip archive**. This backup is not a Docker layer or image; the ECS image remains unchanged.

## High-leverage findings, directly measured (all sizes logical/uncompressed)

| Component | Evidence | Potential approach | Risk |
|---|---|---|---|
| `/sgl-workspace/sglang/rust/target` | **1.939 GB**, mostly `release/deps` **1.800 GB** | Strip intermediate Rust compiler artifacts in `framework_final` **before** runtime workspace COPY. Preserve runtime `.so` and independently verify bindings. | Low–medium with selective whitelist |
| Rust `.rlib` and `.rmeta` alone | **0.998 + 0.667 = 1.665 GB** | Remove build-only archive/metadata extensions first, NOT whole `rust/target`. Workspace also contains `libsglang_server.so` and other shared libs. | Low–medium |
| `/opt/nvidia/nsight-compute` | **1.303 GB**, dpkg `nsight-compute-2025.3.1` ~**1,244 MiB** | Specialized base stage without profiler. | Low inference relevance, requires base rebuild/repack |
| CUDA toolkit `/usr/local/cuda-13.0` | **5.313 GB**, including **2.564 GB `.a` static archives** | Audit static libraries individually; retain NVCC, NVVM, ptxas, NVRTC, required headers/libraries for SM120 JIT. | High |
| `flashinfer_cubin` | **4,691,858,760 bytes**, 46,172 files (4.641 GB `.cubin`) | Per-GPU/used-provider selection, not blanket removal. | High GPU compatibility and cold-start |
| Cubin path tokens naming other architectures | **2,909,679,460 bytes**: `100f` **2,040,927,000**, `107a` **820,751,048**, `103a` **48,001,412**; **no path explicitly named SM120** in this package | Test SM120 runtime usage, forward-JIT fallbacks and first-request timing before pruning. Tokens in paths are **not proof** of binary incompatibility/redundancy. | High |
| `flashinfer_jit_cache` | **2,054,683,357 bytes**; 198,692,920 bytes have explicit non-SM120 tags and 18,583,728 bytes explicit SM120 tags; 1,837,406,709 bytes lack an unambiguous token | Preserve unknown paths; trace NVFP4+DFlash2 JIT and lazy loads. | High |
| CUDA runtime duplicates (below) | **1,679,571,048 bytes for one copy of 11 distinct pairs**, each SHA256-equal | Replace only with validated symlinks while preserving Torch loader RUNPATH/package behavior, ideally in framework-final *before COPY*. | Medium–high |
| `nvidia_cutlass_dsl` | Approximately **181 MB CUDA12** + **180 MB CUDA13** native bindings | Evaluate removing cu12 branch only after versioned import testing. | Medium |
| `tokenspeed_triton` | `backends/amd/lib/libtriton_amd_codegen.so` **92 MB** | NVIDIA-only backend audit. | Medium |
| `hpc` wheel | **122 MB**; pinned upstream describes builder as SM90a-only | Evaluate missing usages on SM120 without removing SGLang import deps. | Medium |
| Distributed/non-text additions | `mscclpp` 249 MB, `mooncake` 136 MB, `runai_model_streamer` 140 MB, `pyarrow` 168 MB, `nixl_cu13.libs` 122 MB, `nixl_ep_cu13` 95 MB | Trace import and feature initialization in single-GPU text model, then trim safely. | Medium–high |

### CUDA duplicate verification (actual SHA256 proof)

Eleven pairs are **byte-for-byte identical**, despite differing filesystem paths and frequently different filenames/version suffixes. The SHA256 hashes are saved in `cuda-copy-comparison.jsonl` in the private evidence snapshot. Sizes below are for **one** redundant copy, not claimed compressed savings:

| Library | Bytes |
|---|---:|
| `libcublasLt` | 541,607,888 |
| `libcufft` | 286,542,352 |
| `libcusparse` | 162,565,256 |
| `libcusolver` | 141,152,872 |
| `libcurand` | 132,698,328 |
| `libnvrtc.alt` | 109,821,488 |
| `libnvrtc` | 109,338,064 |
| `libcusolverMg` | 103,956,840 |
| `libcublas` | 54,177,976 |
| `libnvperf_host` | 32,405,040 |
| `libnvperf_target` | 5,304,944 |
| **Total** | **1,679,571,048** |

**Crucial loader evidence:** `torch/lib/libtorch_cuda.so` declares DT_NEEDED on `libcufft.so.12`, `libcusparse.so.12`, `libcublasLt.so.13`, `libnvrtc.so.13`, `libnccl.so.2`, etc. Its RUNPATH explicitly contains `$ORIGIN/../../nvidia/cu13/lib`, `$ORIGIN/../../nvidia/cudnn/lib`, `$ORIGIN/../../nvidia/nccl/lib` and others. **Simply deleting Python wheel copies would break resolution**; moving to validated symlinks may work but needs clean-process GPU tests. SHA equality says *contents* are equal, not that paths or package metadata are interchangeable.

**Do not unify all apparent duplicates:** System `libnccl.so.2.32.3` is **343,864,936 bytes** while Python `libnccl.so.2` is **252,204,648 bytes**. Several system vs Python cuDNN files differ in size; preserve their versions. Baseline `pip check` already reports explicit NCCL version mismatch (Torch expects 2.29.7, installed 2.30.7; upstream overrides for DeepEP) and `nixl` referring to nixl-cu12 while cu13 is installed. These are **existing conditions**, not a new regression introduced by this audit.

## Why removals must occur at the correct build stage

- **Source/workspace:** Remove safe Rust intermediates in `framework_final` after compilation and before `COPY --from=framework_final /sgl-workspace /sgl-workspace`. Deleting them inside the published runtime merely adds overlay whiteouts and does not reclaim compressed v1 layer bytes.
- **Python wheels and FlashInfer:** Select or link files in the builder before `COPY --from=framework_final ...site-packages`. Never delete a kernel based solely on a filename token.
- **CUDA base/Nsight/static archives:** Those files belong to the inherited `nvidia/cuda:13.0.3-cudnn-devel-ubuntu24.04` base layers. A later `RUN rm` cannot shrink inherited OCI blobs. Evaluate a new specialized final stage from a smaller base with the **complete proven JIT toolchain** or a controlled **fresh-filetree repack** preserving all OCI config/metadata. Compare registry manifests, not filesystem `du`.

## Candidate and approval gates

1. **CPU source overlay A:** Whitelist removal of Rust `.rlib`/`.rmeta` intermediates and optional source/test/build files; static imports/ELF integrity checks. No production template change.
2. **CPU overlay B:** Only the eleven confirmed SHA-identical shared-library copies, replaced by tested paths/symlinks. Verify `DT_NEEDED`, RUNPATH, package resolutions and CPU-side import paths. Leave NCCL/cuDNN differences untouched.
3. **CPU overlay C:** Trace FlashInfer provider lookup and architecture-specific kernels; prepare separate SM120 experiment *without pruning ambiguous/unknown artifacts*. Include unknown architecture/fatbin handling.
4. **Separate high-risk base experiment:** CUDA runtime+selected NVCC/JIT components, leaving source CUDA 13.0.3/pinned Torch/FlashInfer/DeepGEMM unchanged. No unapproved CUDA builds.
5. **GPU validation:** On explicitly approved disposable RTX PRO 6000 SM120 Pod(s), use identical main NVFP4 model + DFlash2 draft and context settings; cold and warm startup; authenticated 256/512+ token benchmarks counted by `usage.completion_tokens`, JIT latency/cache/network dependency, long-context, API 200/401, 20-GiB RAM-first lean, SSD fallback, Full OpenWebUI and Tailnet as relevant. Any correctness, speed or cold-start regression blocks promotion.
6. **OCI release:** Compare compressed bytes/layer descriptors against **12,907,436,335** and secure config/secrets. Use new candidate tags and subsequently a **new** release tag, never overwrite `v0.2.0` or change production templates by default.

The 1.665 GB Rust metadata, 1.303 GB Nsight, 2.564 GB CUDA `.a`, 1.680 GB duplicate CUDA runtime files and 2.910 GB explicitly other-arch cubin paths are **distinct uncompressed candidate pools**, not promised removable bytes and not additive OCI registry savings. CUDA/JIT dependencies, packaging, hardlinks and layer compression must be proven before estimating the actual v2 pull-size difference.

### Lean versus Full

The current image does **not** ship OpenWebUI installed: the existing bootstrap provisions OpenWebUI separately at runtime only when `SERVE_WEBUI=1`. Therefore an image named `lean` without changing its GPU/model-specific content is unlikely to save meaningful registry bytes. An **SM120 + Qwen3.8 + DFlash2 specialized image** may be useful independently of template UI mode, with a general-purpose image retained for other GPUs/models.
