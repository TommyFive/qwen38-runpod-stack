# Advanced environment variables — Qwen38 RunPod Stack

> **Advanced reference for this fork, based on `v0.2.0`.** For the short list of everyday settings, go back to the [README](../README.md#environment-variables).

## Where to configure variables

The most straightforward way to run a Pod is through the **RunPod Control UI**: open one of the four QWEN38 templates, edit its **environment variables**, save the template and deploy a **new Pod**. Template edits do **not** rewrite an existing running Pod. Keep the original public/private port distinction and the embedded launch/bootstrap payloads.

**Important difference for command-line users:** `qwen38fast` creates its own full `--env` JSON for a Pod. That overrides the template's environment object, so **changes to the template's ENV alone are not guaranteed to affect Pods launched through `qwen38fast`**. Configure the corresponding local `QWEN38_*` launcher variables when using the CLI.

Credentials should normally be supplied using RunPod Secret references (e.g. `{{ RUNPOD_SECRET_LLM_API_KEY }}`), not literal values in a public repository, shell-history command or shared diagnostics. A private template must publish **no public RunPod ports**; a mode switch by itself cannot undo published port mappings.

## Complete environment variable reference

This is the **configuration reference for external/user-configurable ENV switches implemented at `v0.2.0`**. There are two distinct layers:

- **Launcher ENV** is set on the local machine before `qwen38fast` / `qwen38pi`, typically with the `QWEN38_` prefix. The launcher assembles the entire RunPod ENV object; merely adding an arbitrary Pod variable to your local shell does **not** mean it is forwarded.
- **Pod ENV** is supplied directly through RunPod template/console or forwarded by the launcher. Variables with the same concept may have different names at these layers (for example `QWEN38_NETWORK_MODE` → `NETWORK_MODE`).

Defaults below are code defaults, not a guarantee that the live RunPod templates or local installation have been refreshed.

### Launcher: templates, connectivity and credentials

| Variable | Default | Meaning |
|---|---|---|
| `QWEN38_TEMPLATE` | Discover `qwen38-v0.2.0-full-public` | Explicit override to a different public Full template ID (rollback) |
| `QWEN38_TEMPLATE_PI` | Discover `qwen38-v0.2.0-lean-public` | Explicit override to a different public Lean template ID |
| `QWEN38_TEMPLATE_TAILNET` | Discover `qwen38-v0.2.0-full-tailnet` | Override private Full ID, still subject to live portless verification |
| `QWEN38_TEMPLATE_TAILNET_PI` | Discover `qwen38-v0.2.0-lean-tailnet` | Override private Lean ID, still subject to live portless verification |
| `QWEN38_NETWORK_MODE` | `runpod` | `runpod` = public RunPod proxy; `tailnet` = private portless template |
| `QWEN38_TAILNET_DOMAIN` | detect from local Tailscale | Your `*.ts.net` tailnet DNS suffix; required if detection fails |
| `TS_HOSTNAME` | generated random label | Optional explicit Tailnet/MagicDNS Pod hostname |
| `TS_ENABLE_SSH` | `1` | Enable **native** Tailscale SSH on a connected Pod; `0` disables |
| `TS_AUTHKEY` | unset | Used by the **opt-in local-credential** mode; default RunPod-secret mode references secret `TS_AUTHKEY` instead |
| `QWEN38_CREDENTIAL_MODE` | `runpod_secrets` | `runpod_secrets` (default) or `local`; legacy local mode exposes credentials to the RunPod CLI ENV call |
| `QWEN38_HF_SECRET_NAME` | `HF_TOKEN` | RunPod HF Secret name; set explicitly to empty to omit the reference |
| `QWEN38_API_SECRET_NAME` | `LLM_API_KEY` | Name of the existing RunPod Secret used for SGLang; `LLAMA_API_KEY` is an explicit legacy override until migration is completed. The CLI never reads the Secret's value. |
| `QWEN38_SGLANG_CLIENT_KEY_FILE` | unset | Optional local matching SGLang API key file for launcher's positive readiness/inference probes |
| `QWEN38_WEBUI_ADMIN_EMAIL` | `admin@qwen38.example.com` | Pre-provisioned Full WebUI admin email |
| `QWEN38_WEBUI_ADMIN_PASSWORD` | generated protected file | Full WebUI admin password override; must be at least 16 characters |
| `HF_TOKEN` | unset (local mode) | Optional local Hugging Face token in `local` credential mode; file fallback `~/.cache/huggingface/token` |
| `RUNPOD_CLOUD` | `COMMUNITY` | First attempt to launch on Community; launcher tries Secure if Community creation fails |

### Image and container disk (v0.2.0)

`./create-templates.sh` uses the **private**
`ghcr.io/tommyfive/qwen38-sglang:v0.2.0` image and resolves the RunPod
`ghcr.io` registry credential by ID. Image integrity is anchored to the
immutable `sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd`
digest recorded in `images/sglang-qwen38/release.json`.
A GitHub Release alone does not publish the GHCR image alias; verify the
`qwen38-image-release` workflow passed.

| Variable | Default | Meaning |
|---|---|---|
| `QWEN38_IMAGE_REF` | `ghcr.io/tommyfive/qwen38-sglang:v0.2.0` | Template creation image, with explicit original-upstream rollback |
| `QWEN38_FULL_DISK_GB` | `150` | Full/OpenWebUI writable SSD (conservative pending new-image Full test) |
| `QWEN38_LEAN_DISK_GB` | `20` | Lean writable SSD in RAM-first mode; auto-raises to 150 when selecting SSD model storage with the default |
| `QWEN38_MODEL_STORAGE` | `ram` | Checkpoint storage mode; RAM-first lean 20-GiB validated |

No existing RunPod templates are overwritten. Explicit template IDs preserve
legacy rollback. A new default launch refuses to proceed if the matching
v0.2.0 template is missing or has mismatched image/auth/network metadata.

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
| `SGLANG_API_KEY` | **required** | Engine-specific Pod variable for SGLang Bearer authentication; new Qwen38 template references RunPod Secret `LLM_API_KEY` (legacy selector: `LLAMA_API_KEY`) |
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


## Source of truth

The code in [`bin/qwen38fast`](../bin/qwen38fast), [`create-templates.sh`](../create-templates.sh), [`scripts/bootstrap-sglang-openwebui.sh`](../scripts/bootstrap-sglang-openwebui.sh), [`scripts/model-storage.py`](../scripts/model-storage.py), and [`scripts/tailscale-runtime.sh`](../scripts/tailscale-runtime.sh) takes precedence over the documentation if a later release changes defaults. See [Security](SECURITY.md), [Benchmark](BENCHMARK.md) and [Cost Control](COST_CONTROL.md).
