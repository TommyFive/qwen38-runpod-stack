# Qwen38 candidate image — evidence-based largest-layer audit (2026-10-11)

**Status:** Source/history analysis complete; no new image build or GPU test authorized or performed. Changes below are *proposals*, not tested runtime removals. Do not merge PR #21 or alter production templates on this basis alone.

## Exact evidence and attribution

- Published private GHCR candidate: `ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd`.
- Verified authenticated manifest inspection: **12,907,436,335 bytes compressed**, 31 layers; baseline **14.676 GB** (rounded) compressed, 68 layers. This is **1.769 GB / approximately 12.1% smaller**.
- Candidate largest compressed layer: **6.981 GB** (rounded), about **54.1%** of the total.
- Archived Docker image history (`image-history.txt`): largest *uncompressed* layer **17.1 GB** (rounded), created by:

      COPY /opt/sglang/lib/python3.12/site-packages /opt/sglang/lib/python3.12/site-packages # buildkit

- All other uncompressed layers in the archived history are **4.89 GB or smaller**. Thus, the 6.981 GB compressed blob must correspond to this unique 17.1-GB Python `site-packages` layer (compressed data cannot plausibly exceed a 4.89-GB source layer by more than 2 GB). **The per-layer compressed digest/metadata was not included in the user's displayed size-only summary**, but the size attribution is decisive.
- Exact source: pinned upstream SGLang commit `5f55db35e926d50676f75b812640ea2410b0fe0e`, file `docker/Dockerfile`, **line 790**. The project pin verified the original upstream Dockerfile blob prior to injecting the empty `qwen38-minimal` extra.

## Why the directory is so large

The runtime stage copies the **complete** Python site-packages directory built by the `framework_final` stage, rather than a subset of imports.

The pinned `python/pyproject.toml` base dependencies include mandatory or runtime-sensitive GPU libraries (including `torch==2.13.0`, `flashinfer_python[cu13]==0.6.17`, `sglang-kernel==0.4.6.post1`, `sgl-deep-gemm`, `sgl-deep-ep`, NVIDIA Cutlass/CUDA bindings, tilelang and others). The existing `qwen38-minimal` extra only removes *optional* `all` extras. The **base dependency list stays intact** by deliberate design.

The Dockerfile also *explicitly installs* Python tooling in `framework` at lines **516–535**:
`datamodel_code_generator`, `pre-commit`, `pytest`, `black`, `isort`, `icdiff`, `uv`, `wheel`, `scikit-build-core`, `py-spy`, `cubloaty`, `google-cloud-storage`, `pandas`, `matplotlib`, `tabulate`, `termplotlib`, `runai-model-streamer[s3,gcs,azure]`.

These packages are present by build instructions, but the exact per-package byte counts are **not known from the saved Docker history**. Some tools appear development-only, but others serve optional runtime use cases or dependency loading. Removing them without dependency and GPU verification is unsafe.

## Other large image-history layers (uncompressed; NOT the 6.981-GB blob)

| History size | History creation | Optimization significance |
|---|---|---|
| **4.89 GB** | CUDA devel base, `cuda-cudart-dev` and CUDA command-line development packages | Candidate for a future runtime-only CUDA base analysis, but SGLang explicitly requires nvcc/JIT; high regression risk |
| **2.12 GB** | CUDA runtime libraries package installation | GPU-essential components, high regression risk |
| **2.08 GB** | `COPY /sgl-workspace /sgl-workspace` | Separate audit target, may include source/workspace not needed for serving |
| **1.55 GB** | Runtime apt-installed Python/runtime/JIT dependencies | Mixed necessary and optional packages; do not blindly prune |

Uncompressed layer sizes are not directly comparable with compressed registry size. Do not add them to predict pull times or savings.

## Optimization options, in recommended order

1. **Measure package-level footprint first**, on an already explicitly approved candidate GPU Pod (or a future cheap CPU/VM if separately authorized). The new read-only utility
   `images/sglang-qwen38/inspect-site-packages.py` recursively totals logical file sizes for each top-level package under
   `/opt/sglang/lib/python3.12/site-packages`, without importing packages, following symlink targets or making network calls.
   It does **not** download image layers. It cannot be run against a deleted ECS VM.
2. **Low-risk, opt-in v2 variant:** In the *framework_final stage before the runtime COPY*, eliminate demonstrably unused non-runtime developer/test tooling, dist-info/test data, redundant caches, and other verified unnecessary contents. Only target packages after observing installed footprints, tracing imports and validating all mandatory serving paths. **Deleting after the final COPY in the runtime image creates whiteouts; it does not reclaim bytes from the preceding 17.1-GB copied layer.** Removing files in the builder before COPY is necessary to shrink the final compressed layer.
3. **Workspace 2.08-GB layer:** Find subdirectories that can be excluded while preserving editable SGLang imports, native binaries, kernels metadata, DFlash2 and model-specific functionality. The upstream `.dockerignore` already filters many generated artifacts; do not assume all 2.08 GB is redundant.
4. **High-risk later experiment:** Compare CUDA *runtime* vs *devel* base only if all required `nvcc`, JIT and Triton/NCCL/FlashInfer compilation paths remain available or can be separately provisioned. The pinned upstream Dockerfile explicitly uses `nvidia/cuda:13.0.3-cudnn-devel-ubuntu24.04` for JIT (line 699); replacing it blindly can make the image smaller but unusable.
5. **Build-time separate opportunity:** `hpc_ops_builder` compiles x86_64 wheels and the upstream Dockerfile comments that some kernels are sm90a-only (line 424). Target GPU is SM120. Investigate whether this stage is necessary for the Qwen38 serving path before disabling it. Its observed build step cost was **311.1 seconds**, but this is not necessarily a 5-minute wall-clock saving due to parallelism.

## Validation guardrails

Never remove blindly:
- `torch` / Triton / `nvidia-*` GPU libraries and their binary wheels;
- `flashinfer_python`, its JIT cache or matching `sglang-kernel` cubins;
- `sgl-deep-gemm`, `sgl-deep-ep`, CUDA graph/nvcc JIT dependencies;
- SGLang's editable package paths, runtime scripts, model/draft requirements;
- Authenticated API or pod security prerequisites.

Keep the existing v1 digest as an immutable rollback. A v2 experimental image must use a separate tag, undergo offline source validation, a documented size comparison and paid GPU smoke test **only after a separate explicit authorization**.

## Current measurement limit

The ECS machine and its runtime filesystem have been deleted, and the archived material includes Docker history, BuildKit logs and build records — **not the content listing of the 17.1-GB Python layer**. Consequently this audit identifies the exact heavy Dockerfile instruction and optimization candidates, **but cannot identify measured package-by-package byte counts or prove which packages can be safely deleted**. Those require an authorized running container or the download/extraction of relevant image layers.

Source: [Pinned SGLang Dockerfile](https://github.com/sgl-project/sglang/blob/5f55db35e926d50676f75b812640ea2410b0fe0e/docker/Dockerfile), [pinned pyproject](https://github.com/sgl-project/sglang/blob/5f55db35e926d50676f75b812640ea2410b0fe0e/python/pyproject.toml), [measured build results](BUILD_RESULTS_2026-10-10.md).
