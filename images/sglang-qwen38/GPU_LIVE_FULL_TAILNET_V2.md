# Minimal-v2 controlled GPU live test — Full + Tailnet, benchmark-first

**Status: PREPARATION ONLY — NO GPU POD HAS BEEN AUTHORIZED OR LAUNCHED IN THIS CHANGE.** The code in this feature branch is experimental and must not be merged into `main` before GPU acceptance. This procedure implements the user's requested **Full + Tailnet** configuration (`SERVE_WEBUI=1`, `NETWORK_MODE=tailnet`), `DEBUG=1`, `BENCHMARK=1`, and a **blocking** complete SGLang benchmark **before OpenWebUI and any external benchmark**.

## Exact immutable images

| Variant | Immutable GHCR image |
|---|---|
| **B (first)** | `ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7` |
| v1 (matched control) | `ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd` |
| A (only if B regression/diagnostics require it) | `ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint@sha256:ec013c2e20528a92d61b6a7a0352ba081e166ef99025a5fbb4be06572381bb1e` |

Do **not** change existing `qwen38-v0.2.0-*-tailnet` templates or v1 production GHCR tags. New names are `qwen38-gpulive-20261012-<candidate>-full-tailnet-bench5-debug`, specifically one per immutable image. No production image builds or deployment happen in this procedure.

## 1. Secret and template prerequisites (cost-free)

Use a Mac mini checkout of branch `feature/minimal-v2-gpu-full-tailnet-live-test` and a RunPod account authorized for templates. Prepare **four RunPod Secrets** in the RunPod console, then verify their names without displaying secret values:

- `LLAMA_API_KEY` (the existing Qwen38 SGLang API secret name; override with `QWEN38_API_SECRET_NAME` only if your account uses another).
- `HF_TOKEN` (if the selected model requires authenticated Hugging Face access).
- `TS_AUTHKEY`, for a **tagged, least-privilege, preferably ephemeral** Tailscale device. Tailnet policy must permit the client's HTTPS 443, WebUI HTTPS 8443 and optional Tailscale SSH. The tailnet DNS/TLS configuration must be functional.
- **Separate** `QWEN38_WEBUI_ADMIN_PASSWORD` (default), a strong password of at least 16 characters. This is a **new Secret prerequisite** if your RunPod account does not already have it. `WEBUI_ADMIN_EMAIL` defaults to `admin@qwen38.example.com`; customize via `QWEN38_LIVE_WEBUI_ADMIN_EMAIL`. Do not store this password in Git, a template field or a command argument.

The RunPod CLI currently has no `secret list` command. **Template creation cannot prove that a RunPod Secret reference will resolve when a Pod launches.** Verify availability in the RunPod console **before approving GPU spend**. The bootstrap rejects missing/unresolved API and WebUI credentials; Tailscale startup fails closed if unenrolled.

Generate a local dry-run preview with **no RunPod API calls**:

```bash
bash images/sglang-qwen38/create-minimal-v2-full-tailnet-live.sh --candidate=b
```

After confirming all four Secret names exist, create **only the isolated template, not a Pod**:

```bash
bash images/sglang-qwen38/create-minimal-v2-full-tailnet-live.sh --candidate=b --create
```

The generator creates a skeleton, attaches the pinned Full/Tailnet bootstrap + Tailnet + storage + server benchmark, sets `DEBUG=1 BENCHMARK=1 BENCHMARK_BLOCKING=1`, patches any accidental provider-default public ports to `[]` and independently verifies the exact template environment and zero published ports. Any error cleans up only the newly created template. A second call refuses a name collision; it never overwrites production or experimental templates. **Default RAM-first Full container disk is 30 GiB** as a conservative starting point because Full at 20 GiB was not yet GPU-validated; keep identical disk sizes for v1/B comparisons.

Verify using `runpodctl template get <new-id> -o json` **without printing the secret-bearing environment**. Only display ID, name, `imageName`, `containerDiskInGb`, empty `ports`, absent `portsConfig`, `NETWORK_MODE=tailnet`, `SERVE_WEBUI=1`, `BENCHMARK=1`, `BENCHMARK_BLOCKING=1`, `DEBUG=1`. Refuse to start if any check fails.

## 2. Explicit separate paid GPU approval and safe pod launch

**This document does NOT authorize Pod creation.** After a separate approval for one RTX PRO 6000 Blackwell Server Edition (96 GiB) GPU, set a maximum wall-clock budget and per-Pod watchdog from the **Mac mini**. Use exactly the isolated template ID and `--ssh=false` (RunPod public SSH off; Tailscale native SSH inside private Tailnet only). Prefer Secure Cloud and a known healthy region for initial correctness; the cost/hour must be read from the actual RunPod quote, not guessed. The GPU Pod should have **no provider-published ports**. Confirm before any external connectivity testing.

**Never use `qwen38fast stop` as the safety stop** if unrelated Pods may be running: that historical subcommand deletes *all* Pods. Instead, record the exact newly created ID in a private `0600` run record and stop/delete **only that ID**. An account-wide reaper is not a substitute for a per-Pod watchdog, and a nominal launcher duration is not a guaranteed RunPod TTL.

## 3. Mandatory first GPU operation: full server-side benchmark

The Full bootstrap first establishes Tailscale and loads main + draft models into RAM, then starts authenticated SGLang. Only when the model is available does the **blocking in-Pod loopback benchmark** run. It is *synchronous*, before starting or installing OpenWebUI; other performance/quality requests must wait until the benchmark completes.

```text
NETWORK_MODE=tailnet   SERVE_WEBUI=1   DEBUG=1
BENCHMARK=1            BENCHMARK_BLOCKING=1
BENCHMARK_RUNS=5       BENCHMARK_MAX_TOKENS=512
BENCHMARK_TIMEOUT_SECONDS=1800
BENCHMARK_REPORT_PATH=/dev/shm/qwen38-runtime/benchmark.json
```

There are **three prompt classes** (technical, coding, code edit), each with **one warmup plus five measured completions**: 18 authenticated in-Pod requests in total. The benchmark only counts SGLang's `usage.completion_tokens`, not SSE chunks. The barrier requires a complete JSON with `status=completed`, all 3 workloads and 15 valid measurements, including positive finite TTFT and decode throughput derived from actual server token usage.

- Expected successful stdout markers: `QWEN38_BENCHMARK_GATE status=started`, `BENCHMARK_GATE_VERIFIED workloads=3 runs_per_workload=5`, `QWEN38_BENCHMARK_GATE status=completed`.
- A failed/partial/missing report **exits the bootstrap** without starting OpenWebUI and is **not** a valid run. Do not perform external benchmarks; capture logs and terminate **only the named test Pod** via the watchdog/operator.
- Private RAM-only report: `/dev/shm/qwen38-runtime/benchmark.json`; detailed benchmark output `/dev/shm/qwen38-runtime/benchmark.log`; redacted startup output `/dev/shm/qwen38-runtime/bootstrap.log`. `DEBUG=1` enables additional redacted diagnostics; do not export raw environment or authentication tokens.
- **Capture these artefacts to the Mac mini over authenticated Tailscale SSH BEFORE stopping the Pod.** On Pod deletion, the in-RAM logs disappear. Store under `~/.local/share/qwen38-coldstart-tests/<unique-run-id>/` with 0700 directory / 0600 logs; publish only sanitized, token-free derived evidence to the research branch.

**Caution:** `BENCHMARK_BLOCKING=1` intentionally increases Full/OpenWebUI *availability* time by the benchmark duration. Measure production cold-start readiness separately from the explicit test barrier. Use bootstrap `sglang_start`, `health_generate_ready`, `benchmark_gate_start/complete` and WebUI startup timestamps rather than conflating these phases.

## 4. GPU correctness, security and Full WebUI checks — only after benchmark PASS

- GPU: NVIDIA RTX PRO 6000 Blackwell Server Edition (SM120), `torch.cuda.is_available()`, NVFP4 main model, DFlash2 draft, FlashInfer runtime/JIT, CUDA Graphs and NCCL/DeepEP. Collect raw exception summaries and kernel failures; no optimization/deletion during this stage.
- Tailnet-only: no public RunPod HTTP/SSH mappings; API available via authenticated `https://<pod-tailnet>.ts.net/v1` (443); Full OpenWebUI via `https://<pod-tailnet>.ts.net:8443`; negative unauthorized API `401`, authenticated `200`, WebUI login required; disabled signup.
- Warm external **Tailnet** benchmark after the server report has passed:
  ```bash
  python3 bin/qwen38bench --api-base https://<pod-tailnet>.ts.net/v1 \
    --key-file ~/.runpod/qwen38.key --isl 8192 --osl 1024 --runs 5
  ```
  The new `--api-base` bypasses the **public RunPod proxy** and accepts only HTTPS `*.ts.net/v1`. Ensure the local `--key-file` contains the actual matching SGLang API secret; `qwen38bench` must not auto-create a different key.
- Record GPU VRAM, RAM, mounted `/dev/shm`, writable SSD, runtime logs (redacted), and whether GPU provider's image layers were cached. Run matched coding-quality regressions with executable tests; do not infer code quality from throughput alone.

## 5. Control v1, optional fallback A, promotion criteria

First B correctness and benchmark must pass; then optionally use the same isolated generator `--candidate=v1` to create a control Full/Tailnet template and run it **with identical** GPU SKU/cloud, region, storage, Qwen3.8 NVFP4 + DFlash2 settings, model revisions, prompt set, and warm/cold-cache classification. Only test A if B fails GPU acceptance or a conservative control is required.

Use existing [GPU validation plan](GPU_VALIDATION.md), [benchmark methodology](../../docs/BENCHMARK.md), and [issue #46](https://github.com/TommyFive/qwen38-runpod-stack/issues/46). Do not declare a speedup from a partially cached run, different GPU/region or 27-token smoke response. Use five server-usage-derived decode measurements per workload and full output for matched external benchmark.

**Approval gates:** correct GPU startup & speculative decoding, full server benchmark completed before WebUI/external tests, Tailnet security, matched Coding tests, no material performance/TTFT regression, measured download/extract/disk footprint advantage, reproducible logs, costs and safe stop. Only after explicit approval should any v2 production tag/template replace v1. `main` and existing v1 RunPod templates remain untouched.

**Known limitations:** A benchmark success does not independently prove OpenWebUI auth, Tailscale TLS or model-quality parity; those are separate tests. A test Pod's lifecycle must be managed independently and its RAM-resident logs archived before teardown. This feature branch prepares the test but intentionally does not launch or bill a GPU.
