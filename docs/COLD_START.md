# Cold-start profiling / Issue #11

## Scope and baseline

This feature records **time to first successful inference (TTFI)**, not merely
SGLang's `/v1/models` response, while separating download, health, and (when
observed) RunPod-side provisioning. It does **not** change SGLang flags or attempt
unmeasured CUDA graph, image, cache, or model optimizations. No pod is launched
by CI, and CI cannot establish a production performance improvement.

Reported baseline (one recent `qwen38fast` pod, Oct 9, 2026): **~6m50s
end-to-end**, of which **~3m** was platform image pull/start according to the
UI. This is not evidence for a 6m50s CPU-to-VRAM transfer. On a separate pod,
HF download was ~2m58s, target weight load 5.09s, draft load 37.92s, CUDA
graph capture ~56s. These are **different pods**, not a combined measurement.

### Instrumented event sources

| Source | Automatic markers | Limitations |
| --- | --- | --- |
| Launcher (host, `qwen38fast` / `qwen38pi`) | pod-create request/completion, `/v1/models`, first **successful** `/v1/chat/completions` (or failure), OpenWebUI ready | Wait-loop granularity can overstate readiness by up to ~20s; proxy latency counts toward end-to-end |
| Pod bootstrap | bootstrap start, optional SSH ready, network probe, main HF download, SGLang process start, loopback `/health_generate` 200, optional OpenWebUI isolated-venv install | Does not witness scheduling/image pull before container starts |
| RunPod UI/API timestamps and SGLang logs | Scheduling, image pull, container start, target/draft weight loading, CUDA graph capture | **Manual timestamps**, recorded only when directly evidenced; absent stages stay unknown |

Event format: `QWEN38_COLDSTART {"schema":1,"event":"...","source":"pod|host","utc":"...Z","mono":12345.6}`.
UTC is for cross-system correlation; each source's own monotonic clock is used
for durations when possible. Cross-host durations can have clock skew.
Markers contain no access tokens, prompts, response payloads or HF paths.

Telemetry is on by default for new deployments, including embedded templates.
Disable it with `QWEN38_COLDSTART_TRACE=0 qwen38fast` or set
`COLDSTART_TRACE=0` for a RunPod UI template. Existing running pods are
unchanged. The host runs **one 8-token inference probe** after model discovery,
bounded to 120s; a failed probe does not create a fake TTFI. The pod polls
`/health_generate` via authenticated loopback with a bounded ~10m deadline
without blocking service start.

**Warning:** New templates generated from this branch are required to get
trace defaults for **RunPod UI launches**. CLI launches carry their own embedded
bootstrap via `BOOTSTRAP_B64`. Re-run `./setup.sh` and recreate templates
after merging; do not assume pre-existing templates update in place.

## Collect a sample (explicit, paid pod run)

These commands are for a local workstation, **not a production VPN VPS**.
Start only when a charged RunPod experiment is intended:

```bash
# New pod creation; capture the launcher markers on the local machine.
QWEN38_COLDSTART_TRACE=1 qwen38fast 2>&1 | tee "$HOME/qwen38-host-1.log"
# Separately obtain the same pod's bootstrap.log or container-console output.
# For the baseline branch this is /workspace/bootstrap.log.
# Collect SGLang init timeline from /workspace/sglang.log or RunPod Logs.
```

When available, manually transcribe *verified* platform/UI and SGLang markers
to `runpod-observed-1.json`, **not estimated timestamps**:

```json
{
  "scheduling_start": "2026-10-10T00:00:06Z",
  "image_pull_start": "2026-10-10T00:00:20Z",
  "image_pull_end": "2026-10-10T00:03:10Z",
  "container_started": "2026-10-10T00:03:15Z",
  "target_weights_start": "2026-10-10T00:05:00Z",
  "target_weights_end": "2026-10-10T00:05:06Z",
  "draft_weights_start": "2026-10-10T00:05:08Z",
  "draft_weights_end": "2026-10-10T00:05:46Z",
  "cuda_graphs_start": "2026-10-10T00:05:48Z",
  "cuda_graphs_end": "2026-10-10T00:06:42Z"
}
```

The JSON above is **illustrative and not actual measured evidence**.
Omit unknown fields. `--platform` accepts that explicit observed-event
timeline, including SGLang timestamps. Neither a guessed timestamp nor a
weight-load duration from an unrelated pod should be passed in.

```bash
python3 bin/qwen38cold report \
  --host "$HOME/qwen38-host-1.log" \
  --bootstrap "$HOME/qwen38-bootstrap-1.log" \
  --platform "$HOME/runpod-observed-1.json" \
  --label baseline-01 --cloud community --region EU-RO-1 \
  --gpu pro6000 --storage ram --cache miss --startup cold \
  --output "$HOME/qwen38-sample-1.json"

# After multiple recorded runs:
python3 bin/qwen38cold summary "$HOME"/qwen38-sample-*.json
```

`--bootstrap` and `--platform` are optional when corresponding evidence is
unavailable. The report uses `null` for missing phases. `--output` JSON
includes per-phase seconds and evidence timestamps; the summary calculates
median and **nearest-rank p95** from successful inference samples only.
Fewer than five valid runs per group are labeled exploratory. Use
`--by cloud region storage cache startup` to specify matching groups.

The total `ttfi_sec` runs from the host's *pod-create request* through the
first **successful** chat completion and therefore includes image provisioning,
download, weight load, CUDA init, proxy propagation, and the launcher's
readiness-poll delay. `api_ready_since_create_sec` is a separate, earlier
milestone. The SGLang `health_generate_ready` event is not a completion.

### Sampling and comparison matrix

For each relevant combination, collect **at least 5 independent launches**
(without launching parallel pods). Record:

- Cloud: community vs secure; region/datacenter and GPU SKU.
- Startup: fresh new pod, warm restart, image cache hit/miss **only when proven**
  by platform evidence; otherwise use `cache unknown`.
- Storage: plain ephemeral SSD, persistent network volume, or RAM model cache
  as introduced by separate Issue #9; record pre-staging time, network throughput,
  HF/Xet bytes, memory usage, volume fees and download costs separately.
- Image: image tag **and resolved digest**, manifest size, compressed layers,
  cold/warm pull; measure layer reuse. Inspect manifest on a workstation or a
  dedicated build host, **never build/compile on production VPN VPS**.
- SGLang: main/draft load and CUDA graph phases from **same pod**. Record context,
  speculative decoding algorithm, CUDA graphs and memory fraction. Change one
  variable per A/B run, and test post-start token/s and correctness as well.

Only then rank bottlenecks and propose targeted changes. Never disable CUDA
graphs/speculation or alter SGLang's PyTorch/NCCL environment based on
uncontrolled timings. The OpenWebUI `uv` install remains in its own venv.

## Interpretation / decision gates

1. Platform image pull may dominate and **cannot be accelerated by bootstrap
   changes**. Compare image digests and pull caching across cloud/regions, and
   investigate a smaller/pre-pulled image only with measured reproducible wins.
2. HF download must be measured as bytes/seconds; the existing config.json
   speed probe is not a reliable throughput test. See #5 and #6. Do not infer
   throughput from counts of completed files.
3. The main model's reported 5.09s VRAM load must not be confused with a
   roughly 3-minute checkpoint transfer. Target/draft/CUDA markers require
   verified SGLang evidence.
4. Compare image + snapshot caching/SSD/network volume costs across total
   startup, not only sub-phase throughput. Include the cost of keeping a volume
   mounted between runs.
5. A before/after target is chosen **after** the >=5-run baseline has median
   and p95; report absolute seconds, cloud/region, sample count, confidence
   limitations and failure rate. No claimed speedup before real GPU trials.
6. SSH availability is separate from model readiness: `ENABLE_SSH=0` is the
   normal default; even with SSH enabled, no SSH daemon can exist during image
   pull. RunPod's `ssh.runpod.io` path does not prove direct TCP/22 access.

Related: #5 network check, #6 download telemetry, #7 Tailscale, #8 privacy,
#9 RAM storage, #10 steady-state benchmark. Feature branches remain independent.
