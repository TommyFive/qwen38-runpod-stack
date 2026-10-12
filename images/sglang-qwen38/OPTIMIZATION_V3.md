# Optimization knowledge and v3 roadmap

## Status and measurement units

v1 and v2 B are published; v2 B passed restored CPU checks and subsequent
SM120 NVFP4 + DFlash2 Lean/Full GPU smokes. v3 is **not built or benchmarked**.
Logical file bytes, aggregate uncompressed Docker layers, TAR bytes and compressed
OCI layer-descriptor sums are distinct. Candidate pools below overlap and are
**not additive compressed savings**. Upstream is rounded, not an exact baseline.

| Image | Compressed OCI layer bytes | Layers | Reduction |
|---|---:|---:|---|
| Official SGLang upstream | ~14,676,000,000 | 68 | rounded reference |
| minimal-v1 | 12,907,436,335 | 31 | ~12.1% vs upstream |
| minimal-v2 A (Rust only) | 11,842,557,123 | 8 | intermediate CPU control |
| minimal-v2 B | 10,703,739,835 | 8 | 2,203,696,500 bytes / 17.07% vs v1; ~27.1% vs upstream |

The v1 upstream index was
`sha256:616a3e97f45191af975896cfa644279096cb31bd408a071c2e99ca7209c3cafe`.
Pinned software: SGLang `5f55db35e926d50676f75b812640ea2410b0fe0e`,
CUDA 13.0.3, Torch 2.13.0+cu130, FlashInfer 0.6.17,
sglang-kernel 0.4.6.post1, Transformers 5.12.1.

## Implemented: upstream → v1 → v2 B

**v1:** replace the upstream `all` extra with the empty `qwen38-minimal` extra.
Exactly 25 direct optional declarations are omitted: diffusion 20, HTTP/2 1,
tracing/OpenTelemetry 4. Base dependencies are unchanged. This is **not evidence
that all corresponding packages physically disappeared**, including transitive
requirements. Exact declarations remain in the published inventory.

**v2 A/B:** prune only explicit Rust intermediates; B additionally symlinks
11 SHA256-identical CUDA wheel copies to unchanged system libraries.

| Intentional change | Files | Original logical bytes |
|---|---:|---:|
| Rust `.rlib` | 597 | 998,069,614 |
| Rust `.rmeta` | 595 | 667,264,896 |
| CUDA copies replaced with relative symlinks | 11 | 1,679,571,048 |
| Total targeted changes | 1,203 | 3,344,905,558 |

[Exhaustive inventories](../../docs/releases/v0.2.2-removal-inventory/removal-summary.json)
preserve every removed path, size, symlink destination and CUDA SHA256. The inventory
checksum tests reconcile all 1,192 Rust files and all 11 CUDA pairs with the pruner.
Never remove the whole Rust target: runtime shared objects remain required.

CUDA redundant-copy bytes: libcublasLt 541,607,888; libcufft 286,542,352;
libcusparse 162,565,256; libcusolver 141,152,872; libcurand 132,698,328;
libnvrtc.alt 109,821,488; libnvrtc 109,338,064; libcusolverMg 103,956,840;
libcublas 54,177,976; libnvperf_host 32,405,040; libnvperf_target 5,304,944.
`libtorch_cuda.so` DT_NEEDED includes cufft.so.12, cusparse.so.12,
cublasLt.so.13, nvrtc.so.13 and nccl.so.2. Its RUNPATH uses wheel directories
`$ORIGIN/../../nvidia/{cu13,cudnn,nccl}/lib`; simply deleting those copies breaks
loader paths. The pruner hashes **all pairs before any replacement**.
System NCCL (343,864,936 bytes) and wheel NCCL (252,204,648 bytes) are not identical;
several cuDNN copies also differ. Their versions must not be unified blindly.

`generate-repack.py` copies the pruned merged root into `FROM scratch`, preserving
runtime config, entrypoint, environment, labels, working directory and links.
The original single-layer A/B exports were respectively **11,921,733,430** and
**10,777,962,784** compressed bytes. GHCR's documented 10-GB per-layer limit and
10-minute upload timeout motivated streaming layer splitting. A/B became 8 layers
with the descriptor totals above. Splitting preserves TAR entry order, metadata,
ownership, contents and links, but changes layer digests, diff IDs, history and
manifest. Original OCI TAR checksums are **not** manifest hashes.
Original archive hashes and all 30 historic asset hashes remain in
[evidence/v2-checkpoint.json](evidence/v2-checkpoint.json).
No checkpoint release asset is required for the current supported recovery path.

## CPU filesystem and package evidence

The read-only v1 audit counted 155,634 regular files, 1,444 symlinks,
365 dpkg packages, 283 Python distributions, 201 large ELF dynamic objects and
27.971 GB accessible merged logical content. It excluded virtual `/proc`, `/sys`,
`/dev` and transient `/tmp`, `/run`, `/mnt`; an independent `du` check found the
last three together below 0.1 MB. Docker's uncompressed layer sum was
41,686,416,816 bytes; historical overwritten layers/accounting explain why it is
not the same quantity. Probes used no network, no capabilities and a read-only root.

GPU-side site-packages inventory: 16,853,575,348 logical bytes across 581 entries.

| Component | Logical bytes |
|---|---:|
| flashinfer_cubin | 4,691,858,760 |
| nvidia | 3,350,190,308 |
| flashinfer_jit_cache | 2,054,683,357 |
| sgl_kernel | 1,194,780,130 |
| torch | 1,091,091,641 |
| triton | 719,870,322 |
| nvidia_cutlass_dsl | 461,178,869 |

FlashInfer cubin + JIT cache total 6,746,542,117 logical bytes (~40% of site-packages),
not 6.75 GB of registry savings. The largest v1 compressed layer (~6.981 GB, 54.1%)
is attributed to the unique ~17.1-GB site-packages COPY at pinned Dockerfile line
790; this attribution was based on layer/history size evidence, not a saved
per-layer mapping. Other largest compressed layers: ~2.323, 1.508, 0.828, 0.728 GB.
Other uncompressed history layers: CUDA devel 4.89 GB, runtime libraries 2.12 GB,
workspace COPY 2.08 GB, runtime apt/JIT dependencies 1.55 GB.

## v3 decision matrix

All rows are **open**, unless explicitly qualified. Numbers are measured logical
candidate pools, not promises. P1 = investigate first; P2 = trace before trimming;
P3 = isolated high-risk experiment. No removal is authorized by this roadmap.

| Measure / status / priority | Evidence and defensible potential | Risks | Required validation and recommendation |
|---|---|---|---|
| Nsight Compute — open, P1 | `/opt/nvidia/nsight-compute` ~1,303 MB; dpkg 2025.3.1 ~1,244 MiB. Compressed saving unknown, at most measured removable content before compression. | Medium: profiling/tool dependencies; inherited base layers cannot shrink via later deletion. | CPU package/ELF/import audit; cold/warm SM120 GPU startup, NVFP4+DFlash2. Remove via rebuilt final base or proven repack only. |
| CUDA static archives — open, P3 | CUDA toolkit ~5.313 GB, `.a` ~2,564 MB. Only individually unused archives are candidates; no compressed estimate. | High: NVCC/NVVM/PTXAS/NVRTC and lazy JIT/link paths may require archives/headers. | Trace first-use and cold-cache compilation, long context, all supported GPUs; retain compiler toolchain until runtime file-open evidence proves absence. |
| FlashInfer cubin selection — open, P3 | 4,691,858,760 bytes / 46,172 files (~4.641 GB cubins); explicit other-arch path tokens 2,909,679,460 bytes: 100f 2,040,927,000; 107a 820,751,048; 103a 48,001,412. No explicit SM120 filename. | High: SM120 is not SM100; fatbins, generic providers, forward-JIT and offline startup. Filename tokens do not establish compatibility. | Trace provider/kernel loads for NVFP4+DFlash2, 256/512+ tokens, long context, cold/warm cache and network-disabled startup. Preserve unknown/multiarch assets. |
| FlashInfer JIT cache selection — open, P3 | 2,054,683,357 bytes; only traced-unused subset; compressed saving unknown. | High: first-request compilation, cache misses, network fetching, TTFT. | Same GPU matrix plus forced fresh cache, no silent provider fallback and first-request timing. Keep core/cubin/cache versions matched. |
| Explicit non-SM120 JIT paths — unproven removability, P2 | 198,692,920 bytes tagged non-SM120; 18,583,728 tagged SM120; 1,837,406,709 unknown. Subset of JIT row, **not additive**. | High: path classification is not binary architecture proof. | Inspect fatbins and provider lookup; run cold/warm GPU traces before allowlisting any deletion. |
| CUTLASS DSL CUDA12 branch — open, P2 | ~181 MB cu12 and ~180 MB cu13 native bindings within 461 MB package. Compressed potential unmeasured. | Medium: import dispatch or compatibility fallback may reference cu12. | CPU versioned import/ELF/metadata checks plus SM120 main/draft and JIT probes. Keep cu13 and shared metadata. |
| HPC wheel / SM90a components — open, P2 | ~122 MB; pinned builder describes SM90a-only kernels. Build stage 311.1 s, overlapping other steps. | Medium: eager SGLang imports may require wheel even on SM120. | Trace imports and calls, preserve dependency contract; test absence on GPU. Build-time saving is not wall-time or image-size proof. |
| Development packages — unquantified, P1 | Upstream lines 516–535 install tools listed below; no sufficient unique removable-size proof. | Medium: transitive imports, model loaders, compilation. | Measure per-package bytes/dependency graph; CPU imports, GPU boot/benchmark and Full runtime install; trim only proven unused. |
| Replace CUDA devel base — open, P3 | Runtime-only base savings unquantified; line 699 explicitly retains devel for JIT. | High: loss of NVCC/PTXAS/NVRTC, headers, CUDA graphs, Triton/FlashInfer. | Separate experiment with complete proven JIT toolchain; CPU dynamic links and broad cold/warm GPU matrix. Never equate successful import with successful inference. |
| Further identical libraries — open, P1 | Existing 11 pairs already implemented; additional pool unknown. | Medium: RUNPATH, versions, metadata and lazy loading; NCCL/cuDNN counterexamples. | Bounded SHA256 search with `verify-duplicates.py`; exact hash/link allowlist then loader + CPU/GPU tests. Never consolidate on name/size alone. |
| Layer layout/compression — open, P1 | 8-layer split B vs original scratch export differs by 74,222,949 compressed bytes; layout already matters. No further saving estimate. | Medium: upload limits, extraction order/hardlinks, CPU decompression and registry compatibility. | Verify ordered filesystem parity, config/diff IDs, gzip integrity, all blobs and registry sizes; matched cold-pull experiments. |

Additional measured leads: NVIDIA-only audit of `tokenspeed_triton` AMD codegen
~92 MB; distributed/non-text packages `mscclpp` 249 MB, `mooncake` 136 MB,
`runai_model_streamer` 140 MB, `pyarrow` 168 MB, `nixl_cu13.libs` 122 MB,
`nixl_ep_cu13` 95 MB. All are **open P2**, medium–high import/provider risk,
unmeasured compressed potential. Require feature traces, dependency checks,
no-network imports and GPU cold/warm correctness before removing any.

Upstream explicit tooling includes datamodel_code_generator, pre-commit, pytest,
black, isort, icdiff, uv, wheel, scikit-build-core, py-spy, cubloaty,
google-cloud-storage, pandas, matplotlib, tabulate, termplotlib and
runai-model-streamer[s3,gcs,azure]. Installation instructions alone neither prove
current presence nor removability; GPU-tested image lacks `uv`, and current
bootstrap installs a checksum-pinned copy on demand.

### Rejected or deferred shortcuts

- **Rejected:** deleting after the final COPY to shrink inherited blobs. Overlay
  whiteouts do not reclaim old compressed bytes. Prune in `framework_final`
  before COPY, or use a validated fresh-filetree repack.
- **Rejected:** removing all Rust target files, apparent CUDA duplicates, unknown
  cubins or JIT providers. Runtime `.so`, NCCL/cuDNN differences and SM120 paths matter.
- **Rejected:** claiming 0.49 GB net savings from FlashInfer 0.6.18. Historical
  wheel listings showed JIT cu130 x86_64 ~1.51→1.02 GB but cubin ~1.1→1.6 GB;
  changes roughly cancel and wheel bytes are not OCI savings. No mixed-version upgrade.
- **No useful proven image split:** OpenWebUI is runtime-installed only for Full,
  not baked into this image. Lean naming alone cannot remove it from image layers.
- **Deferred:** base replacement and per-GPU specialization until workload traces
  exist. Keep the generic rollback for other GPU/model combinations.
- **Not proven:** faster GPU startup, coding quality or v1/v2 throughput from
  incomparable hosts/cache states. See [VALIDATION.md](VALIDATION.md).

## Build performance: separate from runtime image size

Original dedicated x86_64 builder: 8 vCPU, 64 GiB RAM, 300 GiB SSD; BuildKit
Docker-container driver, max parallelism 2, memory limit 48g. First attempt was
SIGTERM-terminated (root cause unknown, **not proven OOM**). Successful partially
cached attempt 42m31s, combined attempts 59m51s; 90 steps, 29 cached. Sampled peak
RAM 45.81 GiB, minimum free SSD 146.92 GiB, initial free ~280 GiB; 86 samples at
30 seconds. Capacity graphs do not measure IOPS; extra CPU/faster SSD benefits
remain unproved. The live BuildKit cache was not exported and is unavailable.

| Step | Measured seconds (overlapping, not additive) |
|---|---:|
| Rust gateway maturin/Cargo | 1,008.2 |
| `--load` export/import | 680.3 (376.4 export + 303.8 tar transmission) |
| Framework/cubin retries | 358.1 |
| Torch dependencies | 321.3 |
| HPC ops | 311.1 |
| FlashInfer cache setup | 268.5 |
| Framework/MSCCLPP | 216.0 |
| site-packages COPY | 97.2 |
| FlashInfer COPY | 82.7 |

Investigate cubin retry/download reliability, reusable scoped remote BuildKit
cache, Rust stage reuse and direct `--push` versus `--load` in future authorized
builds. These are build-duration candidates, not measured runtime savings.
`tools/watch-build.py` keeps numeric telemetry and signals only an isolated build
process group. No provider SSH/bootstrap orchestration is needed.

## Provenance and reproducible next iteration

The original private v1 build archive SHA256 is
`f8e965d3701ad979f03b40c2cbec2eb24d10499c29386aa57330b5c8819f234d`;
its byte-identical BuildKit log
`e06c230de4db79b9d088890f92aba35514bc1f5e1eac8a01bd4265884b790b78`.
CPU raw inventory gzip (~2.4 MB):
`9068c1ce0e590102eb5b466dbf7601b7d711e697f3b9c396cc62b0f09da13b69`.
CPU plaintext checkpoint archive:
`8941363c7612e5f25a8d207f5a1f07af4894e5fb1a8059637e1fe40f248a5bf3`.
First v1 GPU pre-stop snapshot:
`bb2f9caaca8391bdb4c9d19668d3589b5f74591866e6763428d15bafb2812028`.
These identify historical private evidence, not guaranteed currently retrievable
public assets. Encrypted asset hashes and original/split OCI hashes remain in the
checkpoint evidence; public recovery no longer uses those asset downloads.

Order for v3: (1) reproduce read-only inventory and immutable baseline; (2) test
one P1 allowlisted change at a time; (3) hash/ELF/config/CPU checks; (4) separately
authorized matched SM120 GPU correctness/security/cold+warm tests; (5) compare
compressed manifests and full runtime gates; (6) publish a **new immutable**
version only after acceptance. Never overwrite v0.2.0/v0.2.2.

References: [pinned Dockerfile](https://github.com/sgl-project/sglang/blob/5f55db35e926d50676f75b812640ea2410b0fe0e/docker/Dockerfile),
[pinned dependencies](https://github.com/sgl-project/sglang/blob/5f55db35e926d50676f75b812640ea2410b0fe0e/python/pyproject.toml),
[FlashInfer releases](https://flashinfer.ai/releases/),
[installation](https://docs.flashinfer.ai/installation.html),
[JIT wheels](https://flashinfer.ai/whl/cu130/flashinfer-jit-cache/),
[cubin wheels](https://flashinfer.ai/whl/flashinfer-cubin/),
[GHCR limits](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).
