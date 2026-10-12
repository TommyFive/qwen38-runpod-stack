# 2026-10-12 GPU cold-start review — minimal-v2 B versus minimal-v1

**Status: measured exploratory comparison; NO demonstrated Docker-start speedup.** No additional GPU Pod was started. Analysis uses archived RunPod system/container logs from the Mac mini and independent v1 records. Timebase: UTC. This report documents the existing run only; it is not an acceptance of Full/OpenWebUI (which failed separately because `uv` was missing).

## Identical core GPU and image references

- v2 B: RTX PRO 6000 Blackwell Server Edition (Secure Cloud); RunPod Pod `8ifu7b1s3z9bib`, manifest `ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7`, Full/Tailnet + 30 GiB container disk; image descriptor compressed layers **10,703,739,835 bytes** (8 layers).
- v1 control: same GPU SKU and Secure Cloud; manifest `ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd`, image descriptor compressed layers **12,907,436,335 bytes** (31 layers). Earlier runs used 150 GiB (run 1) and 20 GiB (run 2) container disks.

Image size reduction: **2,203,696,500 bytes = 17.07%**, *not* a measured throughput or cold-start improvement.

## Event timings from archived logs

| Stage | v1 initial 2026-10-11 | v1 run02 2026-10-11 | v2 B 2026-10-12 |
|---|---:|---:|---:|
| First Docker image activity -> first `Status: Downloaded newer image` | **180 s** | **303 s** | **200 s** |
| Pod API create request -> bootstrap start | 185.5 s | 308.4 s | 228.2 s |
| Request -> first Docker image activity | 1.4 s | 1.4 s | 24.9 s |
| Main HF model RAM download | 253.0 s | 22.2 s | 67.1 s |
| SGLang process start -> `health_generate_ready` | 79.3 s | 67.2 s | 103.7 s |
| Pod creation request -> `health_generate_ready` | 518.7 s | 398.9 s | 403.1 s |

**Run-specific timestamps, v2-B:**

- Pod create: `2026-10-12T07:51:41.050Z` (provider create response time captured on Mac mini).
- First observed Docker image activity: `07:52:06Z`.
- First observed extract: `07:52:42Z`.
- Last observed `Download complete` event: `07:53:01Z`; **this is not proof that all layer bytes had finished downloading**, because fewer such terminal events are present than layers.
- Last observed layer `Pull complete` and `Status: Downloaded newer image`: `07:55:26Z`.
- `start container`: `07:55:28Z`; first bootstrap marker `07:55:29.271Z`.
- Model RAM download: `07:55:33.246Z` through `07:56:40.377Z` (**67.1 s**).
- SGLang start `07:56:40.477Z`; authenticated `health_generate_ready` `07:58:24.139Z` (**103.7 s** after start).
- Completed blocking server benchmark: `07:59:19.992Z`; this was intentionally delayed until after GPU/model readiness and is not included in the preceding `health_generate_ready` cold-start metric. Full WebUI never became ready (missing `uv`).

The image preparation step includes network transfer, decompression, filesystem extraction and provider scheduling, with steps overlapping. It is **not correct to equate the 200 s interval with pure download time**, nor to calculate bandwidth as compressed bytes / 200 s. The first extraction to last completed layer is **164 s** and overlaps the remaining download work.

## Layer cache and comparison caveats

The v2 B system log contains **no** `Already exists` entries in the captured sequence; 8 distinct layer IDs have `Pull complete` / `Extracting` events. In contrast, the v1 logs show **15 distinct cached (`Already exists`) layer IDs** and 15 extracted/downloaded layer IDs in each recorded run, meaning the v1 runs were *partially cached*. The two v1 runs also differ materially in model download time (253 s versus 22 s), which illustrates how strongly different cloud host/cache/network conditions affect end-to-end timing.

Therefore the 200 s v2 B Docker phase is **20 s slower** than v1 first run's 180 s and **103 s faster** than v1 run02's 303 s, but **none of these deltas proves a causal effect** of v2 layer pruning or CUDA symlinks. Likewise, model download and inference initialization differences cannot be attributed to the image size alone. A no-web-UI benchmark gate additionally makes any comparison of *WebUI availability* invalid for this run.

## Practical next steps (do not start another paid pod without approval)

1. Preserve this run as a measured GPU success for NVFP4 + DFlash2, with Full/OpenWebUI separately failed (missing `uv`).
2. Before claiming cold-start acceleration, run matched *new-host, cold-cache* v1 and B on the same GPU SKU, cloud/region, storage and startup configuration; document layer cache hits/misses.
3. Add persistent provider image-stage events: first pull, per-layer terminal download/extract status, image available, container created/started. The absence of all terminal `Download complete` events means separate network/extraction critical paths are approximate at best.
4. Check host disk/unpack performance and layer order: the v2 B `first extract` -> `last pull complete` span alone is 164 s despite 17% lower compressed descriptor bytes.
5. Do not infer `TTFI` from `health_generate_ready` alone; TTFI requires a timed, successful authenticated user-facing inference. The in-pod benchmark is separately validated.

## Evidence

Local private, redacted source logs on Mac mini:
- `~/.local/share/qwen38-gpu-live/2026-10-12-v2b/runpod-redacted.log` (RunPod system and container events)
- `~/.local/share/qwen38-gpu-live/2026-10-12-v2b/bootstrap.log` (native UTC cold-start markers)
- `~/.local/share/qwen38-gpu-live/2026-10-12-v2b/analyze-coldstart.py` (read-only extractor)
- `~/.local/share/qwen38-gpu-live/2026-10-12-v2b/coldstart-comparison-local.json` (machine-readable timeline)
- `~/.local/share/qwen38-coldstart-tests/qwen38-imgtest-20261011-060057/{creation.json,summary.json,pod-events.jsonl}`
- `~/.local/share/qwen38-coldstart-tests/qwen38-imgtest-20261011-run02/{creation.json,pod-events.jsonl}`

[GPU server benchmark evidence](./20261012-v2b-sglang-server-benchmark.json), [final GPU acceptance evidence](./20261012-v2b-final-acceptance.json), [tracking issue #46](https://github.com/TommyFive/qwen38-runpod-stack/issues/46). `main` remains unchanged.
