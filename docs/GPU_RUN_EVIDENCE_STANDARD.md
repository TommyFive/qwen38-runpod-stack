# QWEN38 GPU Run Evidence Standard (mandatory for every future paid Pod)

**Scope:** Every paid RunPod launch used for integration, functional smoke, load/benchmark, baseline cold-start, custom-image experiments, or regression. This protocol exists specifically to accumulate comparable **Secure vs Community / RunPod stock image vs pinned custom image** datasets over many subsequent runs.

**Workflow owner decision:** 2026-10-10. **Do not skip metadata or cold-start traces on "quick" test pods.** Gathering metadata does not require rerunning the throughput benchmark. Preserve evidence even for failed starts, slow scheduling, canceled deployments and aborted pods.

## Immutable record for every Pod (one record per Pod ID)

Use one file `docs/runs/YYYYMMDDTHHMMSSZ_<pod-id>.md` (or JSON + Markdown) and post its exact link to [benchmark #10](https://github.com/TommyFive/qwen38-runpod-stack/issues/10) and [cold-start/observability #23](https://github.com/TommyFive/qwen38-runpod-stack/issues/23). Keep old records; **never edit previous measurements to imply a different configuration**.

Required keys — always record explicit `unknown` and WHY when not verifiable:

| Group | Fields |
|---|---|
| Identity | exact Pod ID, repo commit SHA, RunPod template ID, RunPod Pod name, author/test intent, run start UTC from authoritative `createdAt`, create-request and terminate-request UTC |
| Cloud | **requested** Community/Secure and **independently verified actual** type; hourly billed price; direct API / source-of-truth `cloudType` or host `secureCloud` preferred; classify by price as `rate-inferred`, not proven cloud metadata |
| Geography | actual region / datacenter ID (e.g., RunPod machine `dataCenterId`) if available from authorized API or redacted platform logs, evidence source, else `unknown`; do not infer actual datacenter from GPU availability listings or IP GeoIP |
| Compute | GPU type/count and VRAM, host RAM and `/dev/shm` size, CPU, image name **and immutable digest if verifiable**, published-port configuration, container/volume sizes, GPU host cold/warm and model/image cache warm/cold states (mark unknown) |
| Model | main model HF revision, draft revision, SGLang image/runtime revisions, `SPEC`, `MAX_LEN`, `MEM_FRAC`, `MODEL_STORAGE`, `MODEL_RAM_PEAK_FACTOR`, postload weight release switch, `DEBUG`, `COLDSTART_TRACE`, `BENCHMARK`, Tailnet/Public Full/Lean |
| Timeline | UTC **and** monotonic markers; pod-create request/result, scheduling/assignment if observable, first/last image-pull or download layer, extract, container start, bootstrap, Tailscale ready, main+draft download start/end (mark combined when combined), SGLang start/GPU load/graph capture if observable, `health_generate_ready`, first **successful authenticated inference** (TTFI), and UI first auth-enabled ready |
| Outcomes | every HTTPS 443/8443/API/UI status, TLS verification, positive/negative bearer and UI auth results, RunPod portless condition for private, no secret value logged, model/VRAM/RAM proof, no cached data leaked |
| Cost & cleanup | actual `costPerHr`, tested billable minutes, approximate dollars (time × rate) with source/limitations, exact-ID kill guard and final exact-ID deletion result, post-test `pod list == []`, no global reaper |
| Benchmark | if `BENCHMARK=1` actually requested: per-workload warmup/repetition, total output tokens per server usage, tok/s, TTFT, model revision and concurrency; if not requested, state `not run intentionally: previous decoding benchmark already accepted` |

## Collection procedure

1. Before Pod launch, verify `runpodctl pod list` is empty (in currently single-project account), CI/repo SHA, current four template mappings, RunPod Secret reference, short key expiry, and exact-ID termination plan. Require owner approval for spending.
2. Record **requested** cloud class and the actual fallback. Save UTC launcher stdout/stderr as **0600** under `~/.runpod/trace-runs/<pod-id>/*` on Mac mini. Never use `set -x` with secrets or upload raw credential-bearing environment/system logs into Git.
3. As soon as RunPod returns Pod ID, start exact-ID scoped cleanup guard. Record `createdAt`, `costPerHr`, `runtimeStatus`, GPU hardware, image identity, and all **nonsecret** metadata. Determine actual Secure/Community from authenticated Pod/machine metadata only when supported; if only bill rate known, label `rate-inferred`.
4. Capture RunPod **system** and **container** logs via `runpodctl pod logs <exact-id> --source system|container` with UTC and timestamps. Fetch local Pod `QWEN38_COLDSTART` markers and relevant filtered SGLang/OpenWebUI startup evidence by permitted Tailnet SSH. Save raw originals only on Mac mini as restricted 0600 files (never in Git if secret-bearing); generate a **redacted** evidence summary for GitHub.
5. Try to obtain actual machine Datacenter ID and region via authorized RunPod metadata, preserving the source. If this needs a credentialed request not approved by tooling, record `unknown (permission unavailable)` rather than circumvent safety controls.
6. Validate only missing functional gates; **do not rerun previously accepted tok/s benchmarks** absent regression. When running custom images, use the same schema, even for failed container starts, so the baseline cohort remains comparable.
7. Delete the verified exact Pod ID, cancel the exact-ID guard, assert no running Pods and RunPod spend rate 0. Include termination evidence. No auto-TTL guarantee exists in RunPod CLI 2.15.0.
8. Commit the per-Pod sanitized record into `docs/runs` on a feature branch, use CI, merge into integration/main according to approval, and **append links and a one-line cohort row to both #10 and #23**. Never publish keys, signed URLs, private email addresses or host config dumps.

## Analytical guardrails

- Record **actual** cloud/DC/cache metadata separately from launcher intention; matching the price is circumstantial, not direct evidence.
- `image available` is not the same as `image pull complete`; if scheduling and pulls are conflated, say so.
- A five-start sample provides only a very weak empirical p95; show individual samples, failures and missing-data indicators.
- Compare Secure vs Community/custom image only for matched hardware/region/template/storage/model revision/digest where possible; report confounders.
- Default `BENCHMARK=0` prevents expensive throughput repetitions; the **cold-start timeline is always collected** (`COLDSTART_TRACE=1` unless a requested opt-out is itself the test).

## Existing baseline evidence

- [Integrated GPU runs and accepted live smokes](../INTEGRATION_SMOKE_20261010.md)
- [Community-requested Full cold-start run](../INTEGRATION_FULL_COMMUNITY_20261010.md)
- [#23 deferred observability](https://github.com/TommyFive/qwen38-runpod-stack/issues/23)
- [#10 standardized throughput benchmark](https://github.com/TommyFive/qwen38-runpod-stack/issues/10)

**This is a permanent repo workflow requirement, including all subsequent custom-image evaluation runs.**
