# 2026-10-12 minimal-v2 B RC1 — verified single-Pod Full + Lean GPU live test

**Outcome:** Experimental v2-B image **passed both Full and Lean RTX PRO 6000 Blackwell smoke tests** on one authorized RunPod Secure Cloud Pod. The image was **never rebuilt**. **Production deployment/merging has not happened**. Separate coding correctness and a successful real WebUI administrator login remain unverified; do not confuse throughput with correctness.

[Machine-readable test summary](./20261012-v2b-rc1-live-acceptance.json) · [US-KS-2 host screenshot / Docker cold-start evidence](./20261012-v2b-rc1-US-KS-2-coldstart-evidence.md) · [CPU/backup tracking #46](https://github.com/TommyFive/qwen38-runpod-stack/issues/46) · [Existing Draft PR #48](https://github.com/TommyFive/qwen38-runpod-stack/pull/48)

## Scope, image and isolation

- **Datacenter now identified from user screenshot: US-KS-2 (Secure Cloud).** Host allocation: 16 vCPU on AMD EPYC 9335, 283 GB RAM and 30 GB disk. The previously unrecorded first OCI pull was **190 s (11:28:19–11:31:29 UTC)**. The successful Full runtime log followed an **already-cached restart**, so its model readiness cannot be simply added to the earlier image-pull timeline. [Detailed provenance, per-layer timings and source hashes](./20261012-v2b-rc1-US-KS-2-coldstart-evidence.md).
- Authorized **single** Pod: `7rwwhciymmqr77`, `qwen38-v2b-rc1-261012-c36f28`, RTX PRO 6000 Blackwell Server Edition, Secure Cloud, **$2.49/h**, provisioned ~11:28:17 UTC, independently verified **deleted 12:02:03 UTC**. Provider showed **zero remaining Pods**. The independent Mac mini GPU watchdog and log collector were unregistered after deletion.
- Observed account balance **$3.2962450844 → $1.8943093426** (delta **~$1.40**); this is a **post-termination balance-based estimate, not an official per-Pod invoice**. RunPod's balance settled further after deletion; the $1.8943 balance was confirmed at 12:08:57 UTC. Unrelated account activity cannot be independently excluded.
- **Immutable image:** `ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7`. CUDA, PyTorch and SGLang image layer contents unchanged.
- Tested final bootstrap SHA256: `b589dfa24a75bf7e2ba1c399944c4646d07ab889d5416301f47a062a149c411c`, from feature branch commit [`dbcee65`](https://github.com/TommyFive/qwen38-runpod-stack/commit/dbcee65). All provider-published Pod ports disabled; Tailscale userspace networking and private HTTPS.
- Linux arm64 Mac mini controlled the Pod via RunPod CLI and authenticated Tailnet SSH. Secrets remained RunPod Secret references; neither provider environment nor `/proc/*/environ` contents were published.

## Root causes and verified remediation

| Observed issue | Confirmed root cause | Correction | GPU result |
|---|---|---|---|
| `/workspace/smoke-storage.sh: No such file or directory` | v2-B image lacks assumed `/workspace` directory | Put smoke helper in private runtime tmpfs; create separate runtime OpenWebUI venv directory in `/tmp` | **PASS**, helper exists while `/workspace` is absent |
| `ERROR: uv missing; OpenWebUI disabled` | `uv` not included in minimal image | **Only with `SERVE_WEBUI=1`**, download pinned `uv 0.12.10` x86_64 PyPI wheel, verify SHA256 and HTTPS distribution host; install OpenWebUI into isolated runtime venv | **PASS**, no new image needed |
| `QWEN38_WEBUI status=failed phase=uv` on first RC1 attempt | `uv --version` actually outputs `uv 0.12.10 (x86_64-unknown-linux-gnu)`, while bootstrap matched exact text `uv 0.12.10` | Fix anchored version predicate to allow architecture suffix, with regression test, commit [`dbcee65`](https://github.com/TommyFive/qwen38-runpod-stack/commit/dbcee65); update **same Pod's** env and reset | **PASS**, Full install and readiness succeeded |
| Silent/ambiguous Full startup failures | Installer output suppressed or background process launch falsely counted as readiness | Redacted private install logs, explicit phases `uv/install/readiness`, 900 s install cap, HTTP `/health` gate and nonzero fail-closed status | **PASS** for this run |

**No OpenWebUI or uv packages are baked into the OCI image.** The Lean code path never invokes the uv or WebUI installer. This run included sequential provider-controlled restarts on the *same* Pod, not additional Pods. These resets and different runtime conditions are **not** independent comparable cold-start experiments.

## Full mode `SERVE_WEBUI=1` — PASS with noted gaps

- After the corrected bootstrap was injected into **the original test Pod**, 3 workloads × 5 measured generations completed with SGLang usage-derived token counts. `BENCHMARK_GATE_VERIFIED workloads=3 runs_per_workload=5`; blocking benchmark **completed 11:46:46.654 UTC** before OpenWebUI installation.
- OpenWebUI `0.11.4` installed **at Pod startup** in its own Python virtual environment, not inside the main SGLang/PyTorch Python environment. `QWEN38_WEBUI status=installed` followed by `status=ready` at ~11:47:37 UTC; the isolated install took roughly 50 seconds including first-service initialization.
- Local `GET /health` → **HTTP 200**. Tailnet HTTPS `https://<current-pod-peer>:8443/health` → **HTTP 200 with valid TLS**. SGLang `/v1/models` without API key → **HTTP 401**. WebUI models API unauthenticated → **HTTP 401**; invalid login → **HTTP 400**; anonymous configuration: authentication enabled, sign-up disabled. A read-only aggregate query found **one administrator row** in ephemeral SQLite DB. **An actual login using the administrator's secret and authenticated chat-through-WebUI was NOT performed**, and therefore is not claimed.
- Approximate container SSD usage after runtime OpenWebUI dependency installation: **7.3 GB / 30 GB**. This expense is **Full only**; the Lean build avoids it.
- Full v2-B machine-readable benchmark medians:

| Workload | Median decode tok/s | Median TTFT |
|---|---:|---:|
| technical | 134.54 | 51.9 ms |
| code | 186.26 | 53.9 ms |
| code_edit | 194.19 | 56.8 ms |

## Lean mode `SERVE_WEBUI=0` — PASS

The same Pod's environment was safely changed to Lean mode and explicitly reset after the Full results were durably archived. **No new GPU Pod was created.**

- SGLang health generation **PASS**; **15/15** server-usage-based completions finished (benchmark completed **11:59:41.219 UTC**). The log contains `SERVE_WEBUI=0, skipping OpenWebUI, SGLang API only`.
- Private Tailnet HTTPS SGLang endpoint `:443/v1/models` accessible with valid TLS; anonymous request **HTTP 401**. UI port `:8443` **not reachable**, as intended. The server-side benchmark proves authenticated model generation occurred in Lean mode.
- Lean v2-B benchmark medians:

| Workload | Median decode tok/s | Median TTFT |
|---|---:|---:|
| technical | 133.72 | 55.2 ms |
| code | 182.89 | 53.4 ms |
| code_edit | 196.09 | 51.7 ms |

These are *decode throughput* measurements. They do not alone demonstrate coding-answer correctness, instruction following or tool-call interoperability.

## RunPod templates — no paid Pods created by template preparation

Both isolated templates point to **the exact unchanged v2-B image** and now embed the corrected bootstrap SHA256 above. Both use **30 GiB container SSD**, Tailnet-only networking, no provider-published ports, no provider public SSH, and model RAM-first storage.

| Template | ID | Default mode | Startup benchmarking | Purpose |
|---|---|---|---|---|
| Experimental Full test | `9o071jcin3` | `SERVE_WEBUI=1`, `DEBUG=1` | `BENCHMARK=1`, `BENCHMARK_BLOCKING=1` | Diagnostic/full validation |
| Separate Lean candidate | `4vzhpbj5kw` | `SERVE_WEBUI=0`, `DEBUG=0` | `BENCHMARK=0`, `BENCHMARK_BLOCKING=0` | Candidate for direct API usage, avoids production benchmark startup overhead |

The new Lean candidate was **verified as a template only, not GPU-tested with its exact BENCHMARK=0/DEBUG=0 flag combination**. No existing productive v1 template or GHCR tag changed. The research PR remains a draft and `main` remains untouched.

## CI, local evidence and remaining release gates

- For `dbcee65`: [Bootstrap integrity](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38244174820), [Benchmark regression](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38244174905), and [Image source checks](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38244174793) **PASS**.
- Private full logs, benchmark JSON and SHA256 manifests retained on the Mac mini: `~/.local/share/qwen38-gpu-live/2026-10-12-v2b-rc1/full-corrected/` and `.../lean-corrected/`. Redacted provider logs, local test reports and termination verification remain in the run root. These raw logs are **not** published.
- **Still open before claiming unrestricted production acceptance**: a separate pass/fail coding correctness suite (including tool calling, if required by client usage), positive admin-password login and genuine WebUI chat, and validation of production deployment/rollback under the intended actual `BENCHMARK=0` setting. Audio-related TorchCodec/FFmpeg import warnings were observed earlier and are not evaluated as text-serving failures.
- Pod deletion was independently verified by RunPod; no ongoing GPU charges from this test. **A new GPU Pod launch requires separate paid authorization.**

**Conclusion:** The primary direct SGLang API and optional Full/OpenWebUI infrastructure now *work* on the same optimized minimal-v2 B image. The principal missing packages and subsequent runtime bootstrap defect were fixed entirely in scripts, without a rebuild or GHCR image change. Production rollout remains a separate, intentional action.
