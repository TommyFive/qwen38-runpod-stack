<div align="center">

# Qwen3.8 RunPod Stack — enhanced fork

**Run Qwen3.8-27B NVFP4 + DFlash2 on RunPod with an OpenAI-compatible API, optional OpenWebUI, and a private Tailscale-only deployment.**

[![Release](https://img.shields.io/github/v/release/TommyFive/qwen38-runpod-stack)](https://github.com/TommyFive/qwen38-runpod-stack/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)
[![SGLang](https://img.shields.io/badge/engine-SGLang-purple)](https://github.com/sgl-project/sglang)
[![RunPod](https://img.shields.io/badge/platform-RunPod-blue)](https://www.runpod.io/)

</div>

> **Project origin:** This is the [TommyFive fork](https://github.com/TommyFive/qwen38-runpod-stack) of [nicremo/qwen38-runpod-stack](https://github.com/nicremo/qwen38-runpod-stack). Credit for the original GPU/agent workflow goes to the upstream project. This README describes **this fork's actual behavior**, including incompatible changes and security limitations; refer to [upstream's README](https://github.com/nicremo/qwen38-runpod-stack#readme) for the original design. Both use the repository's [MIT license](LICENSE). The fork is versioned independently; [v0.1.0](https://github.com/TommyFive/qwen38-runpod-stack/releases/tag/v0.1.0) is the first integrated release.

## Contents

- [What this fork adds](#what-this-fork-adds)
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
| **RunPod Secrets** | Default use of RunPod secret **references** (`LLAMA_API_KEY`, optional `HF_TOKEN`, private `TS_AUTHKEY`) rather than injecting local cleartext into the launcher; optional explicit local-credential mode. |
| **Real RAM-only model downloads** | **Both the main model and DFlash2 draft are downloaded directly from Hugging Face into a RAM-backed `/dev/shm` cache**, not downloaded to SSD and copied afterward. Since the ~22.7 GiB model blobs do not occupy the container SSD, you can provision **significantly less disk** for a new Pod/template, subject to space needed by the Docker image, OpenWebUI installation and other runtime files. The existing example templates still request **150 GB container disk**; reducing that allocation is a separate template choice, **not** automatic. `MODEL_STORAGE=ssd` remains available as an opt-in fallback. |
| **Optional RAM reclaim** | Experimental post-inference checkpoint-blob release after authenticated model use; **off by default** and only allowed with RAM storage. |
| **Correct tokens/s measurement** | Both the in-Pod benchmark and external `qwen38bench` count **actual generated tokens** via SGLang `usage.completion_tokens`, not Server-Sent Events (SSE) chunks. An SSE chunk can contain multiple tokens or none. Standardized in-Pod workloads run only with `BENCHMARK=1`. |
| **Cold-start evidence** | Host/Pod UTC + monotonic events, `qwen38cold` reports and per-Pod datasets covering image pull, model download, GPU load/graphs, health readiness, cloud class and missing region/cache metadata. |
| **Four deployment templates** | Public Full/Lean and Private Full/Lean; helper scripts for safely repairing private port mappings and updating existing template helpers/secret references in place. |
| **Validation** | Real RTX PRO 6000 GPU tests for RAM/SSD, native SSH, positive/negative API auth, positive WebUI login, private HTTPS and DFlash2; offline GitHub Actions for integrity and benchmark regressions. |

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

These distinctions matter if you already used the upstream setup:

| Topic | Upstream baseline | Behavior in this fork |
|---|---|---|
| Templates | Public API / Full variants | **Four** separate Public/Private × Full/Lean templates. Private templates must have **zero published ports**; changing `NETWORK_MODE` alone does not make a public template private. |
| Secrets | Locally generated/forwarded key workflow | RunPod Secret references are the **default**; the local proxy must use the **matching** API key, not an unrelated generated one. |
| **SSH access** | The SGLang image has no active `sshd`, so connecting to exposed SSH is unreliable/nonfunctional by default. | **Verified native Tailscale SSH** without a tun device; optional early OpenSSH provisioning for debugging (`ENABLE_SSH=1`). |
| **Full Pod startup / NCCL** | Direct `pip install open-webui` can modify or replace GPU dependencies in SGLang's Python environment, triggering a `deep_ep.check_nccl_so()` / NCCL incompatibility at startup. | **Isolated OpenWebUI venv**; avoids changing the live SGLang/PyTorch/NCCL environment and starts UI after authenticated SGLang readiness. |
| **Tokens/s accounting** | Historical SSE-chunk estimates are not actual generated-token counts. | Both benchmark paths use server-reported **`usage.completion_tokens`**; missing usage is reported as unavailable, never replaced by chunk counts. |
| WebUI start | Older SSH-assisted restart workflow | OpenWebUI starts **inside the Pod** after authenticated SGLang readiness; a client-side SSH restart is unnecessary. |
| Storage / disk sizing | Model downloads/cache consume container or volume disk. | Main and draft weights **download directly into `/dev/shm` RAM**, removing ~22.7 GiB of model weights from SSD requirements; smaller Pod container disk is **possible**, but the current template still allocates 150 GB. |
| Privacy | Public RunPod service model | Authenticated public mode **or** Tailnet-only mode, protected runtime artifacts and deliberate diagnostic flags. |
| Testing | Basic throughput tooling | Repeatable in-Pod benchmark, cold-start tracing, security/storage regression tests. |
| Rental duration | Automatic-shutdown assumptions in historical documentation | **A `1h` / `4h` argument is a requested window, NOT a guaranteed TTL or cost cap.** Existing stop/reaper are account-wide; see below. |

This fork **does not automatically inherit upstream changes**. Normal GitHub fork behavior preserves attribution and history; changes from upstream should be reviewed and merged selectively. There is no requirement to copy upstream's README verbatim.

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

### Safe manual install (does not activate the legacy reaper)

The current `./setup.sh` **automatically installs and loads an account-wide reaper LaunchAgent on macOS**. Until issue [#18](https://github.com/TommyFive/qwen38-runpod-stack/issues/18) is fixed, prefer this targeted installation if you do **not** want that background process:

```bash
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/qwen38-runpod-stack"
for file in bin/*; do
  test -f "$file" && install -m 755 "$file" "$HOME/.local/bin/"
done
for file in \
  scripts/bootstrap-sglang-openwebui.sh \
  scripts/tailscale-runtime.sh \
  scripts/model-storage.py \
  scripts/benchmark_sglang.py \
  scripts/private-template-ports.py; do
  install -m 700 "$file" "$HOME/.local/share/qwen38-runpod-stack/"
done
# Add ~/.local/bin to your PATH if necessary; start qwen38-proxy
# manually if you use the stable local endpoint.
```

If you deliberately run `./setup.sh`, first read [cost-control implications](docs/COST_CONTROL.md): it installs **both** proxy and global reaper LaunchAgents. The reaper is neither project-scoped nor a reliable per-Pod TTL.

### RunPod templates and secrets

For regular usage, prefer configuring the existing templates **once in the RunPod Control UI**. The steps below are for initial template creation and controlled updates; do not recreate templates on every launch.


Provision RunPod Secrets via its console (never commit or echo real values):

| RunPod Secret | Purpose |
|---|---|
| `LLAMA_API_KEY` | **Required** SGLang API Bearer secret (mapped to `SGLANG_API_KEY`) |
| `TS_AUTHKEY` | **Required for private mode**; tagged/ephemeral Tailscale enrollment |
| `HF_TOKEN` | Optional for Hugging Face downloads; omit if the model is public and not needed |

Create four templates **once**, or refresh existing IDs with the helper documented in [Security](docs/SECURITY.md):

```bash
./create-templates.sh    # creates FOUR templates; record the returned IDs

export QWEN38_TEMPLATE="public-full-id"
export QWEN38_TEMPLATE_PI="public-lean-id"
export QWEN38_TEMPLATE_TAILNET="private-full-id"
export QWEN38_TEMPLATE_TAILNET_PI="private-lean-id"
export QWEN38_TAILNET_DOMAIN="your-tailnet.ts.net"
```

Do not literally use the placeholder IDs above. Creating templates again creates **new IDs**, not automatic updates of existing ones. When reusing templates, refresh bundled helpers explicitly with `scripts/sync-runpod-secrets.py --refresh-helpers` and all four template-ID arguments; see [Security](docs/SECURITY.md). Verify private templates have **no published ports** before use.

**Direct RunPod console launches:** Provide `SGLANG_API_KEY`, plus `TS_AUTHKEY` for private mode, and `WEBUI_ADMIN_EMAIL` / `WEBUI_ADMIN_PASSWORD` (at least 16 characters) for Full mode. Template defaults hold references to the API/Tailscale/HF secrets, **not** a default admin password. Missing required credentials must fail closed.

## Run and connect

**Primary workflow — RunPod Control UI:** Select the appropriate **Full** (with OpenWebUI) or **Lean** (API-only), **Public** or **Private** template. Adjust the relevant template **Environment Variables** in RunPod, deploy a new Pod, and wait until SGLang is ready. For Private Full, connect through Tailscale HTTPS `https://<pod-host>.ts.net:8443`; the API uses HTTPS `https://<pod-host>.ts.net/v1`. A private template must have **no published ports** and requires Tailnet authorization, `SGLANG_API_KEY` and (for Full) WebUI admin credentials.

The commands below are **optional** local alternatives. A CLI-created Pod may **override the RunPod template's ENV**, so use the corresponding CLI/host options for such launches.


### Private Full (recommended for sensitive access)

```bash
QWEN38_NETWORK_MODE=tailnet qwen38fast 1h --network tailnet
# The launcher prints the Pod ID, API URL, and (Full) HTTPS WebUI URL.
# Login is required in OpenWebUI.
```

The launcher creates a unique Tailnet hostname by default. Your Tailnet policy must permit the client to connect on TCP 443 and 8443. The Full admin username defaults to `admin@qwen38.example.com`; the generated local password is in `~/.runpod/qwen38-webui-password` (file mode 0600). You can override both as described below.

### Private Lean, Public Full and Public Lean

```bash
QWEN38_NETWORK_MODE=tailnet qwen38pi 1h --network tailnet
qwen38fast 1h          # PUBLIC mode unless overridden by env
qwen38pi 1h            # PUBLIC API-only mode unless overridden
qwen38fast status      # status and current spend
```

**Do not use `qwen38fast stop` or `qwen38pi stop` in a shared RunPod account:** they terminate **all Pods visible to that account**. Instead use the precise ID you intend to stop:

```bash
runpodctl pod list
runpodctl pod delete YOUR_EXACT_POD_ID
runpodctl pod list
```

The `1h` argument above is **not an automatic termination guarantee**. Billing continues until RunPod actually terminates the Pod.

### Fixed local OpenAI endpoint (optional)

The proxy listens on `http://127.0.0.1:8388/v1`. It reads `~/.runpod/current-pod` and `~/.runpod/current-endpoint.json` and routes to the chosen public **or** Tailnet URL. Configure your client once (see [`pi/models.runpod.json`](pi/models.runpod.json)); run `qwen38-proxy` manually unless you deliberately installed the proxy LaunchAgent.

**Important:** the local proxy reads `~/.runpod/qwen38.key`. It must contain the **same value** as the RunPod `LLAMA_API_KEY` secret. The default RunPod-secret mode does **not** automatically copy that secret to your Mac. Optionally set `QWEN38_SGLANG_CLIENT_KEY_FILE` to a securely stored matching file for launcher readiness/TTFI probes. Never paste a live token into chat, Git, console logs or shell history.

For authenticated HTTP status testing, the correct external API returns `401` without a Bearer and `200` with a valid one. HTTPS/TLS should verify normally; do not add `-k`.

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

**Authentication settings:** `SGLANG_API_KEY` (RunPod Secret `LLAMA_API_KEY`) is mandatory. Private templates additionally require `TS_AUTHKEY` (RunPod Secret); Full templates require `WEBUI_ADMIN_EMAIL` and a strong `WEBUI_ADMIN_PASSWORD` (minimum 16 characters). Do **not** store real credentials in Git.

**Important:** These template settings apply to Pods started via the **RunPod Control UI**. The optional local `qwen38fast` launcher creates its own full environment, so changing the template's ENV does **not automatically override** that launcher's settings.

Advanced options—RAM admission factors, benchmark repetitions, Secrets configuration, template helper variables, proxy settings and the complete distinction between Pod and launcher ENV—are documented in **[Advanced environment reference](docs/ENV_REFERENCE.md)**. You normally do not need them.

## Security and costs

- **Public versus private:** public RunPod proxies are reachable from the Internet and rely on application authentication. Private templates publish no RunPod ports; Tailnet Serve requires working ACL/grants *and* valid TLS, plus API/WebUI authentication.
- **Secrets:** default RunPod Secret references keep the launcher from expanding local API/HF/Tailscale secret values in `--env`. In `local` mode, the CLI request can carry plaintext secrets via arguments/control plane. SGLang also exposes its key in process argv to privileged Pod users. A rented GPU host and its provider remain in the trust boundary; RAM/tmpfs is **not** end-to-end encryption.
- **Persistence:** runtime/credential state is designed for RAM by default, but this should not be interpreted as a guarantee about host-level snapshots, provider diagnostics or all application caches.
- **Stop/TTL risk:** `qwen38fast stop`, `qwen38pi stop` and the old `runpod-reaper` are **account-wide**. The launcher uses a requested `Nh` runtime window, **not** a guaranteed RunPod billing or auto-stop guarantee. Monitor cost and delete **the exact Pod ID**. Do not enable the legacy reaper in mixed-project RunPod accounts.
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
