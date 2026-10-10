# Security and data privacy (#8)

## Public RunPod networking

RunPod proxy URLs \`https://<pod>-8000.proxy.runpod.net\` and
\`https://<pod>-8080.proxy.runpod.net\` are internet-reachable. They are
**not** protected merely by having an SSH key or by enabling Tailscale.
The SGLang API requires a nonempty \`SGLANG_API_KEY\` and preserves
\`--api-key\` authentication. OpenWebUI has \`WEBUI_AUTH=True\`,
\`ENABLE_SIGNUP=False\` and a pre-provisioned administrator. If either
\`WEBUI_ADMIN_EMAIL\` or \`WEBUI_ADMIN_PASSWORD\` is missing, the UI
does **not** start. Authentication must never be disabled for debugging.

RunPod templates created by \`create-templates.sh\` intentionally do **not**
persist an API token or admin password. When launching directly from
the RunPod web UI, supply \`SGLANG_API_KEY\` and (for UI use)
\`WEBUI_ADMIN_EMAIL\` / \`WEBUI_ADMIN_PASSWORD\` using RunPod's secret
injection controls. Otherwise startup fails closed for the API or
skips the UI. Template IDs embed the bootstrap; **recreate templates**
after an update. Existing running pods and old templates are NOT fixed by
a repository commit.

The integrated stack adds separate *portless* RunPod templates with Tailnet-only
Tailscale Serve and native Tailscale SSH. A Tailnet-only endpoint is not
equivalent to a public RunPod proxy. Tailnet privacy also depends on
Tailscale grants/ACLs and HTTPS Serve configuration. The combined integration branch preserves the original feature-PR histories;
real GPU/pod verification remains a release gate. Tailscale native SSH must not be confused with public
RunPod TCP/22 or an OpenSSH daemon.

## Ephemeral runtime

Default \`DEBUG=0\` emits phase/progress lines and an explicit allowlist
snapshot. Child request/server logs are discarded. New start scripts,
bootstrap.log, snapshot.json, optional debug logs and OpenWebUI conversation
database are under verified tmpfs (\`/dev/shm/qwen38-runtime\`,
\`/dev/shm/qwen38-webui-data\`). \`umask 077\` and mode 700 directories
keep other local users out. Tailscale userspace state, socket, helper binaries,
and optional benchmark logs also remain in private tmpfs.

**Model weights, the selected draft checkpoint and all Hugging Face/Xet
caches default to verified tmpfs** (\`MODEL_STORAGE=ram\`), with capacity
admission that fails closed before downloading if memory or tmpfs is insufficient.
Explicit `MODEL_STORAGE=ssd\` instead stores them in `/workspace/hf\`.
The isolated OpenWebUI **packages** remain under `/workspace\`
(distinct from conversation data).
The separate OpenWebUI virtualenv avoids changing SGLang/PyTorch/NCCL.

Set \`DEBUG=1\` or launcher \`QWEN38_DEBUG=1\` explicitly to retain
SGLang/OpenWebUI diagnostics in private tmpfs files. The redactor removes
known secrets and Bearer headers, but **cannot guarantee** every possible
application/third-party log line contains no personal information;
avoid debug when processing sensitive prompts. We deliberately do **not**
enable SGLang \`--log-requests\` or tracing. Persistent logs/data require
two explicit distinct opt-ins:
\`ALLOW_PERSISTENT_RUNTIME_LOGS=1\` with \`RUNTIME_LOG_DIR\` override, and
\`ALLOW_PERSISTENT_WEBUI_DATA=1\` with \`WEBUI_DATA_DIR\` override.
A tmpfs uses host RAM and has a capacity limit; size it for uploads and
conversations or avoid the UI.

## Credentials and limitations

\`HF_TOKEN\` is optional. For \`qwen38fast\`, an explicit exported
\`HF_TOKEN\` overrides \`~/.cache/huggingface/token\`; direct RunPod
template launches accept \`HF_TOKEN\` via template environment.
The HF credential is for downloads only and never replaces the
independent \`SGLANG_API_KEY\`. An HF token may help with gated
models/rate limits; it does **not** guarantee higher download bandwidth.

The launcher stores the generated API key at
\`~/.runpod/qwen38.key\` and its generated UI password at
\`~/.runpod/qwen38-webui-password\` (mode 0600). They are NEVER baked
into generated start scripts. RunPod's current CLI passes the full
\`--env\` JSON (including credentials) through **command-line arguments**
and the RunPod control plane. SGLang also requires its API key in
\`--api-key\` **process argv**; privileged pod users can inspect it.
We do not remove authentication to hide this limitation. On a rented
pod, the hosting platform and pod administrator can also inspect the
process environment, memory and file descriptors. tmpfs and RAM-only
weights are **not** end-to-end encryption.

The runtime redactor is defense-in-depth, not a mechanism to safely
enable prompt logging. Do not place production/sensitive content into
this stack without accepting the cloud trust boundary.

### RunPod Secret references (default since 2026-10-10)

The launcher defaults to `QWEN38_CREDENTIAL_MODE=runpod_secrets`, so the Pod
control plane receives **references**, never cleartext values, for:

- `SGLANG_API_KEY={{ RUNPOD_SECRET_LLAMA_API_KEY }}` (existing A40 secret, reused)
- `TS_AUTHKEY={{ RUNPOD_SECRET_TS_AUTHKEY }}` on tailnet pods only
- `HF_TOKEN={{ RUNPOD_SECRET_HF_TOKEN }}` by default, using the existing
  Hugging Face RunPod Secret named `HF_TOKEN`. The name is configurable with
  `QWEN38_HF_SECRET_NAME`; set it to an explicit empty string to omit a token
  for public models.

The same references are embedded as template defaults for RunPod UI launches.
The CLI supplies a complete `--env` override at pod creation, so it explicitly
recreates these references and does not rely on the template defaults.

`QWEN38_CREDENTIAL_MODE=local` is the legacy opt-in fallback, which loads
Tailscale/HF secrets from local environment/files and generates
`~/.runpod/qwen38.key`. **Do not export the old local secrets by default**; use
`source ~/.config/qwen38/templates.env` and source a Keychain loader only to
supply `RUNPOD_API_KEY` for CLI authentication if required.

**Local proxy caveat:** `qwen38-proxy` reads `~/.runpod/qwen38.key` to
send its Bearer token to SGLang. When the pod uses the existing RunPod
`LLAMA_API_KEY` Secret, that local file must contain **exactly the same
value** or authenticated calls through `127.0.0.1:8388` will fail.
RunPod Secrets do not offer automatic plaintext retrieval to the proxy;
no match can be inferred. Provision that value manually via the macOS
Keychain/local protected file if local proxy access is required.

RunPod REST omits `ports` in the JSON response for an empty port set.
The port hardener interprets **absent** as empty, but rejects explicit null,
malformed or nonempty lists, always PATCHes `{"ports":[]}` during repair,
and re-reads to verify. Do not launch private pods until live checks pass.

### Update the four existing RunPod templates without recreating them

After loading CLI credentials (needed only for the RunPod management API) and
sourcing `~/.config/qwen38/templates.env`, run:

```bash
cd ~/.openclaw/workspace/documentation/qwen38-runpod-stack
source ~/.config/qwen38/load-credentials.sh
source ~/.config/qwen38/templates.env
# The existing RunPod Hugging Face Secret HF_TOKEN is used automatically.
python3 scripts/sync-runpod-secrets.py \\
  --public-full "$QWEN38_TEMPLATE" \\
  --public-lean "$QWEN38_TEMPLATE_PI" \\
  --private-full "$QWEN38_TEMPLATE_TAILNET" \\
  --private-lean "$QWEN38_TEMPLATE_TAILNET_PI"
```

The operation reads and updates only the four named templates. It uses REST
`PATCH` with `env` updates, explicitly repairs private `ports: []`, and
re-reads persisted state. It does **not** create or start a GPU pod. If any
verification fails, stop and inspect the resulting template before use.
The existing IDs stay unchanged.
