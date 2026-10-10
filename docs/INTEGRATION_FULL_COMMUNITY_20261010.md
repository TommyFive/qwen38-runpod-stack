# GPU Live Test 1 — Private Full, Community Cloud (2026-10-10)

**Status:** Partially passed. Optional post-VRAM RAM release **passed on real GPU**, OpenWebUI authentication *negative* checks passed. Tailnet HTTPS ports 443/8443 **not reachable** (Issue #20). All paid pods have been targeted-deleted.

## Identity, provenance and infrastructure

| Field | Value / evidence |
|---|---|
| Exact Git commit | `bffa632233d8c5877890f211192e8150009619e1` (Draft PR #19), isolated worktree `/tmp/qwen38-pr19-live-test1`; the normal integration worktree was not switched |
| Base integration branch | `integration/issues-7-11-20261010`, unchanged in normal Mac mini checkout during the launch |
| Pod ID | `pmtnuoiw1gzimp` (**deleted**) |
| GPU | 1× NVIDIA RTX PRO 6000 Blackwell Server Edition |
| Template | `aa7z98qnzs` — Private Full, zero published RunPod ports, `SERVE_WEBUI=1` |
| Image | `lmsysorg/sglang:dev-qwen38-27b-dflash2`, RunPod digest `sha256:616a3e97f45191af975896cfa644279096cb31bd408a071c2e99ca7209c3cafe` |
| Requested cloud | **COMMUNITY** (`RUNPOD_CLOUD=COMMUNITY` passed to launcher; no secure fallback message) |
| Cloud evidence | Pod reported **$1.69/h**, equal to RunPod catalog **Community $1.69/h** for this GPU; catalog Secure price **$2.49/h**. **Cloud is classified COMMUNITY by request + billed GPU rate; direct `cloudType` is not returned by this version of `runpodctl pod get`.** |
| Datacenter / region | **Unknown / not API-verified**, do not infer from Tailscale relay or country of Mac mini. A future Secure comparison should aim for the same datacenter or control for region. |
| Test overrides | `MODEL_STORAGE=ram`, `MODEL_RAM_PEAK_FACTOR=1.75`, `MODEL_RAM_RELEASE_AFTER_LOAD=1`, `DEBUG=1`, `BENCHMARK=0`, `COLDSTART_TRACE=1`, `NETWORK_MODE=tailnet` |
| Admission | 22.76 GiB main+draft; 57.74 GiB free tmpfs; 47.83 GiB required with test multiplier 1.75; 116.27 GiB finite cgroup RAM available; preflight passed. Production default multiplier remains **2.5**, release remains **OFF** by default. |
| Pod price | $1.69/h GPU rate (reported current account rate included incidental spend ~$1.711/h). Account balance moved from ~$10.626 to ~$10.100; about **$0.53** cost (provisional, may settle later). |
| Cleanup | Exact-ID `runpodctl pod delete pmtnuoiw1gzimp` successful; RunPod then returned `[]`, account spending rate $0/h, temporary 45-minute exact-ID guard canceled. |

## Chronological evidence — all timestamps UTC

| Timestamp | Stage / source | Elapsed since Pod created |
|---|---|---:|
| 08:20:53.873 | Host `pod_create_request` | — |
| 08:20:55.450 | Host `pod_created` | 0 s |
| 08:25:33 | RunPod system: `Downloaded newer image` | **4m 37.6s** |
| 08:25:37 | RunPod system: `start container: begin` | 4m 41.6s |
| 08:25:38.359 | Pod `bootstrap_start` | 4m 42.9s |
| 08:25:41.076 | Tailscale connected; Native SSH / Serve configured | 4m 45.6s |
| 08:25:42.458 | Pod `main_download_start` (main **and** draft) | 4m 47.0s |
| 08:28:37.272 | Main 19.18 GiB snapshot verified | 7m 41.8s |
| 08:29:09.973 | DFlash2 3.58 GiB snapshot verified | 8m 14.5s |
| 08:29:10.119 | Pod `main_download_end` | 8m 14.7s |
| 08:29:10.266 | Pod `sglang_process_started` | 8m 14.8s |
| 08:29:10.294 | Pod `openwebui_install_start` | 8m 14.8s |
| 08:29:47 | SGLang main weight GPU load complete (~5.85s) | ~8m 52s |
| 08:29:49 | SGLang DFlash2 draft GPU load complete (~0.67s) | ~8m 54s |
| 08:29:53.463 | Pod `openwebui_install_end` | 8m 58.0s |
| **08:30:54** | First verified HTTP 200 authenticated `/v1/chat/completions` (SGLang access log, 1-second precision) | **~9m 59s** |
| 08:30:55.983 | Pod `health_generate_ready` | 10m 0.5s |
| **08:30:58.971** | RAM-release JSON receipt mtime, `verified_after_inference` | **10m 3.5s** |
| 08:31:24.645 | OpenWebUI bootstrap: admin account created successfully | 10m 29.2s |
| 08:31:39.209 | First explicitly recorded OpenWebUI `GET /api/config` HTTP 200 | **10m 43.8s** |

### Interpreting latency correctly

- Pod creation API response: **1.58s** (`pod_create_request` → `pod_created`).
- Creation → full image downloaded: **4m38s**; **this includes scheduling and any preceding platform delay**, not a pure isolated network pull-speed measurement. Image pulled on this Community-classified pod, not cache-hot.
- Bootstrap → Tailscale connected: **2.72s**.
- Main+draft HF download: **207.66s = 3m27.7s**, includes inventory/download validation but not image pull.
- SGLang process spawned → first successful authenticated chat: **~104s**, includes VRAM load, Mamba/KV allocation and CUDA Graph capture. Model transfer itself took ~6.5s combined, not ~104s.
- OpenWebUI venv package installation: **43.17s**, overlapping SGLang initialization; subsequent app startup, embedding model initialization and admin creation took longer.
- First verified SGLang inference after Pod creation: **~10m**; OpenWebUI HTTP 200 first explicitly observed after **~10m44s**. Do not treat this as median/p95 or as a controlled Secure-vs-Community comparison.
- Earlier one-off RTX PRO 6000 image pulls observed ~7m22s on another run (also billed ~$1.69/h); those are not matched by datacenter/cache and cannot establish a Secure/Community causal difference.

## Runtime and privacy checks

**Passed:**
- Existing full private template verified portless in RunPod API. Public RunPod endpoints `<pod>-8000.proxy.runpod.net/v1/models` and `<pod>-8080.proxy.runpod.net/api/config` returned **404**.
- Tailscale authenticated/online, native SSH via tailnet IPv4 succeeded. Tailscale Serve status showed HTTPS handlers on **443 → 127.0.0.1:8000** and **8443 → 127.0.0.1:8080**.
- SGLang API: anonymous **401** and wrong Bearer **401** on `/v1/models`. The automatic release worker performed authenticated inference before and after cleanup.
- OpenWebUI: isolated runtime was running at `127.0.0.1:8080`, app config `features.auth=true`, `features.enable_signup=false`; unauthenticated `/api/v1/chats/list`, `/api/v1/chats/all`, `/api/v1/auths/` and `/api/chat/completions` returned **401**. Anonymous signup attempt returned **403**. The nonsensitive `/api/config` endpoint returned **200**, as designed. A `/api/v1/chats` GET returned only the HTML SPA fallback (content-type `text/html`), **not chat data**. Bootstrap log confirmed admin account creation.
- **Automatic RAM release** `ram-release.log`: `status=waiting_for_inference`, `status=released files=3 weight_gib=22.732 freed_gib=22.731`, `status=verified_after_inference files=3`; private `ram_release.json` (0600). VRAM remained ~87,287 MiB total used. No benchmark requested or run.
- After cleanup, tmpfs usage ~**7.9 GiB**, including **~7.0 GiB at `/dev/shm/qwen38-hf/xdg/uv/archive-v0`** from the OpenWebUI install/package cache. The 22.73 GiB model weight blobs were released, but the full stack's `uv` cache remains an important additional RAM consumer.

**Not passed / not proven:**
- **Tailnet HTTPS 443 and 8443 time out** from the Mac mini even with `--noproxy '*'` and explicit DNS-to-tailnet IPv4 mapping; local `nc` to both ports also times out. A pod self-tailnet-IP HTTPS check timed out too. Mac mini Tailscale peer ping succeeded by **peer-relay** (~199–200ms) and native SSH worked. Serve configuration alone is **not proof of external access**. Root cause unverified: ACL/port policy vs userspace Serve/routing vs network path. **Issue #20**. No ACLs were changed, no public ports exposed.
- Actual authenticated OpenWebUI sign-in and chat after session creation **not verified**: credential-bearing probe was denied by remote security tooling; admin provisioning and negative auth checks did pass.
- Full OpenWebUI mode tested, but not Public Full, Secure Cloud or SSD. `DEBUG=0`, `COLDSTART_TRACE=0` and different model/draft combinations remain untested.
- `/workspace/smoke-storage.sh` was not present; bootstrap emitted a harmless missing-optional-script warning and continued.
- Cloud region/datacenter and RunPod internal scheduling duration remain unverified. Always record cloud requested, verified/inferred actual class, price, region and image cache status for future cohorts.

## Saved evidence

Private, `0600` evidence files on the Mac mini:
- `~/.runpod/qwen38-pr19-test1-system.jsonl` — 98,390 bytes RunPod system/image events.
- `~/.runpod/qwen38-pr19-test1-coldstart.jsonl` — 1,306 bytes host-independent pod marker sequence.
- `~/.runpod/qwen38-pr19-test1-release.log` — 197 bytes.
- `~/.runpod/qwen38-pr19-test1-release.json` — 51 bytes.

Host creation markers were also captured in the SSH-MCP background session:
`pod_create_request=2026-10-10T08:20:53.873Z`,
`pod_created=2026-10-10T08:20:55.450Z`.

Do **not** commit raw unreviewed runtime logs or secrets to GitHub. This report contains summarized, redacted evidence only.

## Next test design for Community vs Secure hypothesis

Use equivalent RTX PRO 6000, SGLang image digest, model/draft, storage mode, RAM factor, template/full-vs-lean mode, network conditions, image cache state and ideally **same region** across clouds. Collect **5+ independent cold starts per cohort**, separate `create → image pulled`, main+draft HF download, SGLang ready/first inference, OpenWebUI ready, and annotate RunPod cloud class from authoritative API metadata when accessible (otherwise explicitly mark as rate-inferred). A single Community 4m38s image-pull measurement does not demonstrate a cloud effect.

**Release decision:** PR #19 RAM cleanup: real-GPU **PASS** in Full RAM mode, default OFF remains. Private Full overall: **PARTIAL** until Issue #20 and positive UI login resolved. No merge to main yet.
