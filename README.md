<div align="center">

# qwen38-runpod-stack

**One command spins up Qwen3.8-27B (abliterated, NVFP4) on a rented Blackwell GPU and wires it into your local coding agent.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Model: Apache 2.0](https://img.shields.io/badge/Model-Apache%202.0-blue.svg)](https://huggingface.co/Qwen/Qwen3.8-27B)
[![Shell](https://img.shields.io/badge/shell-bash-121011?logo=gnu-bash&logoColor=white)](bin/)
[![Python](https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white)](bin/qwen38-proxy)
[![Platform](https://img.shields.io/badge/platform-macOS-000000?logo=apple&logoColor=white)](#requirements)
[![Engine: SGLang](https://img.shields.io/badge/engine-SGLang-6f42c1)](https://github.com/sgl-project/sglang)
[![GPU: RTX PRO 6000](https://img.shields.io/badge/GPU-RTX%20PRO%206000-76b900?logo=nvidia&logoColor=white)](https://www.runpod.io/gpu-models/rtx-pro-6000)
[![~150 tok/s](https://img.shields.io/badge/measured-~150%20tok%2Fs-brightgreen)](docs/PERFORMANCE.md)

</div>

---

A rented Blackwell GPU is cheaper than a hosted uncensored API once you actually
use it, and it is roughly ten times faster than the same model on a laptop. This
repo makes that a single command: it starts the pod, serves the model over an
OpenAI-compatible API, and gives your coding agent a **fixed local URL** that
always points at whatever pod is currently running. **Cost-control limitation:** stop/reaper currently operate on all pods in the
RunPod account. The owner explicitly limits this account to QWEN38-only pods;
that assumption is essential. The legacy reaper is not active on the audited
headless Mac mini, and no reliable automatic TTL is guaranteed with the
installed RunPod CLI. See [Cost control](#cost-control) and [#22](https://github.com/TommyFive/qwen38-runpod-stack/issues/22).

Measured on 2026-08-23: **~150 tok/s** on an RTX PRO 6000 with SGLang plus
DFlash2 speculative decoding, single stream, 262K context. See
[docs/PERFORMANCE.md](docs/PERFORMANCE.md).

## Table of contents

- [Why](#why)
- [How it fits together](#how-it-fits-together)
- [What's inside](#whats-inside)
- [Requirements](#requirements)
- [Install](#install)
- [Usage](#usage)
- [Cost control](#cost-control)
- [Security](#security)
- [The model](#the-model)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Why

Three separate worlds exist and nobody connects them: run an uncensored model
locally (slow), rent a GPU to host a model (no privacy story, fiddly), and plug a
local model into a coding agent (usually a censored model). This stack does all
three with an abliterated model, and it does the math on when renting beats a
hosted API.

| Where | Speed (Qwen3.8-27B, Q4/NVFP4) | Notes |
|---|---|---|
| MacBook Pro M2 Max 32GB | ~14 tok/s | free, private, but slow for an agent |
| 16GB gaming GPU | ~3 tok/s | technically runs, unusable for agents |
| **RunPod RTX PRO 6000 (this repo)** | **~150 tok/s** | SGLang + NVFP4 + DFlash2 |
| Hosted uncensored API | ~35 tok/s | convenient, more expensive at volume |

## How it fits together

```
  pi / any OpenAI-compatible agent
              │
              ▼
   http://127.0.0.1:8388/v1      ← fixed local address, never changes
              │
      qwen38-proxy  (LaunchAgent)
              │  reads ~/.runpod/current-pod, injects the API key
              ▼
   https://<pod-id>-8000.proxy.runpod.net/v1   ← changes on every launch
              │
        SGLang on a RunPod Blackwell GPU
```

`qwen38fast` / `qwen38pi` writes the running pod's id to `~/.runpod/current-pod`.
The proxy reads it, so your agent config points at `127.0.0.1:8388` once and
never has to change, even though the pod URL is different every time. No pod
running → the proxy returns a clean 503 telling you to start one.

## What's inside

| File | Purpose |
|---|---|
| `bin/qwen38fast` | Full stack: SGLang API **plus** OpenWebUI (port 8080). Starts and waits until usable |
| `bin/qwen38pi` | Lean: SGLang API only, for a coding agent. No OpenWebUI, ready sooner |
| `bin/qwen38bench` | Measures decode rate, TTFT and accepted-token length (discards a warmup run) |
| `bin/qwen38-proxy` | Local proxy on `127.0.0.1:8388` that always targets the running pod |
| `bin/rp` | `runpodctl` wrapper that requests a server timer only when the CLI supports one; not a guaranteed TTL |
| `bin/runpod-reaper` | **Legacy account-wide** 1h cleanup; disabled on audited Mac mini; use only in QWEN38-only accounts |
| `scripts/bootstrap-sglang-openwebui.sh` | Runs inside the pod: downloads weights, starts SGLang (optionally OpenWebUI) |
| `launchagents/*.template` | macOS LaunchAgents for proxy and reaper; `__HOME__` is filled in at setup |
| `pi/models.runpod.json` | The provider block for `~/.pi/agent/models.json` |
| `create-templates.sh` | Creates four RunPod templates (public/private × Full/Lean); existing IDs can be refreshed in place |
| `setup.sh` | Installs everything for the current user |

## Requirements

- [`runpodctl`](https://github.com/runpod/runpodctl) installed and logged in
- A Hugging Face token in `~/.cache/huggingface/token` (the default model is not
  gated, but a token gives faster, rate-limit-free downloads)
- The RunPod SSH key in `~/.runpod/ssh/runpodctl-ssh-key` (only needed for the
  OpenWebUI restart in the full stack)
- Python 3, `base64`, `curl`
- For the agent path: [pi](https://pi.dev) (or any OpenAI-compatible agent)
- macOS for the LaunchAgents (the scripts themselves are portable)

## Install

```bash
git clone https://github.com/nicremo/qwen38-runpod-stack.git
cd qwen38-runpod-stack

./setup.sh                       # bin → ~/.local/bin, load LaunchAgents
./create-templates.sh            # create the RunPod templates, prints two ids
export QWEN38_TEMPLATE=<id>       # the full-stack id
export QWEN38_TEMPLATE_PI=<id>    # the pi id
# copy the block from pi/models.runpod.json into ~/.pi/agent/models.json
```

You can also hardcode the template ids in `bin/qwen38fast` instead of exporting
the env vars.

**Bootstrap changes:** `./setup.sh` copies this checkout's bootstrap to
`~/.local/share/qwen38-runpod-stack/`, which `qwen38fast` uses when creating
new pods. Set `QWEN38_BOOTSTRAP=/path/to/bootstrap-sglang-openwebui.sh` to test
an uninstalled working-tree version. For deployments launched from the RunPod
web UI, run `./create-templates.sh` again and use the newly printed template IDs:
existing RunPod templates retain their embedded bootstrap code.

**Dependency isolation:** On full-stack deployments, OpenWebUI is installed
into its own virtual environment (`/workspace/openwebui-venv`) using the `uv`
bundled in the SGLang image. It defaults to OpenWebUI `0.11.4`; set
`OPENWEBUI_VERSION` at pod creation to select a different version. SGLang's
Python/PyTorch/NCCL environment is not modified by the bootstrap. Installing
OpenWebUI into the serving environment while SGLang starts can replace NCCL
libraries and crash DeepEP's startup check.

## Usage

Lean path for a coding agent:

```bash
qwen38pi                                 # starts, ready as soon as the API answers
pi --model runpod/qwen38-uncensored      # work with it
qwen38pi stop                            # shut the pod down
```

With a web UI (OpenWebUI, opens in your browser):

```bash
qwen38fast                               # starts, opens OpenWebUI
qwen38fast status                        # what's running, what it costs
qwen38fast stop
```

### Optional Tailscale: native SSH and private network mode

Tailscale is **completely optional**: when `TS_AUTHKEY` is unset or empty,
the normal RunPod HTTP proxy workflow remains unchanged. The new runtime is
tested against a real RunPod SGLang container without `/dev/net/tun` or
`CAP_NET_ADMIN`. It runs `tailscaled --tun=userspace-networking --state=mem:`
and enables **native Tailscale SSH** through `tailscale up --ssh`; it never
forwards TCP port 22 through Tailscale Serve.

Configuration (pod environment or variables exported before `qwen38fast`):

| Variable | Default | Purpose |
|---|---|---|
| `TS_AUTHKEY` | empty | Optional Tailscale enrollment; only a nonempty key activates it. Use a short-lived, scoped, one-time auth key. |
| `TS_HOSTNAME` | container-derived | Lowercase MagicDNS DNS-label name (1–63 characters). |
| `TS_ENABLE_SSH` | `1` | Native Tailscale SSH (`0` disables). Tailnet SSH ACL/grants still decide access. |
| `QWEN38_NETWORK_MODE` | `runpod` | Launcher mode: `runpod` keeps public RunPod endpoints; `tailnet` uses tailnet-only templates. The matching pod-side env is `NETWORK_MODE`. |
| `QWEN38_TAILNET_DOMAIN` | discovered if a local Tailscale CLI is connected | Required tailnet DNS suffix (e.g. `tailc8dece.ts.net`) when discovery is unavailable. Never infer it from a random host. |
| `QWEN38_TEMPLATE_TAILNET` / `QWEN38_TEMPLATE_TAILNET_PI` | unset | Required RunPod template IDs for private, portless runs. Create both with `./create-templates.sh`. |

`./create-templates.sh` now generates **four** templates: legacy full/lean
(published RunPod ports) plus private full/lean (**no published RunPod ports**).
Verify that the new tailnet templates have no published ports using
`runpodctl template get <id>` before launching a private pod. The launcher
additionally passes `--ssh=false` for private pods so RunPod does not turn on
its own publicly mapped SSH service. Keep all **public** template IDs distinct:
using a public template with `NETWORK_MODE=tailnet` is not secure.

Typical launch on a local machine with Tailscale already connected:

```bash
./setup.sh
./create-templates.sh
# export the generated four template IDs (displayed by create-templates.sh)
# Enter an auth key securely without saving it in shell history:
read -r -s TS_AUTHKEY; export TS_AUTHKEY
QWEN38_NETWORK_MODE=tailnet qwen38pi
unset TS_AUTHKEY
```

The launcher chooses a collision-resistant `TS_HOSTNAME` if one is not
provided. The local proxy transparently targets the corresponding HTTPS
Tailscale Serve API at `https://<hostname>.<tailnet-domain>/v1`. The optional
OpenWebUI is served at `https://<hostname>.<tailnet-domain>:8443`. These
URLs are reachable only from devices authorized by your Tailscale network
policy; **Tailscale HTTPS certificates and Serve permission must be enabled**
for the relevant tailnet. OpenWebUI starts only after the SGLang API becomes
ready, eliminating the former client-side SSH restart.

`TS_AUTHKEY` is copied to a root-only 0600 file in `/dev/shm` (verified
tmpfs), passed to `tailscale up` via `--auth-key=file:...`, and deleted
immediately after enrollment. Tailscale state stays in RAM and is lost at pod
termination. The static Tailscale version is pinned to 1.102.3 and its
download is SHA-256 checked against the publisher checksum.

**Security limitations:** RunPod may retain environment variables; the
existing `runpodctl --env` API transmits both `TS_AUTHKEY` and
`SGLANG_API_KEY` in the CLI argument list and RunPod control plane.
Do not consider this zero-trace secret delivery or full data privacy; the
broader secret handling and OpenWebUI authentication hardening are tracked in
[issue #8](https://github.com/TommyFive/qwen38-runpod-stack/issues/8).
**Current integration runtime** requires OpenWebUI authentication and disables
anonymous signup; negative anonymous access checks passed on the live Private
Full pod. Tailnet HTTPS Serve 443/8443 is still **unreachable** in that cohort
([#20](https://github.com/TommyFive/qwen38-runpod-stack/issues/20)); do not
present this path as working until TLS/API/UI checks pass.

**Fail-closed behavior:** An empty/invalid token or failed Tailscale/Serve
setup in `tailnet` mode aborts the pod bootstrap before model download.
The `runpod` mode continues its pre-existing serving path when optional
Tailscale fails. No production VPS or permanent host network settings are
modified during installation.

### Debug SSH (off by default)

SSH is disabled by default, including in newly created templates. This keeps the
debugging service off unless it is explicitly required. To enable it for one new
pod, use:

```bash
QWEN38_ENABLE_SSH=1 qwen38fast
```

The launcher passes this through as `ENABLE_SSH=1`; the bootstrap then installs
and starts `sshd` before model downloads. Your RunPod account must have its SSH
key registered. Leave the variable unset for normal launches.

Measure the real decode rate:

```bash
qwen38bench                              # picks the running pod, 5 runs + warmup
```

## Cost control

**Accepted single-project limitation for PR #17 (2026-10-10):** the RunPod
account is currently used **exclusively for QWEN38 project pods**. With this
assumption, the existing account-wide `qwen38fast stop` /
`qwen38pi stop` behavior is accepted as a temporary limitation. **These
commands list and delete every visible pod in the RunPod account**, not only
the pod created by the current invocation. They are unsafe in a mixed-use
account. Do **not** add unrelated workloads without first fixing
[#18](https://github.com/TommyFive/qwen38-runpod-stack/issues/18); the
accepted risk is recorded in
[#22](https://github.com/TommyFive/qwen38-runpod-stack/issues/22).

The existing `runpod-reaper` also operates **account-wide**, using a
global default 1h age threshold with a `keep-` name exemption; it does not
enforce requested per-pod durations such as `qwen38fast 4h`. The legacy
reaper LaunchAgent was **not installed** on the headless Mac mini during the
2026-10-10 audit, but **`./setup.sh` installs/loads it**; account scope and
activation must be considered before running setup. The installed
`runpodctl 2.15.0` has no `--terminate-after` option. Neither `rp` nor
the absent reaper currently guarantees an automatic shutdown after the
requested rental window.

For paid tests, record the exact Pod ID, actively monitor the RunPod
billing rate, and terminate the **specific Pod ID** using
`runpodctl pod delete <exact-pod-id>` or the RunPod dashboard. A nominal
`2h`/`4h` argument is **not a hard cost ceiling**. Keep the global reaper
disabled for supervised integration testing. Implementing a correctly
scoped per-pod TTL is **post-merge**, not a PR #17 merge blocker.

Full details: [docs/COST_CONTROL.md](docs/COST_CONTROL.md).


## Security

- **No keys, no tokens, no personal paths in this repo.** `qwen38fast` generates
  the API key locally and hands it to SGLang, so the publicly reachable pod port
  isn't open to the internet.
- `.gitignore` keeps keys, tokens and pod state out.
- The proxy binds to `127.0.0.1` only.

> The default model has its safety alignment removed. It is intended for
> research, red-teaming and your own responsible use. What you do with it is on you.

## The model

Default is `sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4`, a uniform
`nvfp4-pack-quantized` checkpoint. Point at another with `--model` or the
`QWEN38_MODEL` variable.

**Important:** not every NVFP4 checkpoint works with SGLang. A `mixed-precision`
compressed-tensors checkpoint loads **silently unquantized** in SGLang
([sgl-project/sglang#32736](https://github.com/sgl-project/sglang/issues/32736)),
which throws away the whole FP4 speedup without any error. Use a uniform
`nvfp4-pack-quantized` build. The reasoning behind every choice is in
[docs/PERFORMANCE.md](docs/PERFORMANCE.md).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Pod URL returns 404 | port not exposed at creation | expose `8000`/`8080` when the pod is created, never edit a running pod |
| Model runs but is slow like BF16 | `mixed-precision` checkpoint in SGLang | use a `nvfp4-pack-quantized` build |
| Endless thinking, no answer | `reasoning_effort` defaults high | pass `enable_thinking: false` or a lower effort |
| HTTP 403 from the pod URL | RunPod proxy rejects the default urllib UA | send a browser User-Agent (the proxy already does) |
| Editing a running pod wiped the model | RunPod recreates the container | put models on the `/workspace` volume, or expose ports at creation |
| SGLang crashes in `deep_ep.check_nccl_so()` with `(deleted)` | concurrent pip install into SGLang Python environment | redeploy with isolated OpenWebUI environment; do not disable NCCL checks |

## License

MIT, see [LICENSE](LICENSE). The model itself is Apache 2.0.

## Integrated pre-release branch — #7, #8, #9, #10, #11 (2026-10-10)

A common integration branch, `integration/issues-7-11-20261010`,
consolidates feature PRs **#12–#16** (now closed as superseded by PR #17).
PR #19's optional automatic post-load RAM release is also merged into this
integration branch and defaults OFF.
It includes native **Tailscale SSH** and a private/portless tailnet path,
credentialed **SGLang/OpenWebUI** with private tmpfs runtime state, RAM-only
checkpoint and HF cache by default (explicit `--storage ssd` opt-in),
opt-in authenticated **in-pod benchmarking** (`--benchmark`), and
cold-start tracing/`qwen38cold` reporting.

See **[complete integration/test guide](docs/INTEGRATION_SMOKE_20261010.md)**
before renting a pod. Both GitHub Actions workflows passed at commit
`84672f280cdb7f23746b00199809c2059438e7b0`. Private Lean/Full GPU
smokes established real inference, RAM model+draft storage, optional automatic
22.731 GiB weight release and several negative API/UI auth checks, but
**Tailnet HTTPS Serve 443/8443 remains blocked by #20** and a positive HTTPS
OpenWebUI login has not passed. Public/SSD mode and the current templates need
appropriate release review. Running pods and embedded templates do **not**
update from Git commits; existing four template IDs can instead be refreshed
**in place** via the documented helper with explicit verification.

[PR #17 release strategy](docs/INTEGRATION_STRATEGY_PR17_20261010.md)
separates mandatory functional/security acceptance from **accepted non-blocking**
RunPod account-wide cleanup ([#22](https://github.com/TommyFive/qwen38-runpod-stack/issues/22),
engineering follow-up #18) and further cold-start/observability optimization
([#23](https://github.com/TommyFive/qwen38-runpod-stack/issues/23),
related #5/#6/#11). This branch is not merged into `main`.

Detailed explanations: [Tailscale setup above](#optional-tailscale-native-ssh-and-private-network-mode),
[privacy and threat model](docs/SECURITY.md),
[RAM/SSD storage](docs/INTEGRATION_SMOKE_20261010.md),
[benchmark metrics](docs/BENCHMARK.md),
[cold-start methodology](docs/COLD_START.md).


### RunPod Secrets as default (integration branch)

`qwen38fast` uses RunPod Secret references by default: `SGLANG_API_KEY`
references existing `LLAMA_API_KEY`; private `TS_AUTHKEY` references
`TS_AUTHKEY`. `HF_TOKEN` references the existing RunPod Secret `HF_TOKEN`
by default. Set `QWEN38_HF_SECRET_NAME` to override its name, or explicitly
set it to an empty string to omit an optional Hugging Face token. For previous local-secret behavior,
set `QWEN38_CREDENTIAL_MODE=local`. The local Qwen38 proxy requires the
**same** SGLang API key as the RunPod `LLAMA_API_KEY` Secret;
see [security and setup notes](docs/SECURITY.md).

Existing template IDs can be updated in place using
`scripts/sync-runpod-secrets.py` (see [security guide](docs/SECURITY.md)).

For existing templates, refresh bundled bootstrap/Tailscale/storage/benchmark
script bytes in place (no new IDs) by adding `--refresh-helpers` to
`scripts/sync-runpod-secrets.py`. For RAM-only mode, cgroup v1 and v2 are
supported only with a verified finite limit; unavailable memory accounting
still fails closed.
