# SGLang minimal-v2 — measured research and gated experiment plan (2026-10-11)

> **Historical research baseline (11 October); subsequently extended through 12 October.** After this research was written, two separate *CPU-only* minimal-v2 OCI candidates were built and published to a dedicated **nonproduction GHCR checkpoint package**. Both packages and all 25 backup parts were remotely verified. See [final emergency checkpoint](MINIMAL_V2_CHECKPOINT_2026-10-12.md), [recovery runbook](MINIMAL_V2_RECOVERY.md), and [CPU/GPU test issue #46](https://github.com/TommyFive/qwen38-runpod-stack/issues/46). **No GPU validation, runtime rollout or RunPod template changes** are claimed. The numbered research plan below is historical context, not the present status.

## Immutable reference

- GitHub project: `TommyFive/qwen38-runpod-stack`, latest released project tag **v0.2.1**. The separately published *container* is `ghcr.io/tommyfive/qwen38-sglang:v0.2.0`.
- Production v1 image digest: `sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd` (`linux/amd64`).
- Pinned SGLang: `5f55db35e926d50676f75b812640ea2410b0fe0e`; CUDA **13.0.3**; PyTorch **2.13.0+cu130**; FlashInfer **0.6.17**; DFlash2 and NVFP4 on actual **SM120**.
- Registry compressed bytes: upstream **14.676 GB** (rounded, 68 layers) and minimal-v1 **12,907,436,335 bytes** (31 layers). The improvement is **~12.1%** vs upstream.
- The single largest compressed v1 layer is **~6.981 GB**, matching a **~17.1 GB uncompressed** `COPY /opt/sglang/lib/python3.12/site-packages` instruction; this is already established in `LAYER_AUDIT_2026-10-11.md`.

### First-build forensic data: Mac mini (READ ONLY)

The original successful Alibaba ECS build is no longer reproducible from a local builder cache because the Frankfurt ECS was deleted. The original logs remain in private 0600 archives at:

`/Users/rentamac/.local/share/qwen38-cloudzy-builder-archives/`

Archive `qwen38-cloudzy-20261010T163023Z-4ad22cd0b56b.tar.gz`, previously recorded SHA256 `f8e965d3701ad979f03b40c2cbec2eb24d10499c29386aa57330b5c8819f234d` (verify before using). The audit report references `buildkit.log`, `resource-samples.jsonl`, `image-history.txt`, `image-inspect.txt`, build records, push logs and service journal. The private archive was located during this investigation; the SSH viewer allows ordinary file inspection, but *archive listing/decompression commands were rejected by its read-only policy*. Therefore the analysis below uses the archived figures **already documented in GitHub**, not a new extraction of this archive.

Historical measurements: first attempt terminated with SIGTERM (root cause unknown); successful partially cached attempt **42m31s**, overall attempts **59m51s**. Most expensive BuildKit steps: Rust gateway build **1008.2s**, `--load` export/import **680.3s**, framework/cubin retries **358.1s**, torch deps **321.3s**, HPC ops **311.1s**; durations overlap. Sampled RAM peak **45.81 GiB**, disk minimum free **146.92 GiB** on a 300-GiB ECS. These are **build-time** priorities and must not be confused with OCI size or cold-start benefits.

### Live v1 GPU inventory: Mac mini (READ ONLY)

`/Users/rentamac/.local/share/qwen38-coldstart-tests/qwen38-imgtest-20261011-060057/site-packages.json`

This existing raw JSON was read directly on the Mac mini. Total `site-packages` **16,853,575,348 logical bytes** across **581 entries**. Largest components:

| Component | Measured logical bytes |
|---|---:|
| `flashinfer_cubin` | 4,691,858,760 |
| `nvidia` | 3,350,190,308 |
| `flashinfer_jit_cache` | 2,054,683,357 |
| `sgl_kernel` | 1,194,780,130 |
| `torch` | 1,091,091,641 |
| `triton` | 719,870,322 |
| `nvidia_cutlass_dsl` | 461,178,869 |

Together `flashinfer_cubin` plus `flashinfer_jit_cache` account for **6,746,542,117 logical bytes (~40.0% of site-packages)**. They are NOT a measured 6.75-GB compressed saving opportunity: the entire largest compressed OCI layer is only ~6.981 GB, and arch-specific pruning may leave cache misses/JIT compilation or may break correctness.

The live GPU test demonstrated SGLang + DFlash2 inference and authorization (authenticated 200 / unauthenticated 401), not a controlled v1-vs-v2 A/B test. First authenticated generation readiness was **8m39s after pod creation**, with partially cached image pull; provider host later failed/restarted. Accordingly this is *not* a clean uncached or healthy-host cold-start baseline. See `LIVE_TEST_RESULTS_2026-10-11.md`.

## External upstream research

FlashInfer provides distinct core, cubin and JIT-cache packages. The prebuilt packages intentionally trade image size for **initialization speed, offline operation and avoiding first-use compilation**. Changing their versions or removing architecture assets has real compatibility/performance risk.

FlashInfer's **0.6.18** release reduced the published **cu130 x86_64 JIT-cache wheel** from approximately **1.51 GB** to **1.02 GB**, but increased the published **cubin wheel** from approximately **1.1 GB (0.6.17)** to **1.6 GB (0.6.18)**. The two wheel-size changes roughly cancel; **do not claim 0.49 GB overall image savings by upgrading only the JIT cache**. Version mixing between flashinfer-python, cubin and JIT cache is not a validated upgrade strategy. Nor should 0.6.18 replace the pinned v1 stack without dedicated GPU tests.

Official sources:
- https://flashinfer.ai/releases/
- https://docs.flashinfer.ai/installation.html
- https://flashinfer.ai/whl/cu130/flashinfer-jit-cache/
- https://flashinfer.ai/whl/flashinfer-cubin/

**SM120 nuance:** RTX PRO 6000 is *SM120*, not B200/SM100. FlashInfer architecture compatibility cannot be inferred solely from the characters `sm120` in a filename. Fatbins, JIT providers, generic metadata, fallback kernels and architecture family compatibility make naive deletion hazardous. Prior FlashInfer SM12x/SM10x cubin compatibility issues have been reported. Preserve unknown and multi-architecture assets until traced.

## Experiments (ordered by risk and necessary evidence)

1. **Read-only kernel path inventory:** On an already authorized test v1 container, run `inspect-flashinfer-artifacts.py --json` against the installed site-packages. Save results outside the image. It reports logical bytes and explicit SM120/other/multi/unknown path tokens; it **never deletes**. If most bytes are unnamed/multiarch, file-name pruning is not viable.
2. **Trace real kernel usage:** During authenticated NVFP4 + DFlash2 prefill/decode at 256 and 512+ output tokens and a long-context case, collect file-open/kernel provider selection and startup/JIT cache evidence. Include first-request behavior and a forced cold cache. Define which paths are actually needed; validate that missing cubins do not silently trigger network downloads or expensive JIT.
3. **Targeted v2 candidate overlay:** Use a new opt-in build mode on a dedicated non-production Linux x86_64 builder to remove *only* evidence-backed redundant files **in `framework_final` before the runtime site-packages COPY**. Do not delete after COPY (OCI whiteouts preserve the old layer's registry bytes). Maintain pinned upstream commit/blobs and an explicit deletion allowlist reviewed in a PR; halt on surprising layout or missing expected files.
4. **Workspace footprint:** Separately inventory the **~2.08 GB uncompressed** `COPY /sgl-workspace` layer; never remove the SGLang editable source, Python imports, headers, kernel material or DFlash2 assets without runtime tests.
5. **Only if justified:** investigate runtime CUDA devel requirements and Rust gateway build-stage reuse. The SGLang runtime explicitly needs nvcc for JIT. Keep CUDA devel in v2 until the exact SM120 paths are validated. Optimize `--push` and external BuildKit cache for **build duration** as independent measurements.

## Release and performance gates

Suggested convention:
- GitHub project **v0.2.1** remains as is, image `v0.2.0` stays unchanged.
- A new unvalidated image, if separately authorized to build/push: `ghcr.io/tommyfive/qwen38-sglang:candidate-minimal-v2-<12-char-commit>`.
- After successful GPU tests and measured OCI manifest: promote to *new* image tag `v0.2.2` (and record an immutable digest); use `minimal-v2` as the **iteration label** in docs/metadata. No `v2.0` major bump, no mutable release tag overwrite.
- Production templates and default launchers retain the v1 digest until an explicitly approved rollout. A new candidate should first have independent disposable test template(s).

**Evidence required before promotion:**
- Publish exact OCI `linux/amd64` compressed bytes (sum layer descriptor sizes, not `docker image ls`), layer sizes and digests; compare against 12,907,436,335 bytes.
- Functional matrix: SM120 CUDA context, PyTorch/FlashInfer/SGLang imports, main/draft NVFP4+DFlash2 load, prefill/decode, long-context, native API auth positive/negative, both Public and Tailnet, RAM-first 20-GiB Lean and SSD fallback. Full OpenWebUI and native Tailnet access still need independent validation.
- JIT-cold **and** warmed runs; measure TTFT, tokens/sec from `usage.completion_tokens`, errors, peak VRAM, network dependency, kernel cache misses and first/second request times. Prefer at least five warmed repetitions per workload and matched healthy GPU/DC/cache conditions. A material decode regression, silent output corruption, missing kernel/JIT fallback, or increased startup time is a **no-go**, even if the image is smaller.
- Record provider `Already exists` layers; distinguish RunPod provisioning, image download+extract, model download, and SGLang readiness. Require paired healthy-host trials rather than comparing the unhealthy/partially cached v1 run to an uncached v2.
- Check released image config for secret leakage, provenance, SBOM/licensing and vulnerabilities without embedding user tokens. Avoid adding app secrets to image history.

**Target**: Any *measured and validated* reduction vs 12.907 GB is useful. `<11.5 GB` is aspirational, not a release gate. If only size improves while GPU correctness, startup or throughput deteriorates, **retain v1**.

## Permissions and cost boundaries

This branch is a read-only research aid. No container builds, source deletion, GHCR publication, VPS modifications, RunPod templates or paid GPU Pods are part of its CI. Heavy builds run only on explicitly approved dedicated builders — **never Salty/Rusty/Cloudzy Passwall/VPN production hosts**. Any new dedicated build host, paid test or production rollout requires a separate explicit authorization.
