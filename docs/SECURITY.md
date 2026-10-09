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
keep other local users out. Model weights, HF cache and isolated OpenWebUI
**packages** remain under \`/workspace\` (distinct from conversations).
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
