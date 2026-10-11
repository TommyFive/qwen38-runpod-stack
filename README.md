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
- [Environment variables](#environment-variables)
- [Security and costs](#security-and-costs)
- [Diagnostics and documentation](#diagnostics-and-documentation)
- [Upstream, releases and license](#upstream-releases-and-license)

## What this fork adds

The core idea from upstream remains: rent a GPU, start SGLang, and connect a local coding agent through a stable OpenAI-compatible endpoint. The following are **additions and substantial extensions in this fork**, not features to assume exist in upstream:

| Area | Features / improvements |
|---|---|
| **Private networking** | Optional userspace Tailscale with **native Tailscale SSH**; dedicated Tailnet-only Full and Lean templates publish **no RunPod ports**. Tailscale Serve exposes authenticated API HTTPS on **443** and optional OpenWebUI HTTPS on **8443** to approved Tailnet peers. |
| **TLS on ephemeral Pods** | Tailscale machine identity and certificate state stored in RAM: `--state=mem:` plus a `/dev/shm` `--statedir`, with verified TLS on both endpoints. |
| **Authentication and privacy** | Mandatory SGLang API key; OpenWebUI authentication enabled, signup disabled, pre-provisioned admin, runtime logs and WebUI data on tmpfs by default, `DEBUG=0` quiet mode and redacted diagnostics. |
| **RunPod Secrets** | Default use of RunPod secret **references** (`LLAMA_API_KEY`, optional `HF_TOKEN`, private `TS_AUTHKEY`) rather than injecting local cleartext into the launcher; optional explicit local-credential mode. |
| **RAM-first model storage** | Main and DFlash2 draft model plus Hugging Face cache on verified `/dev/shm` tmpfs by default, finite cgroup v1/v2 capacity admission checks, fail-closed behavior, opt-in `MODEL_STORAGE=ssd`. |
| **Optional RAM reclaim** | Experimental post-inference checkpoint-blob release after authenticated model use; **off by default** and only allowed with RAM storage. |
| **Benchmarking** | Opt-in standardized, authenticated in-Pod SGLang benchmark (`BENCHMARK=1` / `--benchmark`) with fixed workloads, token-accounting checks, JSON reports and regression tests. |
| **Cold-start evidence** | Host/Pod UTC + monotonic events, `qwen38cold` reports and per-Pod datasets covering image pull, model download, GPU load/graphs, health readiness, cloud class and missing region/cache metadata. |
| **Four deployment templates** | Public Full/Lean and Private Full/Lean; helper scripts for safely repairing private port mappings and updating existing template helpers/secret references in place. |
| **Validation** | Real RTX PRO 6000 GPU tests for RAM/SSD, native SSH, positive/negative API auth, positive WebUI login, private HTTPS and DFlash2; offline GitHub Actions for integrity and benchmark regressions. |

**Release verification:** The final [GPU auth/TLS run](docs/runs/20261010T170415Z_cg3pbcn7ua3oim.md) returned API HTTP **401** with missing/incorrect keys and **200** with a valid external Bearer, plus a successful OpenWebUI login and authenticated chat access (**200**). These facts apply to the tested configuration, **not** to every GPU, every optional switch or every RunPod region.

## Changes from upstream

These distinctions matter if you already used the upstream setup:

| Topic | Upstream baseline | Behavior in this fork |
|---|---|---|
| Repository to clone | `nicremo/qwen38-runpod-stack` | **Clone `TommyFive/qwen38-runpod-stack`** for these features. |
| Templates | Public API / Full variants | **Four** separate Public/Private × Full/Lean templates. Private templates must have **zero published ports**; changing `NETWORK_MODE` alone does not make a public template private. |
| Secrets | Locally generated/forwarded key workflow | RunPod Secret references are the **default**; the local proxy must use the **matching** API key, not an unrelated generated one. |
| WebUI start | Older SSH-assisted restart workflow | OpenWebUI starts **inside the Pod** after authenticated SGLang readiness; a client-side SSH restart is unnecessary. |
| Storage | Primarily disk-backed model/cache | RAM-backed main+draft cache by default, optional SSD mode with explicit checks. |
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

### Clone this fork (not upstream)

```bash
git clone https://github.com/TommyFive/qwen38-runpod-stack.git
cd qwen38-runpod-stack
git checkout main
```

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

This is the **configuration reference for external/user-configurable ENV switches implemented at `v0.1.0`**. There are two distinct layers:

- **Launcher ENV** is set on the local machine before `qwen38fast` / `qwen38pi`, typically with the `QWEN38_` prefix. The launcher assembles the entire RunPod ENV object; merely adding an arbitrary Pod variable to your local shell does **not** mean it is forwarded.
- **Pod ENV** is supplied directly through RunPod template/console or forwarded by the launcher. Variables with the same concept may have different names at these layers (for example `QWEN38_NETWORK_MODE` → `NETWORK_MODE`).

Defaults below are code defaults, not a guarantee that the live RunPod templates or local installation have been refreshed.

### Launcher: templates, connectivity and credentials

| Variable | Default | Meaning |
|---|---|---|
| `QWEN38_TEMPLATE` | legacy built-in public Full ID | Override public Full template ID; use your own current template |
| `QWEN38_TEMPLATE_PI` | legacy built-in public Lean ID | Override public Lean template ID |
| `QWEN38_TEMPLATE_TAILNET` | unset | **Required** private Full template ID in `tailnet` mode |
| `QWEN38_TEMPLATE_TAILNET_PI` | unset | **Required** private Lean template ID in `tailnet` mode |
| `QWEN38_NETWORK_MODE` | `runpod` | `runpod` = public RunPod proxy; `tailnet` = private portless template |
| `QWEN38_TAILNET_DOMAIN` | detect from local Tailscale | Your `*.ts.net` tailnet DNS suffix; required if detection fails |
| `TS_HOSTNAME` | generated random label | Optional explicit Tailnet/MagicDNS Pod hostname |
| `TS_ENABLE_SSH` | `1` | Enable **native** Tailscale SSH on a connected Pod; `0` disables |
| `TS_AUTHKEY` | unset | Used by the **opt-in local-credential** mode; default RunPod-secret mode references secret `TS_AUTHKEY` instead |
| `QWEN38_CREDENTIAL_MODE` | `runpod_secrets` | `runpod_secrets` (default) or `local`; legacy local mode exposes credentials to the RunPod CLI ENV call |
| `QWEN38_HF_SECRET_NAME` | `HF_TOKEN` | RunPod HF Secret name; set explicitly to empty to omit the reference |
| `QWEN38_SGLANG_CLIENT_KEY_FILE` | unset | Optional local matching SGLang API key file for launcher's positive readiness/inference probes |
| `QWEN38_WEBUI_ADMIN_EMAIL` | `admin@qwen38.example.com` | Pre-provisioned Full WebUI admin email |
| `QWEN38_WEBUI_ADMIN_PASSWORD` | generated protected file | Full WebUI admin password override; must be at least 16 characters |
| `HF_TOKEN` | unset (local mode) | Optional local Hugging Face token in `local` credential mode; file fallback `~/.cache/huggingface/token` |
| `RUNPOD_CLOUD` | `COMMUNITY` | First attempt to launch on Community; launcher tries Secure if Community creation fails |

### Launcher: storage, observability, benchmarking and helpers

| Variable | Default | Meaning |
|---|---|---|
| `QWEN38_MODEL_STORAGE` | `ram` | `ram` (verified tmpfs) or explicit `ssd` |
| `QWEN38_MODEL_RAM_DIR` | `/dev/shm/qwen38-hf` | RAM-backed HF/cache model root |
| `QWEN38_MODEL_SSD_DIR` | `/workspace/hf` | SSD/container/volume storage root for opt-in SSD mode |
| `QWEN38_RAM_PEAK_FACTOR` | unset → Pod default `2.5` | Optional finite-capacity RAM admission multiplier; accepted values 1.5–5.0 |
| `QWEN38_MODEL_RAM_RELEASE_AFTER_LOAD` | `0` | Experimental opt-in weight blob release after authenticated inference; requires RAM mode |
| `QWEN38_DEBUG` | `0` | `0` quiet/redacted; `1` additional diagnostics (not a guarantee of zero data exposure) |
| `QWEN38_COLDSTART_TRACE` | `1` | Host + Pod cold-start milestone collection; `0` opt out |
| `QWEN38_ENABLE_SSH` | `0` | Enable **legacy OpenSSH debugging** on the Pod (separate from native Tailscale SSH) |
| `BENCHMARK` | `0` | `1` runs opt-in in-Pod benchmark once ready; same as `--benchmark` |
| `BENCHMARK_RUNS` | `3` | Benchmark repetitions (1–20) |
| `BENCHMARK_MAX_TOKENS` | `512` | Max output tokens per benchmark workload (1–4096) |
| `BENCHMARK_TIMEOUT_SECONDS` | `900` | Benchmark timeout (1–7200 seconds) |
| `BENCHMARK_REPORT_PATH` | `/dev/shm/qwen38-benchmark.json` | Report path on the Pod; protect any prompts/results |
| `QWEN38_BOOTSTRAP` | installed bootstrap script | Override the bootstrap file embedded into the next Pod |
| `QWEN38_TAILSCALE_RUNTIME` | installed Tailnet helper | Override bundled Tailscale runtime source |
| `QWEN38_STORAGE_HELPER` | installed model-storage helper | Override bundled storage helper |
| `QWEN38_BENCHMARK_SCRIPT` | installed benchmark script | Override bundled benchmark implementation |

### Template creation and local tools

| Variable | Default | Meaning |
|---|---|---|
| `QWEN38_MODEL` | default NVFP4 model repo | **Template-creation only** model ID; for `qwen38fast` launches use `--model REPO` instead |
| `QWEN38_PORTS_HELPER` | `scripts/private-template-ports.py` | **Template creation only** port repair/verification helper |
| `QWEN38_PROXY_PORT` | `8388` | Local proxy listen port (loopback only) |
| `QWEN38_PROXY_VERBOSE` | unset / `0` | `1` emits redacted exchange diagnostics |
| `RUNPOD_API_KEY` | unset → secure native `~/.runpod/config.toml` | Optional RunPod API credential override used by private-template port repair; avoid placing it in shell history or logs | 
| `RUNPODCTL_BIN` | `/opt/homebrew/bin/runpodctl` | `rp` wrapper and legacy reaper CLI path |
| `RUNPOD_MAX_AGE_HOURS` | `1` | `rp` requested duration when no explicit `Nh` argument; **not** guaranteed TTL |
| `RUNPOD_MAX_AGE` | `1h` | Legacy account-wide reaper age threshold (when explicitly installed/enabled) |
| `RUNPOD_REAPER_DRY_RUN` | `0` | Legacy reaper dry-run mode; `1` logs instead of deleting |

### Pod-only ENV (direct RunPod console / advanced deployments)

These are not automatically read from your local shell by `qwen38fast`. Template/launcher defaults apply to most variables; set Pod overrides only when you understand their security and storage effects.

| Variable(s) | Pod default | Meaning |
|---|---|---|
| `NETWORK_MODE` | `runpod` | `runpod` or `tailnet`; **requires correct matching published port configuration** |
| `SGLANG_API_KEY` | **required** | Nonempty SGLang Bearer secret; template references `LLAMA_API_KEY` |
| `TS_AUTHKEY` | empty | Tailnet enrollment, required in private mode; recommended RunPod Secret reference |
| `TS_HOSTNAME`, `TS_ENABLE_SSH` | generated, `1` | Pod-side Tailnet hostname and native SSH toggle |
| `MODEL_ID`, `SERVED_NAME` | required model, `qwen38-uncensored` | HF model ID and OpenAI-visible model name |
| `SPEC`, `MAX_LEN` | `dflash2`, `262144` | Speculative decoding mode (`none`, `mtp`, `dflash2`, `dspark`) and context window |
| `MEM_FRAC`, `MAMBA_RATIO` | `0.85`, `4.59` | SGLang GPU memory fraction and Mamba ratio |
| `MODEL_STORAGE` | `ram` | `ram` / `ssd`; fails closed when RAM capacity cannot be verified |
| `MODEL_RAM_DIR`, `MODEL_SSD_DIR` | `/dev/shm/qwen38-hf`, `/workspace/hf` | Cache root for each storage mode |
| `MODEL_RAM_PEAK_FACTOR` | `2.5` | Verified finite RAM peak-admission factor |
| `MODEL_RAM_RELEASE_AFTER_LOAD` | `0` | Opt-in post-inference weight release; RAM mode only |
| `HF_TOKEN` | unset | Optional Hugging Face credential; related `HUGGING_FACE_HUB_TOKEN` is derived internally |
| `SERVE_WEBUI`, `ENABLE_SSH` | `1`, `0` | Enable Full UI and optional legacy OpenSSH debugging |
| `WEBUI_ADMIN_EMAIL`, `WEBUI_ADMIN_PASSWORD` | **required for Full** | Explicit pre-provisioned admin; password length >=16; otherwise UI does not start |
| `OPENWEBUI_VERSION` | `0.11.4` | OpenWebUI version installed in a separate venv |
| `WEBUI_SECRET_KEY` | random if unset | Optional stable WebUI session signing secret; handle as a secret |
| `WEBUI_DATA_DIR` | `/dev/shm/qwen38-webui-data` | WebUI DB/data root (tmpfs by default) |
| `RUNTIME_LOG_DIR` | `/dev/shm/qwen38-runtime` | Runtime scripts, traces and optional logs (tmpfs by default) |
| `ALLOW_PERSISTENT_RUNTIME_LOGS` | `0` | `1` explicitly permits a non-tmpfs runtime log directory; increases data exposure |
| `ALLOW_PERSISTENT_WEBUI_DATA` | `0` | `1` explicitly permits non-tmpfs UI data storage; increases data exposure |
| `QWEN38_WORKSPACE` | `/workspace` | Parent for isolated OpenWebUI Python virtualenv (not private user data) |
| `BENCHMARK`, `BENCHMARK_RUNS`, `BENCHMARK_MAX_TOKENS`, `BENCHMARK_TIMEOUT_SECONDS`, `BENCHMARK_REPORT_PATH` | `0`, `3`, `512`, `900`, Pod report path | Same in-Pod benchmark controls as above |
| `DEBUG`, `COLDSTART_TRACE` | `0`, `1` | Runtime logging and timing switches |
| `TS_VERSION` | `1.102.3` (pinned) | Alternative versions are **rejected** without code + test updates |
| `TS_SECRET_DIR` | `/dev/shm/qwen38-secrets` | Temporary Tailnet enrollment key file location (must stay on tmpfs) |
| `TS_RUNTIME_DIR` | helper fallback `/dev/shm/qwen38-tailscale` | Tailscale certificate/state/socket root; **bootstrap sets this under `RUNTIME_LOG_DIR/tailscale`** (must stay on tmpfs) |
| `TS_BIN_DIR` | `/tmp/qwen38-tailscale-bin` | Staging for **public, checksum-verified executable binaries**, not private credentials |

**Internal/generated variables are not configuration switches:** for example `BOOTSTRAP_B64`, `TAILSCALE_RUNTIME_B64`, `STORAGE_HELPER_B64`, `BENCHMARK_B64`, `QWEN38_STATE_DIR`, `MODEL_PATH`, `DRAFT_PATH` and the auto-populated `HF_*_CACHE` variables are passed/derived by the launcher or storage helper. Do not set them manually to bypass guardrails.

**CLI overrides (rather than ENV):** `qwen38fast [1h|4h] --gpu pro6000|b200|b300|5090 --spec dflash2|mtp|dspark|none --model REPO --max-len N --storage ram|ssd --ram-dir PATH --ssd-dir PATH --network runpod|tailnet --ts-hostname NAME --benchmark`. The currently supported checkpoint/quantization path is primarily tested with **RTX PRO 6000 Blackwell**, NVFP4 and DFlash2; other GPUs/settings need their own tests.

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
