# Alibaba ECS SGLang image build — measured results (2026-10-10/11)

**Status:** Docker image built and pushed successfully. Candidate only; GPU runtime compatibility and cold-start benefits **not yet validated**. This report uses saved BuildKit logs, systemd journal, Buildx build records and Docker image/push inspection. Alibaba ECS was released by the user. No new cloud resources were started.

## Artifacts and provenance

| Field | Value |
|---|---|
| Repository | `TommyFive/qwen38-runpod-stack`, draft PR #21 |
| Repository commit tested | `4ad22cd0b56b083b0e487af69f46d94fb9498e73` |
| SGLang upstream commit | `5f55db35e926d50676f75b812640ea2410b0fe0e` |
| Image | `ghcr.io/tommyfive/qwen38-sglang:candidate-cloudzy-4ad22cd0b56b` |
| Pushed manifest digest | `sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd` |
| Build/push exit codes | `0` / `0` |
| Host | Alibaba Cloud ECS Frankfurt, `ecs.r9ae.2xlarge`, x86_64 |
| Resources | 8 vCPU, 64 GiB provisioned RAM, 300 GiB ESSD PL0 root disk |
| BuildKit | Docker-container driver, at most two parallel build steps, memory limit 48g |
| Docker local image | 41,686,416,816 bytes uncompressed, 31 filesystem layers |
| GHCR access | Package private, anonymous registry request received 401; authenticated pull pending |

The image manifest digest is from the successful `docker push`; it is **not** a cold-start measurement, performance benchmark or proof of GPU compatibility.

## Build timeline (UTC)

| Event | UTC |
|---|---|
| First Buildx attempt started | 2026-10-10 14:58:58 |
| First attempt completed as **Error** | 15:16:09 |
| Journal SIGTERM for first image service | 15:15:55 |
| Second Buildx attempt started | 15:16:18 |
| Second attempt completed successfully | 15:58:49 |
| Total elapsed, first attempt to success | **59m 51s** |
| Successful, partially cached attempt duration | **42m 31s** |
| BuildKit steps, successful attempt | 90 of 90 in native Buildx history; 29 cached |

**Interpretation:** Neither 59m 51s nor 42m 31s is a clean, uncached successful-build baseline. The first run populated the BuildKit cache; the successful run reused 29 stages. The first was stopped with SIGTERM, but **no root cause is proved** (do not call it an OOM event without evidence). The per-step durations below partly overlap and must **not** be added to reconstruct wall-clock time.

## Most expensive measured BuildKit steps

| Step | Activity | Duration |
|---|---|---:|
| #35 | Rust SGLang gateway build, maturin/Cargo | **1,008.2 s (16m 48s)** |
| #90 | OCI export / local Docker import (`--load`) | **680.3 s (11m 20s)** |
| #73 | Framework finalization; SGL kernel cubin fetch retries | **358.1 s (5m 58s)** |
| #36 | Torch dependencies | 321.3 s (5m 21s) |
| #42 | HPC ops compilation | 311.1 s (5m 11s) |
| #40 | FlashInfer JIT/cubin cache setup | 268.5 s (4m 29s) |
| #59 | Framework / MSCCLPP source deps | 216.0 s (3m 36s) |
| #78 | Copy Python site-packages into runtime image | 97.2 s (1m 37s) |
| #45 | Copy FlashInfer cache | 82.7 s (1m 23s) |

Within #90, BuildKit reports **376.4 s exporting layers** and **303.8 s sending tarball**. A direct `--push` build could avoid the local `--load` round-trip; it would still need layer compression and registry upload, so do not promise a fixed reduction.

Step #73 contains repeated `sgl-kernel cubin download failed, retrying in 30s`; this is a concrete opportunity to inspect the download path/retry logic (do not simply remove kernel assets).

## Resource measurements

| Metric | Observation |
|---|---:|
| Peak host RAM used (sampled) | 45.81 GiB |
| Lowest available free root SSD (sampled) | 146.92 GiB |
| Initial available free root SSD | ~280 GiB |
| 30-second telemetry records for second run | 86 |
| Uncompressed local Docker image | ~38.83 GiB / 41.69 decimal GB |

Peak usage is sampled and may miss momentary extremes. The Alibaba Cloud screenshot showed peak CPU use near 100% for several minutes but mostly significantly lower, so doubling vCPU is not a proven large benefit. The SSD usage plot is **space consumed**, not IOPS/throughput/saturation; PL1 advantage is unproven. RAM >32GiB was needed at observed parallelism.

## Important size measurement still outstanding

- Baseline `lmsysorg/sglang:dev-qwen38-27b-dflash2`: **14.676 decimal GB compressed** (linux/amd64 manifest, 68 layers) from the initial source-image analysis.
- Candidate: **41.69 decimal GB uncompressed** in Docker, 31 filesystem layers. **Compressed registry layer sum unknown** until authenticated registry manifest inspection.
- These are different size metrics and **must not be directly compared**. A smaller layer count alone does not establish image-size savings.
- Use `images/sglang-qwen38/manifest-size.py` to sum the compressed layer sizes from an OCI/Docker single-platform manifest JSON.

## Preserved forensic evidence

On Mac mini (local private 0600 archive):

`/Users/rentamac/.local/share/qwen38-cloudzy-builder-archives/`

Find the archive with SHA256
`f8e965d3701ad979f03b40c2cbec2eb24d10499c29386aa57330b5c8819f234d`.

It contains `buildkit.log`, `resource-samples.jsonl`, `image-history.txt`, `image-inspect.txt`, `all-build-records.dockerbuild` (two native BuildKit history records), `buildx-record-list.jsonl`, `service-journal.txt` (includes initial SIGTERM), `ghcr-push.log` and `ghcr-push-exit-code.txt`. The extracted BuildKit log was confirmed byte-identical with ECS original, SHA256 `e06c230de4db79b9d088890f92aba35514bc1f5e1eac8a01bd4265884b790b78`.

**Limitations:** The BuildKit cache was **not** exported as a reusable OCI/registry cache. Deleting the VPS destroyed the live cache, not the archived history. Only one offline archive copy is confirmed, on Mac mini; a second independent backup is recommended.

## Prioritized next work

1. **GPU compatibility first:** Private RunPod GHCR registry auth via `--registry-auth-id`, GPU Blackwell (RTX PRO 6000), unchanged model/DFlash2 startup, Bearer auth, verify no functional regressions. Separate from production templates and only after explicit paid-Pod authorization.
2. **Manifest measurement:** Authenticate GHCR read access on an existing workstation. Resolve candidate compressed manifest layer sum; compare with the baseline and inspect largest layers. Do not pull 41 GB merely to read the manifest.
3. **Caching:** Preserve a remote BuildKit registry cache for subsequent ECS rebuilds using carefully scoped `--cache-to`/`--cache-from`, recognizing that the old live cache cannot be recovered from the build-record archive.
4. **Performance:** Separate Rust gateway artifact build/caching from runtime changes and investigate cubin retry failures. Compare direct registry `--push` versus local `--load` only on a deliberately authorized future CPU build.
5. **IO validation:** Measure SSD IOPS/throughput and CPU iowait *during* a future build before spending on PL1; do not infer saturation from used-capacity charts.

**Do not merge PR #21 or replace production RunPod templates until the GPU validation and compressed-size result are known.**
