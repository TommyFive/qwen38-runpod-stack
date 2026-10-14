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
| `QWEN38_TEMPLATE` | Discover matching `custom` or `official` Full/Public template | Explicit override to a different public Full template ID (rollback) |
| `QWEN38_TEMPLATE_PI` | Discover matching `custom` or `official` Lean/Public template | Explicit override to a different public Lean template ID |
| `QWEN38_TEMPLATE_TAILNET` | Discover matching image variant's private Full template | Override private Full ID, still subject to live portless verification |
| `QWEN38_TEMPLATE_TAILNET_PI` | Discover matching image variant's private Lean template | Override private Lean ID, still subject to live portless verification |
| `QWEN38_NETWORK_MODE` | `runpod` | `runpod` = public RunPod proxy; `tailnet` = private portless template |
| `QWEN38_TAILNET_DOMAIN` | detect from local Tailscale | Your `*.ts.net` tailnet DNS suffix; required if detection fails |
| `TS_HOSTNAME` | Selected RunPod template (generated default: `llm`) | Tailscale-only hostname (not the RunPod Pod name). CLI copies the selected template value into Pod ENV rather than generating/overriding it; Tailnet CLI launches require nonempty value. Concurrent Pods may receive a suffix. |
| `TS_ENABLE_SSH` | `1` | Enable **native** Tailscale SSH on a connected Pod; `0` disables |
| `TS_AUTHKEY` | unset | Used by the **opt-in local-credential** mode; default RunPod-secret mode references secret `TS_AUTHKEY` instead |
| `QWEN38_CREDENTIAL_MODE` | `runpod_secrets` | `runpod_secrets` (default) or `local`; legacy local mode exposes credentials to the RunPod CLI ENV call |
| `QWEN38_HF_SECRET_NAME` | `HF_TOKEN` | RunPod HF Secret name; set explicitly to empty to omit the reference |
| `QWEN38_API_SECRET_NAME` | Auto-selected release template's existing Secret reference name (when not explicitly set); otherwise `LLM_API_KEY` | The v0.2.0 launcher derives only the selected template's `SGLANG_API_KEY` **reference name** (for example `LLAMA_API_KEY`), never its value. Explicitly setting `QWEN38_API_SECRET_NAME` overrides that. When using explicitly selected older template IDs, the normal default remains `LLM_API_KEY`. |
| `QWEN38_SGLANG_CLIENT_KEY_FILE` | unset | Optional local matching SGLang API key file for launcher's positive readiness/inference probes |
| `QWEN38_WEBUI_ADMIN_EMAIL` | `admin@qwen38.example.com` | Pre-provisioned Full WebUI admin email |
| `QWEN38_WEBUI_ADMIN_PASSWORD` | generated protected file | Full WebUI admin password override; must be at least 16 characters |
| `HF_TOKEN` | unset (local mode) | Optional local Hugging Face token in `local` credential mode; file fallback `~/.cache/huggingface/token` |
| `RUNPOD_CLOUD` | `COMMUNITY` | First attempt to launch on Community; launcher tries Secure if Community creation fails |

### SGLang image selection, visibility and container disk

There are **two independently named template families**:

- `custom` (default): `qwen38-v0.2.0-{full|lean}-{public|tailnet}`.
  Uses the **public** custom minimal-v1 GHCR image; anonymous access to the
  GPU-tested manifest was verified on 2026-10-11. **No private registry auth** needed.
- `official`: `qwen38-official-{full|lean}-{public|tailnet}`.
  Uses the public upstream `lmsysorg/sglang:dev-qwen38-27b-dflash2` image,
  **without a private GHCR registry credential**.

```bash
./create-templates.sh --image custom   # default
./create-templates.sh --image official # different template names, does not overwrite custom
qwen38pi --image official              # select official image when launching
qwen38fast --image custom              # select the custom image, Full/OpenWebUI
```

Alternatively, set `QWEN38_IMAGE_VARIANT=official` (or `custom`)
for both commands. The legacy `QWEN38_IMAGE_REF` option remains supported
for the **two exact approved references only**; conflicting options fail.
Without `QWEN38_IMAGE_VARIANT`, a matching legacy reference selects the
corresponding template family. Changing only a custom template's image in
the RunPod UI does **not** update the CLI's protected template discovery:
select/create the corresponding family instead.

| Variable or option | Default | Meaning |
|---|---|---|
| `--image custom\|official` | `custom` | Command-line image selector for `create-templates.sh` and `qwen38fast`/`qwen38pi` |
| `QWEN38_IMAGE_VARIANT` | `custom` | Shell-level selector, same behavior as `--image` |
| `QWEN38_IMAGE_REF` | unset | Legacy explicit image reference: tested custom digest or exact upstream tag. Conflicting selectors rejected |
| `QWEN38_FULL_DISK_GB` | `20` RAM-first; `100` SSD mode | Full/OpenWebUI writable Container Disk for either image; **20 GiB Full is not yet live-validated** |
| `QWEN38_LEAN_DISK_GB` | `20` RAM-first; `100` SSD mode | Lean writable Container Disk for either image; **only Custom Lean at 20 GiB was GPU-tested** |
| `QWEN38_MODEL_STORAGE` | `ram` | RAM-first weights; **if changed to `ssd`, also increase Container Disk or attached SSD storage** (100 GiB default, >=50 GiB enforced) |

Custom is pinned to the immutable GPU-tested image:

`ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd`.

The human-readable alias `ghcr.io/tommyfive/qwen38-sglang:v0.2.0`
was successfully published after package **Manage Actions access** was
granted to the repository; all 31 compressed layers matched the tested image.
**GHCR package visibility is now Public**, independently of the GitHub source
repository and Actions permissions. Anonymous access to the exact tested
image manifest (31 layers) was verified on 2026-10-11 using
`images/sglang-qwen38/tools/check-public.py`. Each new Custom template creation
checks that same immutable digest and fails closed on registry errors.
Public image access **does not** expose or grant SGLang, HF or Tailscale
runtime secrets.
The custom image is 12.907 GB compressed versus 14.676 GB for upstream
(about 12.1% smaller). This does **not** establish a proportional cold-start
performance gain. Further FlashInfer kernel and cache optimization is being
evaluated, not yet shipped.

The launcher validates the exact image digest, selected network and template
name before creating a Pod. Newly created Custom templates **omit** private
GHCR registry-auth IDs; older owner templates with such IDs continue to work. An **explicit** `QWEN38_TEMPLATE*` ID
remains a manual override; when combining one with an explicit image selector,
the chosen image must match the template exactly or launch fails safely.
Unset manual ID overrides for normal automatic `--image` switching.
Private Tailnet templates always require zero public ports.

**Container Disk policy (for newly generated templates and new Pods):**
Full and Lean, both public/tailnet, both image variants use **20 GiB by
default** when main+draft weights download into RAM-backed `/dev/shm`.
Only Custom Lean has been live-tested with that 20-GiB setting so far.
Switching to `QWEN38_MODEL_STORAGE=ssd` or `--storage ssd` selects
**100 GiB** by default instead; an explicit disk override must be at least
**50 GiB** but this lower limit is not a tested recommendation.
In the RunPod UI changing an existing template's `MODEL_STORAGE` does
**not** resize Container Disk automatically — increase its disk or a
sufficiently sized mounted volume before starting a Pod. Pod storage
configuration changes do not retroactively resize running Pods.

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
| `TS_HOSTNAME`, `TS_ENABLE_SSH` | Selected template hostname (generated default: `llm`), `1` | CLI preserves template hostname in Pod ENV; no launcher hostname override |
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

**CLI overrides (rather than ENV):** `qwen38fast [1h|4h] --gpu pro6000|b200|b300|5090 --spec dflash2|mtp|dspark|none --model REPO --max-len N --storage ram|ssd --ram-dir PATH --ssd-dir PATH --network runpod|tailnet --benchmark`. The currently supported checkpoint/quantization path is primarily tested with **RTX PRO 6000 Blackwell**, NVFP4 and DFlash2; other GPUs/settings need their own tests.


## Source of truth

The code in [`bin/qwen38fast`](../bin/qwen38fast), [`create-templates.sh`](../create-templates.sh), [`scripts/bootstrap-sglang-openwebui.sh`](../scripts/bootstrap-sglang-openwebui.sh), [`scripts/model-storage.py`](../scripts/model-storage.py), and [`scripts/tailscale-runtime.sh`](../scripts/tailscale-runtime.sh) takes precedence over the documentation if a later release changes defaults. See [Security](SECURITY.md), [Benchmark](BENCHMARK.md) and [Cost Control](COST_CONTROL.md).
