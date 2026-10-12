<div align="center">

# Qwen3.8 RunPod Stack — enhanced fork

**Run Qwen3.8-27B NVFP4 + DFlash2 on RunPod with an OpenAI-compatible API, optional OpenWebUI, and a private Tailscale-only deployment.**

[![Release](https://img.shields.io/github/v/release/TommyFive/qwen38-runpod-stack)](https://github.com/TommyFive/qwen38-runpod-stack/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)
[![SGLang](https://img.shields.io/badge/engine-SGLang-purple)](https://github.com/sgl-project/sglang)
[![RunPod](https://img.shields.io/badge/platform-RunPod-blue)](https://www.runpod.io/)

</div>

> **About this fork:** Based on [nicremo/qwen38-runpod-stack](https://github.com/nicremo/qwen38-runpod-stack), with additional features and independent [releases](https://github.com/TommyFive/qwen38-runpod-stack/releases). See the [original README](https://github.com/nicremo/qwen38-runpod-stack#readme) for upstream behavior. Licensed under [MIT](LICENSE).

## Contents

- [What this fork adds](#what-this-fork-adds)
- [Measured performance](#measured-performance--corrected-server-side-token-counting)
- [Changes from upstream](#changes-from-upstream)
- [Architecture and deployment modes](#architecture-and-deployment-modes)
- [Requirements and installation](#requirements-and-installation)
- [Run and connect](#run-and-connect)
- [Environment variables in RunPod UI](#environment-variables)
- [Security and costs](#security-and-costs)
- [Diagnostics and documentation](#diagnostics-and-documentation)
- [Upstream, releases and license](#upstream-releases-and-license)

## What this fork adds

The core idea from upstream remains: rent a GPU, start SGLang, and connect a local coding agent through a stable OpenAI-compatible endpoint. The following are **additions and substantial extensions in this fork**, not features to assume exist in upstream:

| Area | Features / improvements |
|---|---|
| **Working SSH access** | **SSH now works:** userspace **native Tailscale SSH** has been tested on real Pods without `/dev/net/tun` or `CAP_NET_ADMIN`; optional early **OpenSSH/RunPod debugging** can be enabled with `ENABLE_SSH=1`. The original image does not start `sshd`, so simply enabling a port in upstream is insufficient. |
| **Private networking** | Four Public/Private Full/Lean templates; private templates publish **zero RunPod ports**. Tailscale Serve provides authenticated HTTPS API on **443** and optional OpenWebUI on **8443** to permitted Tailnet peers. |
| **Startup compatibility fix** | Upstream's `pip install open-webui` modifies the live SGLang/PyTorch environment, which can break the NCCL/DeepEP startup check. This fork installs OpenWebUI in a **separate virtual environment**, protecting SGLang's GPU dependencies and allowing the Full stack to start cleanly. |
| **TLS on ephemeral Pods** | Tailscale machine identity and certificate state stored in RAM: `--state=mem:` plus a `/dev/shm` `--statedir`, with verified TLS on both endpoints. |
| **Authentication and privacy** | Mandatory SGLang API key; OpenWebUI authentication enabled, signup disabled, pre-provisioned admin, runtime logs and WebUI data on tmpfs by default, `DEBUG=0` quiet mode and redacted diagnostics. |
| **RunPod Secrets** | Default use of RunPod secret **references** (`LLM_API_KEY`, optional `HF_TOKEN`, private `TS_AUTHKEY`) rather than injecting local cleartext into the launcher; optional explicit local-credential mode. |
| **Real RAM-only model downloads** | **Both the main model and DFlash2 draft are downloaded directly from Hugging Face into a RAM-backed `/dev/shm` cache**, not downloaded to SSD and copied afterward. Since the ~22.7 GiB model blobs do not occupy the container SSD, you can provision **significantly less disk** for a new Pod/template, subject to space needed by the Docker image, OpenWebUI installation and other runtime files. **All four templates now default to 20 GiB in RAM-first mode** (only Custom Lean was live-tested at 20 GiB). Switching to SSD model downloads requires a larger disk; the tooling defaults to 100 GiB in SSD mode. `MODEL_STORAGE=ssd` remains available as an opt-in fallback. |
| **Optional RAM reclaim** | Experimental post-inference checkpoint-blob release after authenticated model use; **off by default** and only allowed with RAM storage. |
| **Correct tokens/s measurement** | Both the in-Pod benchmark and external `qwen38bench` count **actual generated tokens** via SGLang `usage.completion_tokens`, not Server-Sent Events (SSE) chunks. An SSE chunk can contain multiple tokens or none. Standardized in-Pod workloads run only with `BENCHMARK=1`. |
| **Cold-start evidence** | Host/Pod UTC + monotonic events, `qwen38cold` reports and per-Pod datasets covering image pull, model download, GPU load/graphs, health readiness, cloud class and missing region/cache metadata. |
| **Port labels in RunPod templates** | **Public template ports now have descriptive labels in the RunPod Control UI**: `8000 → SGLang API`, `8080 → OpenWebUI` (Full), and `22 → SSH`. Both private Tailnet templates have **no published ports**, so port labels do not apply to them. |
| **RunPod CLI compatibility** | Detect whether the installed `runpodctl` actually supports a server-side termination flag instead of failing Pod creation on CLI versions that removed it. **No guaranteed auto-shutdown** if the flag is absent. |
| **Four deployment templates** | Public Full/Lean and Private Full/Lean; helper scripts for safely repairing private port mappings and updating existing template helpers/secret references in place. |
| **Validation** | Real RTX PRO 6000 GPU tests for RAM/SSD, native SSH, positive/negative API auth, positive WebUI login, private HTTPS and DFlash2; offline GitHub Actions for integrity and benchmark regressions. |

**Why the Pod can use less SSD:** Model files are fetched from Hugging Face **straight into the RAM filesystem**; there is no initial SSD download followed by a copy to RAM. SGLang reads the model and draft weights from RAM and loads them into GPU VRAM. This avoids reserving disk space for roughly **22.7 GiB of downloaded weight blobs** in the tested configuration. **Docker layers, OpenWebUI and other runtime files still need container disk.** All four generated template variants now default to **20 GiB Container Disk** in RAM-first mode. Only Custom Lean has been live-tested at this size. **If you change `MODEL_STORAGE` from `ram` to `ssd`, also raise the template's Container Disk (100 GiB recommended),** or provide a sufficiently large mounted SSD volume. The CLI and template generator choose 100 GiB by default for SSD mode and reject explicitly undersized overrides. Docker layers and OpenWebUI may need additional capacity, so validate Full/official at 20 GiB before relying on it.

## Measured performance — corrected server-side token counting

On one real **RTX PRO 6000 Blackwell** Pod with **SGLang + Qwen3.8-27B NVFP4 + DFlash2**, the opt-in **in-Pod server benchmark** reported:

| Benchmark workload | Decode speed |
|---|---:|
| Technical | **135.8 tokens/s** |
| Code | **187.1 tokens/s** |
| Code editing | **190.6 tokens/s** |

Each workload had **one warm-up plus three measured runs**, using authenticated loopback requests to the running SGLang instance. Decode token counts come from **server-reported `usage.completion_tokens`**, **not** the number of streaming chunks. Reported TTFT was approximately **62–64 ms** for this in-Pod measurement path. See [benchmark methodology](docs/BENCHMARK.md) and the [GPU test record](docs/INTEGRATION_SMOKE_20261010.md).

This is **one GPU/test configuration**, not a guarantee of achievable speed across all prompts, clouds or batch sizes. It is also **not directly comparable** with older upstream `~150 tok/s` or external proxy results that used different prompts/network paths and could count SSE chunks as tokens.

## Changes from upstream

These distinctions matter if you used the original stack. Relevant changes were also proposed to the [upstream repository](https://github.com/nicremo/qwen38-runpod-stack/pulls). The linked PRs are **proposals to upstream**, not evidence that upstream already includes our fixes.

| Topic | Upstream baseline | Behavior in this fork | Upstream PR / status |
|---|---|---|---|
| Templates | Public API / Full variants | **Four** separate Public/Private × Full/Lean templates. Private templates publish **no ports**; changing `NETWORK_MODE` alone does not make a public template private. | — |
| **Port labels** | Template ports do not have explicit human-readable service labels. | Public templates supply **`--port-labels`**: **8000 = SGLang API**, **8080 = OpenWebUI** (Full only), **22 = SSH**. Labels make published services recognizable in the RunPod Control UI. Private templates publish no ports and need no labels. | [nicremo #1](https://github.com/nicremo/qwen38-runpod-stack/pull/1) · **open** |
| Secrets | Locally generated/forwarded key workflow | RunPod Secret references are the **default**; the local proxy must use the **matching** API key, not an unrelated generated one. | — |
| **SSH access** | The SGLang image does not run `sshd` by default. | **Native Tailscale SSH** works without a tun device; optional OpenSSH debugging with `ENABLE_SSH=1`. | — |
| **Full Pod startup / NCCL crash** | Installing OpenWebUI into the serving SGLang environment can mutate GPU dependencies while SGLang starts, triggering a `deep_ep.check_nccl_so()` / NCCL crash. | **Isolated OpenWebUI virtualenv** avoids replacing SGLang/PyTorch/NCCL dependencies; Full mode starts UI only after authenticated SGLang readiness. | [nicremo #4](https://github.com/nicremo/qwen38-runpod-stack/pull/4) · **open**; related [upstream issue #3](https://github.com/nicremo/qwen38-runpod-stack/issues/3) |
| **Tokens/s accounting** | Historical benchmark estimated generated tokens from SSE chunk counts, which may contain multiple tokens or none. | External and in-Pod benchmarks now use **`usage.completion_tokens`**; missing server usage is reported as unavailable instead of inventing numbers. | [nicremo #6](https://github.com/nicremo/qwen38-runpod-stack/pull/6) · **open** |
| WebUI start | Older SSH-assisted restart workflow. | WebUI is started on the Pod after authenticated SGLang readiness; no client-side SSH restart. | Related to [nicremo #4](https://github.com/nicremo/qwen38-runpod-stack/pull/4) · **open** |
| Storage / disk sizing | Model downloads/cache occupy disk. | Main and draft weights **download directly into `/dev/shm` RAM**, removing ~22.7 GiB of model weights from SSD requirements in the tested configuration; all RAM-first template variants now default to 20 GiB (only Custom Lean live-tested at 20 GiB); SSD download mode defaults to 100 GiB. | — |
| Privacy | Public RunPod service model | Authenticated public mode **or** Tailnet-only mode, with protected ephemeral runtime state and explicit logging switches. | — |
| Testing | Basic throughput tooling | Repeatable in-Pod benchmark, cold-start tracing, security/storage regression tests. | — |
| **RunPod CLI timer compatibility** | A wrapper can pass `--terminate-after` even on CLI versions that no longer support it, preventing Pod creation. | Detect supported timer flags before use; start commands remain compatible with newer CLI versions. **If unsupported, this is not a guaranteed auto-shutdown.** | [nicremo #2](https://github.com/nicremo/qwen38-runpod-stack/pull/2) · **open** |

**Upstream PR status checked 2026-10-11:** #1, #2, #4 and #6 were open. These are separate from this fork's own PRs and may change. The fork does not automatically inherit upstream changes.

## Architecture and deployment modes

```text
Local Mac / agent
  pi or any OpenAI-compatible client
         |
         v
  http://127.0.0.1:8388/v1
         |
   qwen38-proxy (local, optional)
         | reads ~/.runpod/current-endpoint.json
         | injects matching local SGLang API key
         |
         +-- PUBLIC mode ------------------------------------+
         |   https://<pod-id>-8000.proxy.runpod.net/v1      |
         |   https://<pod-id>-8080.proxy.runpod.net         |
         |                                                  |
         +-- PRIVATE mode (Tailnet devices only) -----------+
             https://<tailnet-host>.ts.net/v1               |
             https://<tailnet-host>.ts.net:8443 (WebUI)     |
                              |                             |
                              +----------> RunPod SGLang <---+
                                            + DFlash2
                                            + optional OpenWebUI
```

| Mode | Launcher | Access | RunPod ports |
|---|---|---|---|
| Public Full | `qwen38fast` | Public RunPod HTTPS proxies; API key and WebUI login mandatory | `8000/http`, `8080/http`, `22/tcp` template mappings |
| Public Lean | `qwen38pi` | Public API proxy; Bearer required; no WebUI | `8000/http`, `22/tcp` |
| Private Full | `qwen38fast --network tailnet` | Tailscale HTTPS API **443**, WebUI **8443**, native Tailscale SSH | **None** |
| Private Lean | `qwen38pi --network tailnet` | Tailscale HTTPS API **443**, native Tailscale SSH; no WebUI | **None** |

Private Tailnet-only mode requires a valid Tailscale enrollment key, HTTPS certificates and a policy allowing the client to reach Pod 443 (and 8443 for Full). Tailscale authorization **does not replace** API/WebUI authentication. Public RunPod templates **are deliberately internet-reachable**.

## Requirements and installation

You need a RunPod account and authenticated [`runpodctl`](https://github.com/runpod/runpodctl), a supported Blackwell GPU (default RTX PRO 6000), Python 3, Bash, `curl` and `base64`. macOS is used for local LaunchAgents and several helper commands; RunPod containers run Linux. [pi](https://pi.dev) is optional; any OpenAI-compatible client can call the API. For private mode, connect your client to the same [Tailscale tailnet](https://tailscale.com/).

### Install

```bash
git clone https://github.com/TommyFive/qwen38-runpod-stack.git
cd qwen38-runpod-stack
./setup.sh
```

Add `~/.local/bin` to your `PATH` if necessary. On macOS, installation also enables local LaunchAgents; see [Security and costs](#security-and-costs).

### Docker image: compact or official

The **compact image** is the default. It runs the same Qwen3.8 + DFlash2 stack with a smaller download. Choose **official** if you prefer the original SGLang image instead.

| Image | Compressed download size |
|---|---:|
| **Compact (default)** — `ghcr.io/tommyfive/qwen38-sglang:v0.2.0` | **12.9 GB** |
| **Official** — `lmsysorg/sglang:dev-qwen38-27b-dflash2` | **14.7 GB** |

Create the matching RunPod templates **once**, then start a Pod with the same image choice:

```bash
# Compact (default)
./create-templates.sh --image custom
qwen38pi --image custom

# Official (larger)
./create-templates.sh --image official
qwen38pi --image official
```

Use `qwen38fast` instead of `qwen38pi` for Full/OpenWebUI. Both images are public; **no Docker registry login** is required. Switching creates separate templates and does not change existing Pods. Image sizes are compressed registry sizes, not required Container Disk space. See [image details and tests](docs/releases/v0.2.0.md).

### RunPod templates and secrets

Create these **RunPod Secrets** in the RunPod dashboard:

| Secret | When needed |
|---|---|
| `LLM_API_KEY` | Always: API Bearer key |
| `TS_AUTHKEY` | Private/Tailnet deployments |
| `HF_TOKEN` | Only if Hugging Face access requires it |

Already using `LLAMA_API_KEY`? Keep it: use `QWEN38_API_SECRET_NAME=LLAMA_API_KEY` when creating templates. Full/OpenWebUI templates also need a `WEBUI_ADMIN_EMAIL` and `WEBUI_ADMIN_PASSWORD` (16+ characters) when launched in the RunPod UI.

Create the matching templates **once** using the command above. If creation was interrupted, retry with `--resume` (for example, `./create-templates.sh --image custom --resume`). Creating templates does not rent a GPU. See [Security](docs/SECURITY.md) for advanced settings.

## Run and connect

In the **RunPod dashboard**, choose a template and start a Pod: **Lean** = API only, **Full** = API + OpenWebUI; **Public** = RunPod HTTPS, **Tailnet** = Tailscale-only.

Alternatively, launch from your terminal:

```bash
qwen38pi                       # Public Lean
qwen38fast                     # Public Full
qwen38pi --network tailnet     # Private Lean
qwen38fast --network tailnet   # Private Full
```

The launcher prints the connection URL. Private Pods require Tailscale access: API at `https://<pod-host>.ts.net/v1`, and OpenWebUI (Full) at `https://<pod-host>.ts.net:8443`. API requests require the matching Bearer key; OpenWebUI requires login.

### Local OpenAI endpoint (optional)

The local proxy provides `http://127.0.0.1:8388/v1` for compatible clients (example: [pi configuration](pi/models.runpod.json)). Store the **same API key** as your RunPod `LLM_API_KEY` (or existing `LLAMA_API_KEY`) in `~/.runpod/qwen38.key`. For CLI-specific options, see [environment reference](docs/ENV_REFERENCE.md).

## Environment variables

**The easiest setup is in the RunPod Control UI:** open a QWEN38 template, edit its **Environment Variables** and start a **new Pod**. These are the everyday user-defined options; all defaults refer to the current templates/code.

| Variable in RunPod template | Default | What to change it for |
|---|---|---|
| `MODEL_STORAGE` | `ram` | `ram` **downloads weights directly to RAM** and minimizes model-related SSD usage; set `ssd` only if you explicitly want disk storage. |
| `MODEL_RAM_RELEASE_AFTER_LOAD` | `0` | Experimental `1`: after successful authenticated inference, delete unneeded checkpoint blobs from RAM (a restart/reload may need another download). |
| `DEBUG` | `0` | Set `1` for extra diagnostics; keep `0` for normal/private use. |
| `BENCHMARK` | `0` | Set `1` to automatically run the standardized in-Pod SGLang benchmark. |
| `COLDSTART_TRACE` | `1` | Set `0` to disable cold-start timing events. |
| `MODEL_ID` | Qwen3.8-27B NVFP4 checkpoint | Hugging Face repository for the main model; changes must match supported SGLang quantization. |
| `MAX_LEN` | `262144` | Model context length; larger contexts need adequate GPU memory. |
| `TS_ENABLE_SSH` | `1` | Native Tailscale SSH on private/Tailscale-connected Pods; `0` disables it. |
| `ENABLE_SSH` | `0` | Optional **classic OpenSSH** access/debugging; separate from native Tailscale SSH. |
| `OPENWEBUI_VERSION` | `0.11.4` | Pin the Full template's OpenWebUI version; use a version verified with the image. |

**Authentication settings:** Pod variable `SGLANG_API_KEY` (new RunPod Secret `LLM_API_KEY`, or legacy `LLAMA_API_KEY` when explicitly selected) is mandatory. Private templates additionally require `TS_AUTHKEY` (RunPod Secret); Full templates require `WEBUI_ADMIN_EMAIL` and a strong `WEBUI_ADMIN_PASSWORD` (minimum 16 characters). Do **not** store real credentials in Git.

**Important:** These template settings apply to Pods started via the **RunPod Control UI**. The optional local `qwen38fast` launcher creates its own full environment, so changing the template's ENV does **not automatically override** that launcher's settings.

Advanced options—RAM admission factors, benchmark repetitions, Secrets configuration, template helper variables, proxy settings and the complete distinction between Pod and launcher ENV—are documented in **[Advanced environment reference](docs/ENV_REFERENCE.md)**. You normally do not need them.

## Security and costs

- **Public versus private:** public RunPod proxies are reachable from the Internet and rely on application authentication. Private templates publish no RunPod ports; Tailnet Serve requires working ACL/grants *and* valid TLS, plus API/WebUI authentication.
- **Secrets:** default RunPod Secret references keep the launcher from expanding local API/HF/Tailscale secret values in `--env`. In `local` mode, the CLI request can carry plaintext secrets via arguments/control plane. SGLang also exposes its key in process argv to privileged Pod users. A rented GPU host and its provider remain in the trust boundary; RAM/tmpfs is **not** end-to-end encryption.
- **Persistence:** runtime/credential state is designed for RAM by default, but this should not be interpreted as a guarantee about host-level snapshots, provider diagnostics or all application caches.
- **Account-wide cleanup / billing:** On macOS, `./setup.sh` starts the legacy `runpod-reaper`. It and `qwen38fast stop` / `qwen38pi stop` can delete **other projects' Pods in the same RunPod account**. Requested `Nh` durations are **not guaranteed auto-shutdowns**. Monitor billing and manage Pods in the RunPod dashboard. See [cost controls](docs/COST_CONTROL.md).
- **Performance:** benchmark numbers depend on GPU, image digest, region, cache state and load. Avoid treating individual cold-start samples as general averages or comparing unknown Community/Secure datacenters causally.

Read [security and credential model](docs/SECURITY.md), [cost controls](docs/COST_CONTROL.md) and the [GPU evidence standard](docs/GPU_RUN_EVIDENCE_STANDARD.md) before production-sensitive usage.

## Diagnostics and documentation

| Guide | Scope |
|---|---|
| [Security](docs/SECURITY.md) | RunPod Secrets, privacy, authentication, private templates and limitations |
| [Cost control](docs/COST_CONTROL.md) | Account-global reaper/stop behavior and why no hard TTL exists |
| [Benchmarking](docs/BENCHMARK.md) | Opt-in in-Pod benchmark contract, workload, reports and limitations |
| [Cold-start tracing](docs/COLD_START.md) | `qwen38cold` event/report format and honest time-to-first-inference measurement |
| [Performance](docs/PERFORMANCE.md) | Checkpoint quantization choices, GPU/decoding discussion |
| [Integration smoke](docs/INTEGRATION_SMOKE_20261010.md) | Historical GPU test matrix; later success is in the dated run records |
| [Final positive-auth GPU run](docs/runs/20261010T170415Z_cg3pbcn7ua3oim.md) | Release `v0.1.0` final Private Full HTTPS/WebUI authorization proof |
| [Release `v0.1.0`](https://github.com/TommyFive/qwen38-runpod-stack/releases/tag/v0.1.0) | Versioned initial integrated release |

The repo has automated bootstrap/privacy/storage/Tailscale tests and benchmark regression CI. Run them locally before proposing behavior changes; CI does **not** rent GPUs or validate network ACLs.

## Upstream, releases and license

- **Upstream and original concept:** [nicremo/qwen38-runpod-stack](https://github.com/nicremo/qwen38-runpod-stack).
- **This fork's release history:** [TommyFive/qwen38-runpod-stack/releases](https://github.com/TommyFive/qwen38-runpod-stack/releases). Fork-specific changes are tracked here, not implied to be supported upstream.
- **Contribution approach:** prefer focused PRs; preserve upstream credit and MIT licensing. Review upstream updates before merging because authentication, template layout, credential defaults and cost control differ materially.
- **License:** [MIT](LICENSE) for repository code. Model weights are governed by their **own** respective Hugging Face repository licenses and terms; this repository's MIT license does not relicense model artifacts.
