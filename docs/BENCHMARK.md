# Opt-in SGLang in-pod benchmark (issue #10)

This benchmark is **off by default**. It runs in the GPU pod against
**authenticated loopback** (127.0.0.1:8000), *not* the public RunPod proxy,
after SGLang is ready. It does **not** modify the SGLang launch arguments,
reload models, alter speculative decoding, restart the API or enable /metrics.
Normal user inference remains available, although benchmarks temporarily use
GPU compute and can change concurrent latency.

## Enable

After updating the checkout and running ./setup.sh:

    BENCHMARK=1 qwen38fast
    # or:
    qwen38fast --benchmark
    BENCHMARK=1 qwen38pi

For deployments via RunPod web UI, recreate the template with
./create-templates.sh and select the new template ID. The template embeds
both bootstrap and benchmark source. Set BENCHMARK=1 in the template
environment. The default BENCHMARK=0 creates no benchmark script, worker,
report or benchmark requests. For CLI deployments, qwen38fast encodes the
installed benchmark script into the pod environment **only if enabled**.
To try the current checkout without installation, set QWEN38_BOOTSTRAP
and QWEN38_BENCHMARK_SCRIPT to the corresponding files in scripts/.

| Environment variable | Default | Effect |
|---|---|---|
| BENCHMARK | 0 | 1 to opt in. Other values rejected before pod launch. |
| BENCHMARK_RUNS | 3 | 1–20 measured runs/workload, in addition to one discarded warmup. |
| BENCHMARK_MAX_TOKENS | 512 | 1–4096 per response, *cap*, not a guaranteed number generated. |
| BENCHMARK_TIMEOUT_SECONDS | 900 | 1–7200; wall-clock bound covering readiness and HTTP inference. |
| BENCHMARK_REPORT_PATH | /tmp/qwen38-benchmark.json | JSON result; can explicitly choose /workspace/... for export. |

The benchmark worker and trace are stored in /tmp/qwen38-benchmark and
/tmp/qwen38-benchmark.log, respectively, only when enabled. They are private
(0700 directory, 0600 report/script). The final report is atomically replaced.
Benchmark failures, unauthorized API or deadlines mark a failed/partial report;
they do **not** stop or restart a healthy inference server. Pod shutdown sends
SIGTERM to the benchmark worker. Read it on the pod:

    cat /tmp/qwen38-benchmark.log
    cat /tmp/qwen38-benchmark.json

An explicitly configured /workspace report persists as long as that volume
exists. Avoid persistent exports unless needed; the default report is ephemeral.
No request bodies, full prompts, completions, API keys, authorization headers
or raw get_server_info config are written by the benchmark. Reports include
model identifiers, basic quantization metadata, GPU model/VRAM/topology, engine
versions and timings, but **do not share reports publicly by default** because
deployment details can still be sensitive.

## Workload and methodology

The versioned qwen38-sglang-v1 prompt set has three fixed workloads in order:
technical explanation, Python code generation and Python code correction.
For each: one **discarded warm-up** followed by N serial single-stream measured
calls with temperature=0, max_tokens as configured and
chat_template_kwargs.enable_thinking=false. This uses the Qwen/SGLang request
field confirmed for the deployed engine; inspect the generated completion if a
future model version changes support. No overlap/concurrency, adaptive prompt
padding or GPU reload is done. The suite is a fixed *workload*, not a promise
of fixed output length.

SGLang streaming usage.completion_tokens and usage.prompt_tokens are
authoritative when present. A token is **never** inferred from a nonempty
SSE chunk: one chunk may contain several tokens, and keepalive/role/tool/SSE
events may contain zero tokens. If usage is missing, the report marks token
count and decode rate null/unavailable rather than fabricating numbers.

- wall_seconds: full completion duration on loopback.
- ttft_seconds: first nonempty text, reasoning_content or tool output
  (not a heartbeat, role message or empty delta).
- decode_seconds: elapsed time after first output until stream completion.
- tpot_seconds: decode_seconds / (completion_tokens - 1), where there are
  at least two **server-reported** output tokens.
- decode_tokens_per_second: reciprocal of TPOT under the same conditions.
- speculative_acceptance: null unless a future verified SGLang field supplies
  such stats; /metrics may be 404 under default configuration.

Reports use schema_version=1, prompt_set_revision and raw per-run data, plus
server/GPU/model/config metadata, status and timestamps. Model revision is
best-effort from the downloaded Hugging Face snapshot directory, not guessed.

## Resource and cost impact

Default: three workloads × (one warm-up + three measured) = **12 serial
inference requests**, with at most 512 completion tokens each (maximum total
6,144 tokens, excluding input). Duration varies with GPU, model load, cache,
prompt lengths, speculative acceptance and any concurrent traffic. The bounded
default deadline is 900 seconds; this is a **maximum** for the benchmark worker,
*not* an automatic pod termination timer. With example $1.69/hour GPU billing,
a full 15-minute benchmark window would cost about $0.42 in rental time **if**
it caused 15 extra minutes of running; it is not a fixed benchmark charge.
Use the existing RunPod timer/reaper independently to bound **pod** lifetime.
Running the benchmark changes user-request latency through shared GPU load.

## Compared with qwen38bench

| | In-pod BENCHMARK=1 | Manual qwen38bench |
|---|---|---|
| Endpoint | Authenticated 127.0.0.1:8000 | RunPod HTTPS proxy |
| Purpose | Comparable engine-local workload/performance | End-to-end user-perceived proxy latency |
| Workloads | 3 versioned fixed prompts | 1 configurable padded technical prompt |
| Sampling | 1 warmup + N per workload | 1 warmup + N |
| Security | Bearer key via pod environment | Reads local ~/.runpod/qwen38.key (or --key-file) |
| Results | Private JSON and short log summary | Terminal median/measurements |

**Do not compare client and in-pod TTFT/tok/s as if they were the same
measurement path.** The external client now uses usage.completion_tokens too;
earlier SSE-event-count figures may substantially underestimate decode tokens.

## Verification

CI runs Python compilation, shell syntax, mocked authenticated SSE inference,
readiness retries, usage-vs-chunk accounting, missing usage, invalid settings,
missing DONE, end-to-end 3 × (1+N) requests, report privacy, SIGTERM and
the existing CLI tests. CI has no GPU or SGLang model; these are **offline
tests**, not measured GPU performance.

GPU smoke checklist (explicit on-demand pod required; not run by CI):
1. BENCHMARK=0: boot the pod and check that /tmp/qwen38-benchmark* is absent.
2. BENCHMARK=1 BENCHMARK_RUNS=1 BENCHMARK_MAX_TOKENS=16: boot the
   same engine settings, verify API availability during benchmark, check
   exactly 6 completed requests and three report workloads.
3. Repeat with nonempty SGLANG_API_KEY, then with no key in a controlled
   private test; check no secret strings in logs/report.
4. Kill benchmark worker / simulate its timeout and verify SGLang remains
   healthy. Test pod termination with SIGTERM. Do not run a real GPU benchmark
   on any production VPS/build server.
