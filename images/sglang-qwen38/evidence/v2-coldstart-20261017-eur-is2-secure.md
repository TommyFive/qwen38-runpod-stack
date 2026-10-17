# Qwen38 minimal-v2 B / v0.2.2 — EUR-IS-2 Secure Cloud, continuous Full cold start (2026-10-17)

**Result: RAM-only main + DFlash2 draft loading and internal SGLang generation-health succeeded.** The complete initial 8-layer Docker pull and first bootstrap follow each other in the supplied logs. OpenWebUI's **installation completed**, but its positive HTTP readiness/login are **not evidenced**.

**RunPod location:** **EUR-IS-2**, **Secure Cloud**, according to the supplied RunPod screenshot. This screenshot does **not** show the GPU SKU, CPU, memory size or disk allocation, so those are deliberately not invented.  
**Immutable tested image:** `ghcr.io/tommyfive/qwen38-sglang@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7`.

[Complete machine-readable timeline, all 8 layers and source SHA-256 hashes](v2-coldstart-20261017-eur-is2-secure.json) · [Earlier US-NC-1 Secure run](v2-coldstart-20261013-us-nc1.md) · [Community Cloud RAM-failure run](v2-coldstart-20261017-community-us-ram-failure.md) · [Validation overview](../VALIDATION.md)

## Continuous cold-start timeline (UTC)

| Event | 2026-10-17 UTC | Duration / elapsed |
|---|---|---:|
| First provider `create container` (first image activity) | **16:11:46** | Start |
| First GHCR pull / all 8 layers begin | 16:11:47 | +1 s |
| First substantial layer extraction | 16:12:28 | +42 s |
| Last of 8 layer downloads completed | 16:13:04 | +78 s |
| All 8 layers extracted, exact digest pulled | **16:15:38** | **232 s (3m 52s)** |
| Container `start container: begin` | 16:15:40 | +2 s after image ready |
| `bootstrap_start` | 16:15:40.901 | +0.9 s after container start |
| Tailscale connected | 16:15:43.278 | Private network connected; no hostname disclosed |
| Main + DFlash2 draft RAM download | 16:15:44.842–16:16:46.168 | **61.326 s** |
| `sglang_start` | 16:16:46.259 | — |
| `health_generate_ready` | **16:18:31.910** | **105.651 s** after SGLang start |
| OpenWebUI install in isolated environment | 16:16:46.322–16:19:01.141 | **134.819 s**, concurrent with SGLang |
| `bootstrap done` | **16:19:01.146** | **435.146 s (7m 15.1s)** from first image activity |

**First image activity → internal SGLang generation health: 405.910 s (6m 45.9s)**. **First container start → internal generation health: 171.910 s**. **Bootstrap start → internal generation health: 171.009 s**; bootstrap start → completion: **200.245 s**.

The **232-second image time** measures from the first `create container` at 16:11:46 to `Downloaded newer image` at 16:15:38. If instead starting at the first `Pulling from` event (16:11:47), the duration is **231 seconds**. The 16:15:39 `Image is up to date` line is an immediate second provider check after the new image was successfully downloaded; this does **not** turn the initial pull into a warm-cache measurement.

## Docker layer evidence

Provider log contains **8 distinct `Pulling fs layer`**, **8 `Download complete`** and **8 `Pull complete`** markers, **zero `Already exists`** cache hits. All timestamps below are UTC.

| OCI layer prefix | Download complete | First extracting | Pull complete |
|---|---|---|---|
| `811ba24a0a46` | 16:12:28 | 16:12:28 | 16:13:06 |
| `bf8d0582c21b` | 16:12:36 | 16:13:06 | 16:13:34 |
| `58c5909db254` | 16:12:59 | 16:13:35 | 16:14:03 |
| `bba4c4fa8bc7` | 16:12:38 | 16:14:03 | 16:14:36 |
| `d06795969af1` | 16:12:50 | 16:14:36 | 16:15:05 |
| `1b7d52170636` | 16:13:04 | 16:15:05 | 16:15:26 |
| `90eb9e17f661` | 16:12:20 | 16:15:26 | 16:15:38 |
| `4f4fb700ef54` | 16:11:47 | 16:15:38 | 16:15:38 |

First image activity → last download: **78 s**; first extraction → image ready: **190 s**; last download → image ready: **154 s**. Downloads and extractions **overlap**, so these intervals must **not** be added. Repeated `create container: still fetching image` is provider polling, not evidence of multiple Pods.

## RAM-only and Full startup outcome

- `Storage mode: ram, root=/dev/shm/qwen38-hf` and `RAM mode verified: main and draft paths remain on tmpfs` are present. This demonstrates successful main + DFlash2 draft loading into the tmpfs-backed cache on this Secure host, unlike the separate Community Cloud RAM-preflight failure.
- `health_generate_ready` confirms an **internal SGLang generation-health check** at 16:18:31.910 UTC. It is **not** an external authenticated request/TTFT benchmark.
- OpenWebUI installation starts right after SGLang launch and completes at 16:19:01.141. Both phases proceed **in parallel**; adding their durations to SGLang time would misrepresent total boot time.
- The logs show **no positive OpenWebUI HTTP /health response, real admin login, external chat request, standalone coding quality, peak tmpfs occupancy or effective `MODEL_RAM_PEAK_FACTOR`**. Do not infer these from the absence of error messages.
- The startup network probe prints `0.0 MB/s`, but the next main/draft download completes in 61.326 seconds. Treat that diagnostic as **unreliable throughput measurement**, not proof of a stalled link.

## Same image, other recorded first pulls

| Run | Cloud / datacenter | First image activity → image ready | Outcome |
|---|---|---:|---|
| 2026-10-12 | Secure / US-KS-2 | **190 s** | Later cached Full restart validated; not contiguous first boot |
| 2026-10-13 | Secure / US-NC-1 | **85 s** | Continuous first pull → internal generation-health 177.698 s |
| 2026-10-17 | Community / US (unspecified) | **328 s** | RAM capacity preflight rejected; no model start |
| **2026-10-17** | **Secure / EUR-IS-2** | **232 s** | **RAM model/draft and internal SGLang health succeeded; Full installer finished** |

EUR-IS-2's first image pull is **42 s slower than US-KS-2**, **147 s slower than US-NC-1**, and **96 s faster than the Community US observation**. Every run used the same immutable v2-B digest. This rules out different image bytes as the explanation, **not** changes in underlying network routes, caches, disks, host types, provider tiers or data centers. These are unmatched observations and do not establish causal regional/cloud performance differences.

## Source provenance and privacy

| User attachment | SHA-256 | Evidence |
|---|---|---|
| `logs (5)(1).txt` | `3508b67f1cd1644855c79376d85e404adcb87f790b3bb285880e1f9c8b0d57ec` | 4,207 provider log lines; 196,060 bytes |
| `logs (4).txt` | `aed08e8d76d908e1483cae4acdbd27f968779ad0b4f9b88293d2bfb1aa9cfded` | 35 container log lines; 3,728 bytes |
| `image(20261017-162036).png` | `999afdad424673bee24d87e7f5b9238f796116fe11549eab7c4a835fdf` | EUR-IS-2 Secure Cloud screenshot, 1322×326 px |

Raw user uploads remain in the conversation, **not** committed to public GitHub. No RunPod Pod ID, secret, private Tailnet hostname, IP, private deployment env values or billing data are published. Provider event timestamps have **whole-second precision**; pod `QWEN38_COLDSTART` timestamps have millisecond precision. This documentation makes **no change to GPU Pods, images, templates or running services**.
