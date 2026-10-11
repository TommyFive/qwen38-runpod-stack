<div align="center">

# Qwen3.8 RunPod Stack — enhanced fork

**Run Qwen3.8-27B NVFP4 + DFlash2 on RunPod with an OpenAI-compatible API, optional OpenWebUI, and a private Tailscale-only deployment.**

[![Release](https://img.shields.io/github/v/release/TommyFive/qwen38-runpod-stack)](https://github.com/TommyFive/qwen38-runpod-stack/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)
[![SGLang](https://img.shields.io/badge/engine-SGLang-purple)](https://github.com/sgl-project/sglang)
[![RunPod](https://img.shields.io/badge/platform-RunPod-blue)](https://www.runpod.io/)

</div>

> **Project origin:** This is the [TommyFive fork](https://github.com/TommyFive/qwen38-runpod-stack) of [nicremo/qwen38-runpod-stack](https://github.com/nicremo/qwen38-runpod-stack). Credit for the original GPU/agent workflow goes to the upstream project. This README describes **this fork's actual behavior**, including incompatible changes and security limitations; refer to [upstream's README](https://github.com/nicremo/qwen38-runpod-stack#readme) for the original design. Both use the repository's [MIT license](LICENSE). The fork is versioned independently; [v0.1.0](https://github.com/TommyFive/qwen38-runpod-stack/releases/tag/v0.1.0) was the first integrated release, [v0.2.0](https://github.com/TommyFive/qwen38-runpod-stack/releases/tag/v0.2.0) introduced the custom image, and [v0.2.1](https://github.com/TommyFive/qwen38-runpod-stack/releases/tag/v0.2.1) integrated the release deployment fixes.

## Choose your SGLang image: optimized custom or official upstream

This fork **builds and maintains its own optimized SGLang Docker image**
(`minimal-v1`) instead of merely configuring the standard upstream image.
The custom image is the **default** for new Qwen38 templates. Its source,
Docker build pin, release notes and measured GPU evidence are in this repository.

| SGLang Docker image | Compressed linux/amd64 size | Registry layers | Availability |
|---|---:|---:|---|
| [Official upstream](https://hub.docker.com/r/lmsysorg/sglang) — `lmsysorg/sglang:dev-qwen38-27b-dflash2` | **14.676 GB** | **68** | Public Docker Hub |
| **Our optimized minimal-v1** — `ghcr.io/tommyfive/qwen38-sglang:v0.2.0` | **12.907 GB** | **31** | **Public GHCR — verified anonymous access**, no GHCR login |
| **Difference** | **−1.769 GB (−12.1%)** | **−37 layers** | Same Qwen38 NVFP4 + DFlash2 serving goal |

*These are compressed registry-layer sizes, not host-disk usage. The original
14.676-GB measurement is rounded. A 12.1% smaller download **does not prove**
a 12.1% faster cold start. RunPod network and caching strongly affect startup.*

The optimized image was **actually tested on an RTX PRO 6000 Blackwell** with
NVFP4 + DFlash2 and authenticated inference. The Lean RAM-first configuration
also started successfully with a **20-GiB container disk**. The Full/OpenWebUI
and Tailnet modes *with this particular custom image*, standardized long-output
throughput, and a controlled fully uncached cold-start comparison are still
follow-up work. Optimization continues: the [layer audit](images/sglang-qwen38/LAYER_AUDIT_2026-10-11.md)
identified FlashInfer cubins/JIT caches as investigation targets, **not yet
safe-to-remove dependencies**. No additional performance or size gain is
claimed until measured.

**Public image available now:** The `v0.2.0` GHCR tag and GitHub
Release are published, and anonymous pull access to the exact **GPU-tested
SHA-256 manifest** was verified on **2026-10-11** with the
[anonymous manifest checker](images/sglang-qwen38/check-public.py)
(**31 layers, no GitHub login, PAT or RunPod registry secret**).
Anyone can use the custom image. The template helper independently checks
public access before creating new templates and attaches **no private GHCR
credentials**. Older owner templates with attached registry-auth IDs remain
compatible but are not portable to other RunPod accounts.

### Publish once, run without GHCR credentials

Both the **repository source** and **custom GHCR image** are now public.
GitHub package visibility was changed separately from repository access.
The exact tested image can be verified anonymously without downloading the
12.9 GB of registry layers:

```bash
python3 images/sglang-qwen38/check-public.py
# PUBLIC_IMAGE_VERIFIED: ... (31 layers); no login required.
```

**Any RunPod user** can create their own public-image templates with
`./create-templates.sh --image custom`. No personal `ghcr.io` registry
credential is needed. **Your application secrets remain separate**: each user
must configure their own RunPod API/SGLang credentials, and any required
Hugging Face / Tailnet secrets. Public Docker image access does **not**
publish or grant access to those credentials.

`create-templates.sh` checks the anonymous GHCR manifest first and fails
without creating templates if GitHub has not yet made the package Public.
Previously created templates in the owner's account remain unchanged and
may retain account-specific registry-auth IDs.

### One switch for the official upstream image

`./setup.sh` installs scripts only; it does not create templates or GPUs.
Select the image when creating **new** templates, then select the same image
when launching. Defaults are `custom`:

```bash
# Custom minimal-v1 (default): versioned templates, Lean 20 GiB
./create-templates.sh --image custom
qwen38pi --image custom
# Or Full: qwen38fast --image custom

# Official SGLang image: separate templates, Lean 150 GiB until validated
./create-templates.sh --image official
qwen38pi --image official
# Or Full: qwen38fast --image official
```

You can alternatively configure the selection for both commands once:

```bash
export QWEN38_IMAGE_VARIANT=official   # custom | official
./create-templates.sh
qwen38pi
```

**Separate templates avoid surprises:** Custom names start with
`qwen38-v0.2.0-`; upstream names start with `qwen38-official-`, each having
Full/Lean × Public/Tailnet variants. **No existing template is overwritten**.
The launcher verifies the selected template's immutable image reference,
secret reference and network mode before creating a chargeable Pod. Public
Custom image templates do **not** require private registry auth; legacy
owner templates with a registry-auth ID remain usable for backward compatibility. Explicit
`QWEN38_TEMPLATE*` IDs remain a manual override; unset those variables
to use automatic `--image` selection.

In the RunPod UI, **yes, the Docker image reference itself can be changed**,
but for CLI launches that is *not sufficient*: the launcher deliberately checks
the template's name/image combination and requires the matching variant.
Using the commands above is the supported, safer approach. For manual edits,
also check the image's public/private visibility, disk size, port exposure,
environment variables and entrypoint; changes affect only **new Pods**.

The custom templates pin the **immutable, GPU-tested digest** rather than
relying on a mutable tag:

`ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd`

The upstream `dev-qwen38-27b-dflash2` tag can change over time.
Custom Lean RAM-first uses **20 GiB SSD**, Custom Full **150 GiB**.
Both official-upstream template sizes conservatively default to **150 GiB**;
SSD model-storage mode also needs a larger disk than RAM-first Lean.

See [v0.2.0 image details](docs/releases/v0.2.0.md),
[latest project release](https://github.com/TommyFive/qwen38-runpod-stack/releases/tag/v0.2.1),
[measured build](images/sglang-qwen38/BUILD_RESULTS_2026-10-10.md) and
[live GPU report](images/sglang-qwen38/LIVE_TEST_RESULTS_2026-10-11.md).

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
| **Real RAM-only model downloads** | **Both the main model and DFlash2 draft are downloaded directly from Hugging Face into a RAM-backed `/dev/shm` cache**, not downloaded to SSD and copied afterward. Since the ~22.7 GiB model blobs do not occupy the container SSD, you can provision **significantly less disk** for a new Pod/template, subject to space needed by the Docker image, OpenWebUI installation and other runtime files. **Custom Lean now defaults to 20 GiB** (live-tested); Custom Full and both official upstream variants retain **150 GiB** by default. `MODEL_STORAGE=ssd` remains available as an opt-in fallback. |
| **Optional RAM reclaim** | Experimental post-inference checkpoint-blob release after authenticated model use; **off by default** and only allowed with RAM storage. |
| **Correct tokens/s measurement** | Both the in-Pod benchmark and external `qwen38bench` count **actual generated tokens** via SGLang `usage.completion_tokens`, not Server-Sent Events (SSE) chunks. An SSE chunk can contain multiple tokens or none. Standardized in-Pod workloads run only with `BENCHMARK=1`. |
| **Cold-start evidence** | Host/Pod UTC + monotonic events, `qwen38cold` reports and per-Pod datasets covering image pull, model download, GPU load/graphs, health readiness, cloud class and missing region/cache metadata. |
| **Port labels in RunPod templates** | **Public template ports now have descriptive labels in the RunPod Control UI**: `8000 → SGLang API`, `8080 → OpenWebUI` (Full), and `22 → SSH`. Both private Tailnet templates have **no published ports**, so port labels do not apply to them. |
| **RunPod CLI compatibility** | Detect whether the installed `runpodctl` actually supports a server-side termination flag instead of failing Pod creation on CLI versions that removed it. **No hard TTL guarantee** if the flag is absent; the old reaper remains account-wide. |
| **Four deployment templates** | Public Full/Lean and Private Full/Lean; helper scripts for safely repairing private port mappings and updating existing template helpers/secret references in place. |
| **Validation** | Real RTX PRO 6000 GPU tests for RAM/SSD, native SSH, positive/negative API auth, positive WebUI login, private HTTPS and DFlash2; offline GitHub Actions for integrity and benchmark regressions. |

**Why the Pod can use less SSD:** Model files are fetched from Hugging Face **straight into the RAM filesystem**; there is no initial SSD download followed by a copy to RAM. SGLang reads the model and draft weights from RAM and loads them into GPU VRAM. This avoids reserving disk space for roughly **22.7 GiB of downloaded weight blobs** in the tested configuration. **Docker layers, OpenWebUI and other runtime files still need container disk.** Current template defaults are **20 GiB for Custom Lean RAM-first** (GPU-tested) and **150 GiB for Custom Full and official-upstream templates**. These are template selections, not an automatic effect of `MODEL_STORAGE=ram`. Choose a smaller disk only after verifying enough capacity for the image and other files.

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
| **SSH access** | The SGLang image has no active `sshd`, so exposing SSH alone does not provide working login. | **Verified native Tailscale SSH** without a tun device; optional early OpenSSH provisioning for debugging (`ENABLE_SSH=1`). The upstream PR covers **debug OpenSSH**, not the fork's separate native Tailscale SSH integration. | [nicremo #5](https://github.com/nicremo/qwen38-runpod-stack/pull/5) · **closed, not merged** |
| **Full Pod startup / NCCL crash** | Installing OpenWebUI into the serving SGLang environment can mutate GPU dependencies while SGLang starts, triggering a `deep_ep.check_nccl_so()` / NCCL crash. | **Isolated OpenWebUI virtualenv** avoids replacing SGLang/PyTorch/NCCL dependencies; Full mode starts UI only after authenticated SGLang readiness. | [nicremo #4](https://github.com/nicremo/qwen38-runpod-stack/pull/4) · **open**; related [upstream issue #3](https://github.com/nicremo/qwen38-runpod-stack/issues/3) |
| **Tokens/s accounting** | Historical benchmark estimated generated tokens from SSE chunk counts, which may contain multiple tokens or none. | External and in-Pod benchmarks now use **`usage.completion_tokens`**; missing server usage is reported as unavailable instead of inventing numbers. | [nicremo #6](https://github.com/nicremo/qwen38-runpod-stack/pull/6) · **open** |
| WebUI start | Older SSH-assisted restart workflow. | WebUI is started on the Pod after authenticated SGLang readiness; no client-side SSH restart. | Related to [nicremo #4](https://github.com/nicremo/qwen38-runpod-stack/pull/4) · **open** |
| Storage / disk sizing | Model downloads/cache occupy disk. | Main and draft weights **download directly into `/dev/shm` RAM**, removing ~22.7 GiB of model weights from SSD requirements in the tested configuration; Custom Lean defaults to a GPU-tested 20 GiB container disk; Full and upstream remain at 150 GiB pending validation. | — |
| Privacy | Public RunPod service model | Authenticated public mode **or** Tailnet-only mode, with protected ephemeral runtime state and explicit logging switches. | — |
| Testing | Basic throughput tooling | Repeatable in-Pod benchmark, cold-start tracing, security/storage regression tests. | — |
| **RunPod CLI timer compatibility** | A wrapper can pass `--terminate-after` even on CLI versions that no longer support it, preventing Pod creation. | Detect supported timer flags before use; start commands remain compatible with newer CLI versions. **If unsupported, this is not a guaranteed auto-shutdown.** | [nicremo #2](https://github.com/nicremo/qwen38-runpod-stack/pull/2) · **open** |
| Rental duration / cleanup | Historical automatic-shutdown assumptions | A `1h` / `4h` argument is **not** a guaranteed TTL or cost cap. Existing stop/reaper remain account-wide; terminate the **exact Pod ID** instead. | Related to [nicremo #2](https://github.com/nicremo/qwen38-runpod-stack/pull/2) · **open**; project-scoped cleanup remains separate follow-up |

**Upstream PR status checked 2026-10-11:** #1, #2, #4 and **#6** were open; #5 was closed **without merging**. These are not the fork's integration PR numbers. Their status may change independently. The fork **does not automatically inherit upstream changes**, and attribution/history do not require copying the upstream README verbatim.

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
| `LLM_API_KEY` **or existing** `LLAMA_API_KEY` | Required SGLang Bearer key stored in a RunPod Secret; select an existing name via `QWEN38_API_SECRET_NAME` when creating templates |
| `TS_AUTHKEY` | **Required for private mode**; tagged/ephemeral Tailscale enrollment |
| `HF_TOKEN` | Optional for Hugging Face downloads; omit if the model is public and not needed |

**API key naming (only this Qwen38 repository):** The engine still expects `SGLANG_API_KEY` and the HTTP API still requires `Authorization: Bearer <key>`. Newly created templates default to a RunPod Secret called `LLM_API_KEY`, **but you do not need to create or duplicate it** if you already use `LLAMA_API_KEY`: select your existing name with `QWEN38_API_SECRET_NAME=LLAMA_API_KEY ./create-templates.sh --image official` (or `custom`). For automatically selected templates, `qwen38fast` reads the already configured **Secret reference name**, not the secret value, and forwards the same reference. The four deployed v0.2.0 custom templates already reference `LLAMA_API_KEY`. Your local proxy must still have the matching Bearer key; no engine or A40 project changes are involved. See [Secret name migration](docs/SECURITY.md#api-secret-name-migration).

Create the **four templates for your chosen image** once. New templates never overwrite old ones, and creating them does not start a paid GPU. The already deployed custom v0.2.0 templates need not be recreated. For a new official-upstream family using your existing API Secret:

```bash
QWEN38_API_SECRET_NAME=LLAMA_API_KEY ./create-templates.sh --image official
qwen38pi --image official
# Optional Tailnet mode: qwen38pi --image official --network tailnet
```

For the already created custom family, simply use `qwen38pi` or
`qwen38fast`, or pass `--image custom` explicitly. No template IDs need
to be exported for the normal automatic selection. Export
`QWEN38_TAILNET_DOMAIN=your-tailnet.ts.net` only when Tailscale discovery
cannot determine it. **Manual** `QWEN38_TEMPLATE*` ID overrides are for
advanced use or rollback; unset them before switching image families.
Repeated template creation can create duplicate names, which the launcher
deliberately rejects, so create each family **once**. If updating existing
templates, use the controlled `scripts/sync-runpod-secrets.py` helper and
verify that private templates have **no published ports**. See [Security](docs/SECURITY.md).

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

**Important:** the local proxy reads `~/.runpod/qwen38.key`. It must contain the **same value** as the selected RunPod API Secret (`LLM_API_KEY` by default, `LLAMA_API_KEY` with the legacy override). The default RunPod-secret mode does **not** automatically copy that secret to your Mac. Optionally set `QWEN38_SGLANG_CLIENT_KEY_FILE` to a securely stored matching file for launcher readiness/TTFI probes. Never paste a live token into chat, Git, console logs or shell history.

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

**Authentication settings:** Pod variable `SGLANG_API_KEY` (new RunPod Secret `LLM_API_KEY`, or legacy `LLAMA_API_KEY` when explicitly selected) is mandatory. Private templates additionally require `TS_AUTHKEY` (RunPod Secret); Full templates require `WEBUI_ADMIN_EMAIL` and a strong `WEBUI_ADMIN_PASSWORD` (minimum 16 characters). Do **not** store real credentials in Git.

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
