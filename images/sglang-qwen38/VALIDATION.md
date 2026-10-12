# Validation and recovery

## Evidence chronology and limits

No new GPU, image build or remote-host change was performed for repository
consolidation. Historical machine timestamps retain explicit timezone offsets;
human-readable times here use **CST (UTC+8)**. Raw evidence may retain UTC keys
so original timestamps remain machine-comparable.

1. v1: CPU/GPU text inference and Bearer auth passed; initial provider-host
   restarts and partial image cache prevent a clean cold-start baseline.
2. v2 A/B: independent no-network restored CPU imports/config/hash parity passed,
   **12 October 2026, 10:28:08 CST**. Both complete release OCI layouts were
   reconstructed and hash-verified by **11:00:59 CST**. Earlier documents saying
   “B final OCI untested” were superseded by these records.
3. Initial v2 B GPU run: NVFP4+DFlash2, 15 measured completions and Tailnet auth
   passed; Full failed because `uv` was absent. This partial run is not Full acceptance.
4. Subsequent v2 B run: corrected external bootstrap, Lean and Full each passed
   15 measured completions; OpenWebUI health/auth endpoints passed. This is the
   v0.2.2 release evidence. Image content was not rebuilt to fix the bootstrap.

| Evidence file | Content |
|---|---|
| [v2-checkpoint.json](evidence/v2-checkpoint.json) | Historical A/B archive, manifest, asset SHA256 and successful publication/backup workflow references; not a live asset availability assertion |
| [v2-cpu-validation.json](evidence/v2-cpu-validation.json) | Complete baseline/A/B CPU records, parity checks, recovery logs and hashes; old “remaining” fields are time-scoped historical statements |
| [v2-gpu-acceptance.json](evidence/v2-gpu-acceptance.json) | Separate initial partial and subsequent Lean/Full acceptance; no merging of incompatible outcomes |
| [v2-coldstart.json](evidence/v2-coldstart.json) | Subsequent uncached pull and separate cached restart, layer timings and source checksums |
| [v2-sglang-benchmark.json](evidence/v2-sglang-benchmark.json) | Initial GPU run's 15 raw server-usage-derived measurements, model revision and settings; not the later Full/Lean benchmark |

All retained JSON measurements are historical observations, not synthetic new
results. Private pod/template IDs, account balances, workstation paths and
infrastructure names are not needed to reproduce the methodology and are removed.

## CPU / OCI procedure

On an independently approved Linux x86_64 host with sufficient disk and the
immutable images available locally (these commands are not run by ordinary CI):

- `tools/audit/run-collect.sh`: read-only, network-disabled files/Python/dpkg/ELF,
  FlashInfer token classification and bounded duplicate SHA256 inventory.
- `collect.py`, `analyze.py`, `subtree-report.py`, `native-deps.py`: distinct
  inventory, aggregate, subtree and ELF DT_NEEDED/RUNPATH views.
- `compare-cuda-copies.py`: fixed wheel/system pairs; `verify-duplicates.py`:
  bounded broader candidates from the inventory. Equal size/name is not proof.
- `prune-candidate.py`: opt-in exact Rust suffix removal or 11 hash-identical CUDA
  replacements. `generate-repack.py` emits the metadata-preserving scratch
  Dockerfile; no automatic publication.
- `inspect-local-oci.py`: local OCI TAR manifest checksum and compressed sizes.
  `split-large-oci-layers.py` streams ordered bounded layers;
  `verify-split-oci.py` checks source/split filesystem parity.
- `verify-repack.py`, `validate-oci.sh`, `run-import-smoke.sh` and
  `validate-restored-cpu.py`: runtime metadata, link/hash and no-network imports.
  Writable cache tmpfs is required even for original-image imports.

Historic baseline/A/B versions matched: Torch 2.13.0+cu130, FlashInfer 0.6.17,
SGLang and Transformers 5.12.1. All 11 CUDA hashes matched; A/B Rust intermediates
were absent. Baseline `pip check` already reported Torch expecting NCCL 2.29.7
while 2.30.7 was installed (upstream DeepEP override), and `nixl` referring to
nixl-cu12 while cu13 was installed. Do not label these as new pruning regressions.
CPU import success does not prove GPU/JIT execution or inference correctness.

## GPU acceptance and benchmarks

Required future configuration: RTX PRO 6000 Blackwell 96 GiB **SM120**, same
main model `sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4`,
draft `incoai/Qwen3.8-27B-DFlash2`, revisions, 262144 context,
0.85 memory fraction, quantization and speculative settings. Capture CUDA graph,
FlashInfer/provider, NCCL/DeepEP and JIT errors; no silent unquantized fallback.

Server benchmark uses 3 classes (technical, coding, code-edit), 1 warmup plus
5 measured completions each, 512 output tokens, concurrency 1, temperature 0,
streaming, 1800-second timeout. Count SGLang `usage.completion_tokens`, **not SSE
chunks**; preserve TTFT, decode seconds/tok/s and full report. Speculative
acceptance length was unavailable where metrics were not enabled; do not invent it.

`BENCHMARK=1 BENCHMARK_BLOCKING=1` imposes a fail-closed barrier before installing
or starting Full WebUI and before external benchmarks. Partial/missing/invalid
reports must abort; expected report status is completed with all 15 valid runs.
Benchmark duration is not production startup overhead unless enabled there.

| Run | Technical tok/s | Code tok/s | Code-edit tok/s | Median TTFT ms, same order |
|---|---:|---:|---:|---|
| Initial v2 B (Full failed later) | 132.69 | 187.09 | 190.78 | 64.6 / 64.1 / 63.2 |
| Subsequent Lean | 133.72 | 182.89 | 196.09 | 55.2 / 53.4 / 51.7 |
| Subsequent Full | 134.54 | 186.26 | 194.19 | 51.9 / 53.9 / 56.8 |

Full runtime installed OpenWebUI 0.11.4 (260 packages) via verified on-demand uv
0.12.10. `/workspace` handling and the uv version predicate were corrected in
external bootstrap code. Observed writable disk use after UI installation ~7.3 GB.
Lean skipped WebUI and had no 8443 listener. Both used a 30-GiB test container disk.

**Remaining gaps:** real successful administrator-password login and authenticated
WebUI chat were not tested; coding correctness/quality was not independently
scored; no matched v1/B GPU throughput comparison; no exhaustive long-context or
multi-GPU compatibility acceptance. Optional TorchCodec/FFmpeg audio warnings
remain outside text-serving acceptance. Historical initial Full failures are
retained as such, not silently changed into passes.

## Cold-start: do not combine distinct runs

| Stage, seconds | v1 initial | v1 second | initial v2 B |
|---|---:|---:|---:|
| First image activity → image ready | 180 | 303 | 200 |
| Create request → bootstrap | 185.5 | 308.4 | 228.2 |
| Create → first image activity | 1.4 | 1.4 | 24.9 |
| Model RAM download | 253.0 | 22.2 | 67.1 |
| SGLang start → generation health | 79.3 | 67.2 | 103.7 |
| Create → generation health | 518.7 | 398.9 | 403.1 |

v1 had 15 `Already exists` layer IDs in each run (partial cache), 150- and 20-GiB
container disks respectively. Initial B had 8 layer IDs and no cache-hit markers;
first extraction → last pull completion 164 seconds. Missing terminal download
events prevent separating complete download time. Different hosts/storage/cache
invalidate causal speedup claims; 17.07% smaller is **not** 17.07% faster startup.

First v1 host: US-NE-1 Secure Cloud, 16 vCPU, 251 GB RAM. Provider reported a
critical machine warning; restarts occurred after initial generation health.
At 14:12:20 CST it stopped, restarted around 14:12:23 and 14:12:50; weights were
re-fetched until 14:16:06.792, health returned at 14:17:24.138 and external
authenticated chat at 14:17:43. Host fault is plausible, not a proven root cause.
Five 27-token smoke completions gave median 142.91 tok/s, TTFT 0.050 s, total
0.232 s: **not comparable to the standardized 512-token benchmark** or an older
150.7 tok/s baseline. Root overlay reported 161,061,273,600 bytes, ~281 MB peak
writable occupancy; tmpfs 125,000,003,584 bytes with ~24.45 GB model use. This does
not prove an arbitrarily small provider container disk will provision correctly.

Subsequent B, US-KS-2 Secure Cloud: **190 seconds** uncached pull to image-ready,
8 layers, zero cached layers; first-to-last completed download 158 s,
first nonempty extraction-to-ready 137 s, last download-to-ready 32 s,
create-to-container start 194 s. These intervals overlap and cannot be summed.
A **later cached restart** measured model download 104.104 s; SGLang-to-health
89.362 s; bootstrap-to-health 196.528 s; cached container-to-health 197.809 s;
health-to-benchmark gate 54.897 s; WebUI install-to-ready 50.975 s;
cached container-to-WebUI-ready 303.704 s. Do not add 190 seconds to these and
call the result a measured continuous cold boot. Peak observed GPU use 87,465 MiB,
tmpfs 30.619 GiB; main+draft 22.76 GiB. Source timestamps rounded to seconds imply
approximately 1-second precision for provider phases.

Use `tools/analyze-coldstart.py` with archived provider/container markers. A fair
future comparison needs matched GPU SKU, cloud/region, storage, models/revisions,
network, fresh host/cache classification and timed authenticated user inference.
Internal `health_generate_ready` is not itself a user-facing TTFI measurement.

## Security, templates, RAM/SSD and Lean/Full

Regular `create-templates.sh` dry-runs and tests cover public versus **portless**
Tailnet templates, embedded bootstrap integrity, exact image pins and secret
references. Do not recreate historical one-shot templates. RunPod template names
must be shorter than 50 characters. An unresolved Secret reference is not proof
that the secret exists; runtime must fail closed.

Full requires distinct API and WebUI administrator secrets (minimum 16-character
WebUI password), signup disabled and authentication enabled. Tailnet requires
least-privilege tagged ephemeral enrollment, valid DNS/TLS and appropriate policy.
API HTTPS 443: missing/wrong key rejected, successful authenticated benchmark;
Full WebUI HTTPS 8443: health 200, unauthorized API 401, invalid login 400,
one administrator row observed. Positive login/chat remains the gap above.
No public RunPod HTTP/SSH mappings were present in the Tailnet GPU smokes.

`bin/qwen38bench --api-base https://pod.example.ts.net/v1 --key-file KEYFILE`
supports direct Tailnet HTTPS only; no URL credentials, alternate port, query,
fragment, public proxy or simultaneous pod ID. It requires an existing matching
key and never generates a replacement. Tests cover rejection cases and HTTP auth.

Current regular defaults: RAM-first 20 GiB container disk; SSD mode 100 GiB,
minimum 50 GiB. Historical Full/Lean GPU tests used 30 GiB; do not claim Full at
20 GiB was GPU-proven. RAM-only logs/models are ephemeral; preserve sanitized
measurements before a disposable test ends. Per-pod termination must target the
exact test resource; account-wide stop/reaper is not an acceptable test watchdog.

## Registry, release and supported recovery

```bash
python3 images/sglang-qwen38/tools/inspect-registry.py --reference v0.2.2
python3 images/sglang-qwen38/tools/inspect-registry.py --reference v0.2.0
```

Checks: resolve tag, hash manifest bytes, select exactly one linux/amd64 manifest,
hash config, validate architecture/rootfs layer count, HEAD-check every config
and layer descriptor size. Redirects never forward bearer credentials; HEAD stays
HEAD. Blob availability is not a newly downloaded full-content SHA256 proof.

On an approved recovery host, pull the **production repository digest** shown in
README; retain v0.2.0 as rollback. The 30-asset CPU GitHub release is retired;
no current tool/workflow downloads it. Historic asset metadata remains evidence,
not operational recovery instructions. No large assets are copied to another release.
The separate `ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint` package remains
untouched: A provenance digest
`sha256:ec013c2e20528a92d61b6a7a0352ba081e166ef99025a5fbb4be06572381bb1e`, B as
in README. Its removal needs separate approval, including the promotion workflow's
remaining source dependency and unknown external consumers. Historical publication
and recovery proofs: [GHCR run](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38159273066),
[asset backup run](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38158692348),
[acceptance tracking](https://github.com/TommyFive/qwen38-runpod-stack/issues/46).

## Regression suite

Image tests: pins/overlay, compressed sizes, registry auth/redirect behavior,
FlashInfer classification, CPU inventories, SHA fail-closed pruning/repack,
restored imports/config logic, split OCI parity and evidence integrity.
Repository tests: exhaustive release inventories, Bootstrap/uv readiness,
private-port enforcement, public/Tailnet, RAM/SSD, benchmark barrier/reporting,
secret redaction, template dry-runs and privacy scanning. Shell tests that require
Linux tmpfs execute in GitHub Actions; local macOS syntax/CPU tests are not a
substitute. Workflow builds/promotions remain opt-in; ordinary CI builds no image.

Recovery/rollback of this source cleanup is a normal reviewed Git revert, **not**
an image rebuild, tag overwrite or remote history rewrite. Reverting privacy
changes publicly would re-expose data; consult the private remediation report first.
