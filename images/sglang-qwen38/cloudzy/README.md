# One-time Cloudzy CPU image build

**Prepared only:** These files do not deploy, purchase, power on, delete, or alter any cloud server. The user clicks Deploy Now separately in Cloudzy and supplies the resulting new public IPv4.

## Cloudzy selection

- Region: Los Angeles, because that is where the 64GB SKU is available.
- Regular CPU: 16 vCPU, 64GB RAM, approximately 1500GB NVMe (verify final order).
- Ubuntu Server 24.04 LTS, hourly billing, quantity 1.
- Add the existing Mac mini public Ed25519 SSH key to the Cloudzy SSH Keys section. Never provide the private key.
- No optional paid panels or backups. Confirm final price before clicking Deploy.
- This workflow assumes ordinary SSH on port 22 and root key authentication.
- Cloudzy user-data is not confirmed in the shown UI, so this flow deliberately works without it and does not need a provider API token.

## Single command after paid VPS creation

On the Mac mini, the prepared checkout path is:

    /Users/rentamac/.local/share/qwen38-cloudzy-builder-src

After the VM is online, and only with the new public IPv4
(the launcher asynchronously schedules the bootstrap and returns promptly):

    cd /Users/rentamac/.local/share/qwen38-cloudzy-builder-src
    bash images/sglang-qwen38/cloudzy/start-from-mac.sh NEW_PUBLIC_IPV4

Alternatively give the IP to the assistant and approve the same remote Mac mini command through SSH-MCP. This runs only on the named new VM, never on existing production VPS.

The launcher pins the current clean Git commit, saves the target after a successful SSH preflight, and schedules a detached bootstrap service. The bootstrap rejects incorrect hardware/OS or a pre-existing builder, installs official Docker Engine and Buildx, runs offline source checks, constructs a dedicated Docker-container builder with a max of two concurrent BuildKit steps and a 48g memory cap, then triggers a detached systemd one-shot image build. There is no GHCR push, RunPod launch, or automatic VM deletion.

## Permanent ChatGPT access through Mac mini (required design)

The starting script `start-from-mac.sh NEW_PUBLIC_IPV4` now makes a
**read-only SSH preflight**, pins the new SSH host key in a dedicated
`known_hosts` file, and saves the VPS IP + immutable source SHA in a
private local directory:

    /Users/rentamac/.local/state/qwen38-cloudzy-builder/current-ip
    /Users/rentamac/.local/state/qwen38-cloudzy-builder/current-sha
    /Users/rentamac/.local/state/qwen38-cloudzy-builder/known_hosts

These files have restricted 0600/0700 permissions; they contain no password
or private key. The Ed25519 **private** key stays in Mac mini's existing
`~/.ssh/id_ed25519`. First connection uses SSH trust-on-first-use:
**verify the printed SHA256 host-key fingerprint with the Cloudzy console
whenever possible.** Later connections use `StrictHostKeyChecking=yes`;
an unexpected SSH host key change fails closed.

**The bootstrap itself is now launched as a detached systemd unit**
`qwen38-cloudzy-bootstrap`, so installing Docker and preparing the builder
does not depend on a live SSH-MCP terminal session. On success the bootstrap
starts `qwen38-cloudzy-image` as another independent systemd service.

ChatGPT, in any later conversation with SSH-MCP access, can run the
following on the existing `mac-mini-admin` profile, without requesting
the IP again, opening a persistent PTY, or installing a new SSH-MCP profile:

    bash /Users/rentamac/.local/share/qwen38-cloudzy-builder-src/images/sglang-qwen38/cloudzy/monitor-from-mac.sh status
    bash /Users/rentamac/.local/share/qwen38-cloudzy-builder-src/images/sglang-qwen38/cloudzy/monitor-from-mac.sh resources
    bash /Users/rentamac/.local/share/qwen38-cloudzy-builder-src/images/sglang-qwen38/cloudzy/monitor-from-mac.sh errors
    bash /Users/rentamac/.local/share/qwen38-cloudzy-builder-src/images/sglang-qwen38/cloudzy/monitor-from-mac.sh logs
    bash /Users/rentamac/.local/share/qwen38-cloudzy-builder-src/images/sglang-qwen38/cloudzy/monitor-from-mac.sh bootstrap
    bash /Users/rentamac/.local/share/qwen38-cloudzy-builder-src/images/sglang-qwen38/cloudzy/monitor-from-mac.sh docker

`status` combines systemd state, pinned commit, image exit code,
last RAM/SSD sample, current host resources and recent service journal.
`resources` reads the 12 latest 30-second resource samples,
`errors` extracts BuildKit/systemd/kernel errors,
`logs` shows the 65 latest BuildKit lines, `bootstrap` shows install
progress, and `docker` checks BuildKit/container storage.
All six are read-only on the VM. They reconnect using standard noninteractive
SSH to port 22 and are available after the original chat/browser closes,
**as long as the VM remains running and reachable and Mac mini/SSH-MCP
remains available**. This is on-demand monitoring, **not an autonomous
notification or scheduled background task**.

To make a private diagnostic copy on Mac mini before deleting the VM:

    bash /Users/rentamac/.local/share/qwen38-cloudzy-builder-src/images/sglang-qwen38/cloudzy/monitor-from-mac.sh archive

This writes a 0600 tarball under
`/Users/rentamac/.local/share/qwen38-cloudzy-builder-archives/`.
The full image itself **is not contained in this log archive**; it
must be separately published/exported with explicit approval.

If Cloudzy powers off, deletes or reprovisions the VPS, these commands
will fail with connection errors or a host-key mismatch as expected.
Never silently replace stored host keys when the IP is recycled.

## Logs, monitoring, results

On the new VPS:

- /var/log/qwen38-cloudzy/buildkit.log: full local BuildKit log.
- /var/log/qwen38-cloudzy/resource-samples.jsonl: 30-second RAM, SSD and BuildKit step snapshots, written to disk.
- /var/log/qwen38-cloudzy/exit-code.txt: build status (when process exits).
- /var/log/qwen38-cloudzy/image-tag.txt: local candidate tag.
- /var/log/qwen38-cloudzy/image-inspect.txt: built image ID/size if successful.
- /var/log/qwen38-cloudzy/image-history.txt: Docker layer history if successful.

Example one-time diagnostics:

    ssh -i ~/.ssh/id_ed25519 root@NEW_PUBLIC_IPV4 'systemctl show -p ActiveState -p SubState -p Result qwen38-cloudzy-image'
    ssh -i ~/.ssh/id_ed25519 root@NEW_PUBLIC_IPV4 'tail -n 3 /var/log/qwen38-cloudzy/resource-samples.jsonl'
    ssh -i ~/.ssh/id_ed25519 root@NEW_PUBLIC_IPV4 'tail -n 50 /var/log/qwen38-cloudzy/buildkit.log'

Guardrails: The service has a four-hour timeout, prevents duplicate first-run bootstrap, and aborts an isolated build process group on critical resource pressure. The Docker build is explicitly non-publishing.

**Do not delete the VPS until the image and diagnostic logs are saved externally.** No user API credentials, weights, RunPod auth, or GitHub secrets are copied to this VM. Cloudzy billing continues until the provider confirms deletion.

CI checks are offline; the actual VM provisioning and build remain untested until authorized cloud deployment.
