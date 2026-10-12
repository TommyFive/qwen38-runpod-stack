# minimal-v2 B RC1 — RunPod US-KS-2 host evidence and measured cold-start phases

**Test:** 2026-10-12 · Pod `7rwwhciymmqr77` (`qwen38-v2b-rc1-261012-c36f28`) · **Secure Cloud** · **US-KS-2** · image `ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7`.

**New information:** The user-supplied RunPod Details screenshot confirms the previously missing datacenter **US-KS-2** and Secure Cloud placement. The two attached RunPod logs provide the complete **first, uncached Docker image pull** and a **separate, successful later Full-mode restart**. These are two different periods of the *same* Pod and must not be combined into a fictitious end-to-end cold boot.

[Structured evidence and every layer timestamp](./20261012-v2b-rc1-US-KS-2-coldstart-evidence.json) · [Full and Lean GPU acceptance report](./20261012-v2b-rc1-live-acceptance.md) · [Issue #46](https://github.com/TommyFive/qwen38-runpod-stack/issues/46).

## 1. Screenshot-confirmed datacenter and machine allocation

| Field | Value / evidence |
|---|---|
| RunPod Pod | `7rwwhciymmqr77` |
| Data center / location | **US-KS-2** (visible in uploaded screenshot) |
| Cloud tier | **Secure Cloud** (visible in uploaded screenshot) |
| GPU | **1× NVIDIA RTX PRO 6000** (runtime log identifies Blackwell Server Edition, CUDA compute capability 12.0, 97,887 MiB VRAM) |
| CPU | **AMD EPYC 9335 32-Core Processor**; **16 allocated vCPUs** (screenshot) |
| Pod RAM | **283 GB** (screenshot) |
| Container disk | **30 GB** (screenshot) |
| Image | minimal-v2 B digest above, unchanged during this test |
| Screenshot age | RunPod UI showed Pod uptime **1m 36s** at time of capture; screenshot is historical, **not current Pod status** |

The screenshot establishes the **datacenter ID**, not the exact physical machine/host ID. GPU host identity, network route and image cache topology are not available from this screenshot.

## 2. Uncached Docker first pull, from provider system log (uploaded `logs (18).txt`)

| Event | UTC | CST / China (UTC+8) |
|---|---|---|
| Create-container request logged | 11:28:18 | 19:28:18 |
| Docker `Pulling from`, 8 layer pulls | **11:28:19** | **19:28:19** |
| First substantial layer starts extraction | 11:29:12 | 19:29:12 |
| Last `Download complete` (8th layer) | **11:30:57** | **19:30:57** |
| Last `Pull complete` | **11:31:29** | **19:31:29** |
| `Status: Downloaded newer image` | **11:31:29** | **19:31:29** |
| First `start container` | 11:31:32 | 19:31:32 |

| Measured interval | Duration |
|---|---:|
| **First Docker pull → image ready (network + overlapping decompression/extraction)** | **190 s = 3m 10s** |
| First Docker pull → last layer download finished | 158 s = 2m 38s |
| First nonempty layer extraction → final layer extraction completed | 137 s = 2m 17s |
| Last download complete → final image ready | 32 s |
| Container create event → first start-container event | 194 s = 3m 14s |
| Image ready → first container start | 3 s |

No `Already exists` layer hits appeared in the complete first-pull sequence. Eight layers were pulled and eight `Download complete` / `Pull complete` events are present. All timestamps in this provider log are whole seconds and have approximately ±1-second precision.

### Individual layer timeline

All times UTC on 2026-10-12. Values are those printed by RunPod/Docker; size labels are rounded.

| Layer (first 12 chars) | Displayed bytes | Download complete | Extract begins | Pull complete |
|---|---:|---:|---:|---:|
| `811ba24a0a46` | 1.096 GB | 11:29:12 | 11:29:12 | 11:29:30 |
| `bf8d0582c21b` | 1.424 GB | 11:29:55 | 11:29:55 | 11:30:05 |
| `58c5909db254` | 1.990 GB | 11:30:38 | 11:30:38 | 11:30:49 |
| `bba4c4fa8bc7` | 1.423 GB | **11:28:45** | **11:30:49** | 11:31:02 |
| `d06795969af1` | 1.772 GB | 11:30:31 | 11:31:02 | 11:31:15 |
| `1b7d52170636` | 2.243 GB | 11:30:57 | 11:31:15 | 11:31:24 |
| `90eb9e17f661` | 756.4 MB | **11:28:31** | **11:31:24** | 11:31:29 |
| `4f4fb700ef54` | 32 B | 11:28:19 | 11:31:29 | 11:31:29 |

**Interpretation:** Downloads run concurrently, while observed per-layer extraction is serialized. `bba4c4fa8bc7` finished downloading at 11:28:45 but was not extracted until 11:30:49 (**124 s waiting**); `90eb9e17f661` waited **173 s** between download and extraction. Therefore, slow *individual layer completion* does not necessarily mean slow network transfer. The 190-second combined span cannot safely be split into 158 seconds of network plus 137 seconds of extraction, because these activities overlap.

The provider log also shows repeated `create container` polling/progress lines during image retrieval. These are not evidence that 12 different Pods were created. Subsequent `Image is up to date` lines and start events are cached restarts on the existing Pod.

## 3. Distinct later Full restart: runtime model and inference timing (uploaded `logs (17).txt`)

At **11:42:34 UTC**, the system log shows `Status: Image is up to date`; there was **no new 10.7 GB image download**. The container began booting around 11:42:35. The attached container log reports:

| Phase / event | Timestamp UTC | Elapsed |
|---|---|---:|
| Cached container restart / image resolved | 11:42:34 | 0 s |
| Bootstrap start | 11:42:35.281 | +1.3 s |
| RAM checkpoint + DFlash2 download starts | 11:42:38.256 | — |
| RAM checkpoint + draft download verified | 11:44:22.360 | **104.104 s** |
| SGLang starts | 11:44:22.447 | — |
| Successful GPU generate-health check | 11:45:51.809 | **89.362 s** after SGLang starts |
| Blocking benchmark 3×5 completed | 11:46:46.706 | **54.897 s** after health-ready |
| On-demand OpenWebUI install starts | 11:46:46.729 | — |
| OpenWebUI installation/readiness phase completes | 11:47:37.704 | **50.975 s** |
| **Cached container restart → authenticated GPU-ready** | 11:42:34 → 11:45:51.809 | **197.8 s = 3m 18s** |
| **Cached container restart → Full/WebUI-ready** | 11:42:34 → 11:47:37.704 | **303.7 s = 5m 04s** |

Note that the Full readiness duration includes **a compulsory 3×5 benchmark** that is enabled in this diagnostic template and would not apply to the prepared Lean production candidate with `BENCHMARK=0`. The WebUI setup installed **260 dependencies** in an isolated venv at runtime. `uv` printed a harmless fallback-to-copy warning because cache and environment cannot hardlink across their separate filesystems. No `QWEN38_WEBUI status=failed` occurs in this final successful container log.

The main model plus draft amounted to **22.76 GiB**; the log recorded **131.32 GiB free tmpfs** before model download, **30.619 GiB peak tmpfs usage**, and **87,465 MiB GPU memory use** at the end of its available monitor window. GPU log is CUDA 13.0.3, compute capability 12.0, `spec=dflash2`, `max_len=262144`.

## 4. Comparison quality and limits

Earlier work on v2-B measured a first-pull duration of approximately **224 s** (older full provider event sequence). This **US-KS-2 run measured 190 s**, or **34 s faster**. This is an *observed difference*, **not evidence** that Secure Cloud, US-KS-2, a smaller Docker image or the CPU model caused it. Neither the physical host/cache conditions nor matched infrastructure are controlled in the available sample.

**Crucial:** The first-ever pull ended around 11:31:32, whereas the successful Full log starts after a cached restart at 11:42:35. The 190-second pull and the 197.8-second warm bootstrap are **not a contiguous measured end-to-end Cold Boot**. A complete first-Pod end-to-end boot must use events from the *first* bootstrap attempt (not included in `logs (17).txt`).

For any future comparative trials, record the screenshot/API host metadata (datacenter ID, Secure/Community, CPU type, allocated vCPU/RAM/disk, image digest), whether a cold/partial-cache/full-cache pull occurred, and unambiguous event boundaries.

## 5. Evidence provenance and privacy

**User-provided original attachments in this conversation** (do not publish them raw without a separate secret review):

| Evidence | SHA-256 |
|---|---|
| `logs (18).txt` – provider image and restart logs, 4,995 lines | `33451326b5b7a137d867f97f9fd61c958db4aaf66606a7bf3561f63fda1c0b61` |
| `logs (17).txt` – later successful Full container output, 482 lines | `2d24226e6b182dc513653cddb77d2d291e0380e4f82dca4a1b36dc9ac8e22a13` |
| `image(20261012-113000).png` – RunPod Details screenshot (688×563) | `8c0001a36741b930e93b22555240739e185666c74db97da86f487a8c522099ed` |

The screenshot original is retained as an attachment in this chat; **it has not been uploaded as a binary GitHub repository asset**. Its observed properties and SHA-256 are preserved here and in the structured machine-readable evidence. The source log files are not copied to a public repository; the derived, non-secret event timeline is committed.

**Status:** Documentation only. No new Pod, image build, template change, benchmark rerun or production rollout was made for this report.
