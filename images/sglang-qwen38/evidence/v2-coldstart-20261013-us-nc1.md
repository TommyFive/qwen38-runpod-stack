# Qwen38 minimal-v2 B · continuous cold start · 2026-10-13 · US-NC-1

**Image:** `ghcr.io/tommyfive/qwen38-sglang@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7` — same immutable image as the GPU-tested v0.2.2 release.  
**RunPod:** US-NC-1, **Secure Cloud**, **1× RTX PRO 6000**, **AMD EPYC 9355 / 16 vCPU**, **188 GB RAM**, **30 GB container disk** (screenshot).

This is a **single continuous uncached Docker pull → initial container → SGLang generation-health** trace. Unlike the 2026-10-12 US-KS-2 Full report, its bootstrap data are from the first container start, not a later image-cached restart.

[Complete machine-readable timeline and individual layer events](v2-coldstart-20261013-us-nc1.json) · [Previous US-KS-2 run](v2-coldstart.json) · [Validation methodology](../VALIDATION.md)

## Measured startup (UTC)

| Milestone / interval | Time UTC | Duration |
|---|---|---:|
| RunPod create / Docker pull begins | **05:52:54** | start |
| Last of 8 layer downloads completes | 05:53:20 | **26 s** from pull start |
| All 8 layers extracted; image ready | **05:54:19** | **85 s** from pull start |
| First container begins | 05:54:20 | 1 s after image ready |
| `bootstrap_start` | 05:54:21.117 | +1.1 s from container start |
| Tailscale connected | 05:54:23.003 | +1.9 s from bootstrap |
| Main + DFlash2 draft RAM download | 05:54:23.757 → 05:54:34.254 | **10.497 s** |
| SGLang starts | 05:54:34.315 | — |
| `health_generate_ready` | **05:55:51.698** | **77.383 s** after SGLang starts |
| OpenWebUI installation phase (parallel to SGLang) | 05:54:34.355 → 05:56:06.533 | **92.178 s** |
| Bootstrap completed | **05:56:06.536** | — |

<details>
<summary>Cold-start totals and time boundaries</summary>

| Measured total | Seconds |
|---|---:|
| First Docker pull → image ready | **85.000** |
| First Docker pull → first container start | **86.000** |
| First Docker pull → SGLang `health_generate_ready` | **177.698 (2m 57.7s)** |
| First Docker pull → OpenWebUI `install_end` | **192.533 (3m 12.5s)** |
| First container start → SGLang generation-health | **91.698** |
| First container start → OpenWebUI `install_end` | **106.533** |
| Bootstrap start → SGLang generation-health | **90.581** |
| First nonempty layer extraction → image ready | **70** |
| Last layer download → image ready | **59** |

Provider timestamps are whole-second precision; internal bootstrap timestamps include milliseconds. `health_generate_ready` is an internal generation-health check, **not** external first-token latency. `openwebui_install_end` is an install phase marker, **not** independent proof that an authenticated user can access OpenWebUI.

</details>

## Docker OCI-layer event trace

All timestamps UTC on 2026-10-13. Eight `Download complete` and eight `Pull complete` markers were found; **zero `Already exists`** cache hits were reported.

| Layer prefix | Download complete | First extracting | Pull complete |
|---|---|---|---|
| `811ba24a0a46` | 05:53:09 | 05:53:09 | 05:53:22 |
| `bf8d0582c21b` | 05:53:11 | 05:53:22 | 05:53:31 |
| `58c5909db254` | 05:53:17 | 05:53:31 | 05:53:42 |
| `bba4c4fa8bc7` | 05:53:12 | 05:53:42 | 05:53:54 |
| `d06795969af1` | 05:53:20 | 05:53:54 | 05:54:05 |
| `1b7d52170636` | 05:53:19 | 05:54:05 | 05:54:14 |
| `90eb9e17f661` | 05:53:03 | 05:54:14 | 05:54:19 |
| `4f4fb700ef54` | 05:52:54 | 05:54:19 | 05:54:19 |

The **26 s download span** and **70 s extraction span** overlap. Most layer downloads finished well before their serialized extraction. These values **must not be added**. The many `create container: still fetching image` lines are polling/progress, **not** multiple Pods being created. The final `Image is up to date` at 05:54:19 is the same newly pulled image being reused for the immediate create/start, not evidence of a warm-start benchmark.

## Same immutable v2-B image, different datacenters

| Observation | 2026-10-12 US-KS-2 | **2026-10-13 US-NC-1** |
|---|---:|---:|
| Cloud/GPU | Secure / RTX PRO 6000 | Secure / RTX PRO 6000 |
| CPU | AMD EPYC 9335 | **AMD EPYC 9355** |
| Allocated vCPUs | 16 | 16 |
| Displayed RAM | 283 GB | **188 GB** |
| Container disk | 30 GB | 30 GB |
| Uncached Docker pull + extraction | **190 s** | **85 s** |
| Last layer download relative to pull start | 158 s | **26 s** |
| First extraction to image ready | 137 s | **70 s** |
| Checkpoint RAM download | 104.104 s **in a later cached restart** | **10.497 s in initial bootstrap** |
| SGLang startup → internal generation-health | 89.362 s **in cached restart** | **77.383 s in initial bootstrap** |
| Whole initial pull → internal generation-health | **Not observable continuously in earlier Full log** | **177.698 s** |

The identical OCI digest rules out different v2-B image content as the explanation for the observed **105-second faster pull** (55.3% reduction). It **does not establish** that US-NC-1, the CPU, Secure Cloud, or networking caused the improvement: these are unmatched individual observations with uncontrolled host/cache/registry/disk conditions. Model checkpoints and draft revisions were not independently compared by hash in these supplied traces.

The earlier Full template enabled blocking benchmark runs before installing OpenWebUI. In this new `DEBUG=0` trace, no benchmark-gate events are present, and OpenWebUI installation starts immediately after SGLang is launched. Thus, even the OpenWebUI phases are **not like-for-like throughput experiments**.

## Limitations and source integrity

- The start log reports `download probe: 0.0 MB/s`; it does **not** prove the network was stalled, since the model and draft subsequently downloaded and RAM storage verified in 10.497 seconds. Do not infer actual throughput or a cache hit from this probe.
- Log evidence shows `TAILSCALE: connected`, SGLang `health_generate_ready`, `openwebui_install_end`, and `bootstrap done`; it **does not** include `QWEN38_WEBUI status=ready`, HTTP 200 on `/health`, successful admin login, UI chat or standalone coding-quality checks.
- Uploaded raw provider log: `logs (14)(1).txt` — SHA-256 `37dc45138d863662117b04910ae4b184d3bfd8e4fe4547182a9876a102567900` (1,748 lines).
- Uploaded raw container log: `logs (13)(1).txt` — SHA-256 `71dba6d382ec0443e4d99860db4fcf22df64132ef9cc82fb316a2e4497564965` (34 lines).
- Uploaded RunPod Details screenshot: `image(20261013-055404).png` — SHA-256 `f4ace9b805dc6a58f2a411bd477e050eb7d168765046daa8f4214d6eb9f74ee5` (1344×1054 px).

Original attachments remain in the conversation. Only **derived timeline, source checksums and non-secret datacenter parameters** are published here; Pod ID, hostname, Tailnet DNS and environment secrets are not published. No Pod, template, image or running service was modified to produce this report.
