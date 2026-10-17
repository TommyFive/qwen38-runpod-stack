# minimal-v2 B / v0.2.2 — Community Cloud US, Docker cold-pull and RAM admission failure (2026-10-17)

**Status: model not started.** This is a measured **uncached image pull followed by five failed bootstrap attempts**, not a successful inference cold boot. The user identified this as **RunPod Community Cloud**; the screenshot displays location **US**, without a specific datacenter identifier. The exact released image was `ghcr.io/tommyfive/qwen38-sglang@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7`.

[Machine-readable complete timeline and all 8 layers](v2-coldstart-20261017-community-us-ram-failure.json) · [Earlier 2026-10-13 Secure Cloud US-NC-1 comparison](v2-coldstart-20261013-us-nc1.md) · [Validation overview](../VALIDATION.md)

## Cold-start timeline (UTC)

| Event | UTC on 2026-10-17 | Duration |
|---|---|---:|
| First uncached GHCR image pull, 8 layers | **15:38:21** | Start |
| First substantial layer extraction | 15:38:52 | — |
| Last layer downloaded | **15:43:08** | **287 s** after pull start |
| All layers extracted; image ready | **15:43:49** | **328 s = 5m 28s** after pull start |
| First container start | 15:43:52 | 3 s after image ready |
| First bootstrap starts | 15:43:52.939 | — |
| First `RAM preflight FAILED` | **15:43:53.780** | **0.841 s** after bootstrap starts |
| First bootstrap exits | 15:43:53.849 | — |
| More bootstrap attempts | 15:44:01.970, 15:44:18.675, 15:44:35.466, 15:44:52.189 | Repeated identical failure |

**Docker**: 8 `Download complete` and 8 `Pull complete` events; zero `Already exists` markers. The first nonempty extraction to image ready spans **297 s**, while download and extraction **overlap**, so they must not be added. The many `create container: still fetching image` messages are **provider polling**, not multiple GPU Pods. The subsequent five start events are **crash/restarts of the same downloaded image**, not additional image cold pulls.

### Exact Docker layer timeline

All timestamps UTC on October 17.

| Layer (first 12 hex digits) | Download complete | First extracting | Pull complete |
|---|---|---|---|
| `811ba24a0a46` | 15:38:52 | 15:38:52 | 15:39:27 |
| `bf8d0582c21b` | 15:38:59 | 15:39:27 | 15:39:51 |
| `58c5909db254` | 15:39:15 | 15:39:51 | 15:40:15 |
| `bba4c4fa8bc7` | 15:42:25 | 15:42:25 | 15:42:54 |
| `d06795969af1` | 15:42:48 | 15:42:54 | 15:43:20 |
| `1b7d52170636` | 15:43:08 | 15:43:20 | 15:43:39 |
| `90eb9e17f661` | 15:42:49 | 15:43:39 | 15:43:49 |
| `4f4fb700ef54` | 15:42:48 | 15:43:49 | 15:43:49 |

## Why RAM-only was rejected

The failure is **in `scripts/model-storage.py:preflight()`**, reached through `scripts/bootstrap-sglang-openwebui.sh` before any main/draft weight download or SGLang startup. The bootstrap is deliberately fail-closed, without automatic fallback to SSD:

```text
MODEL STORAGE ERROR: RAM preflight FAILED:
tmpfs needs 64.90 GiB but has 57.74 GiB free.
Resize /dev/shm or select MODEL_STORAGE=ssd
ERROR: model storage admission failed; no fallback to SSD
```

The verified model and DFlash2 draft inventory is approximately **22.76 GiB**. The current default admission calculation is:

```text
shm_required = (model + draft) × MODEL_RAM_PEAK_FACTOR + MODEL_RAM_HEADROOM_GIB
             = 22.76 GiB × 2.5 + 8 GiB
             = 64.90 GiB

shm_available = 57.74 GiB
shortfall = 7.16 GiB
```

This admission failure is **not a GPU memory OOM and not a failed runtime inference**. It is a capacity policy rejection **before downloading the weights**. The previous Secure Cloud test measured a **30.619 GiB peak tmpfs delta/usage** (see [validation](../VALIDATION.md)), considerably below the default **64.90 GiB** requested reserve. However, that measurement comes from a **different host and test**, so it does not guarantee that this Community Pod can successfully start.

A read-only RunPod provider query of the concurrently active matching v0.2.2 Pod reported **125 GB provisioned RAM** and **30 GB container disk**. The supplied screenshot only establishes **US**, while the user explicitly identifies the cloud tier as **Community**; no exact GPU datacenter or CPU model is available from the evidence. A provider Pod's relation to the uploaded log is supported by user context and matching immutable image/settings, not by a shared immutable host identifier in the logs.

The **other admission guards were not reached**: after tmpfs capacity succeeds, the script also checks host `MemAvailable` and the cgroup's remaining RAM, reserving an **additional 8 GiB** for the process. Therefore, neither the new Pod's cgroup capacity nor a successful HF download has been measured here.

### Controlled remediation to evaluate, not applied

- **Preferred if larger host available:** use a Pod with enough verified free tmpfs and overall cgroup RAM for the default **64.90 GiB tmpfs + 8 GiB process** budget; retain fail-closed behavior.
- **Reasonable exploratory test on smaller Community RAM:** explicitly set `MODEL_RAM_PEAK_FACTOR=2.0`. This would reduce the first tmpfs threshold to **53.52 GiB** (under observed 57.74 GiB), and overall cgroup threshold to **61.52 GiB**; the script would still enforce both cgroup and host `MemAvailable` checks. It relaxes safety margin and **must not be represented as already validated**.
- **If neither is suitable:** use `MODEL_STORAGE=ssd` **only with a sufficiently sized SSD container volume**; do not force SSD fallback on this 30-GB RAM-first template. The existing generator/launcher typically selects **150 GiB** for SSD usage.

**Do not globally lower the default 2.5 multiplier, invent a successful Community RAM startup, or bypass cgroup checks based solely on this observation.** The correct long-term fix would be to validate lower transient-peak requirements with additional instrumented GPU runs on smaller Community hosts and adjust admission policy, with rollback and safeguards.

## Comparison — same image digest, different RunPod environments

| Run | Provider location/tier | Uncached Docker image ready | GPU generation healthy |
|---|---|---:|---|
| Oct 12, 2026 | US-KS-2 / Secure | **190 s** | Only later cached restart measured |
| Oct 13, 2026 | US-NC-1 / Secure | **85 s** | **177.698 s** pull-to-internal health |
| **Oct 17, 2026** | **US (datacenter unknown) / Community** | **328 s** | **Not reached (RAM admission rejected)** |

This Community Docker pull was **138 s slower than US-KS-2**, and **243 s slower than US-NC-1**. Because the manifest SHA-256 is identical, the different **Docker image content** cannot account for these differences, but host, region, cache, network, storage and provider tier are **not experimentally controlled**. A single Community observation is insufficient to attribute causality.

## Source provenance, privacy, and limitations

| User-provided file | SHA-256 | Description |
|---|---|---|
| `logs (3).txt` | `74fcff7027b76ef3a94f4fa0b46a57e981170c3e6596309050aada97a0a75083` | RunPod provider image-pull events; 4,709 lines |
| `logs (2)(1).txt` | `7f44324697bf3a269176b9628817b94c00aeca26f1470ea901e2a3da83cd1c65` | Container bootstrap failure events; 80 lines |
| `image(20261017-154549).png` | `b169ab0349cc6c674f37547cf8cca635a97d7799975a802c95ee4a7c4a835fdf` | RunPod location screenshot, 1338×188 |

Original logs/screenshot are retained in the conversation, **not committed as raw public files**. No Pod IDs, account identifiers, Tailscale hostnames, or environment secrets are published. Timing values are reconstructed from uploaded files with 1-second provider event precision and millisecond bootstrap markers. The active Pod, Docker image, RunPod templates and running services were **not modified** for this analysis.
