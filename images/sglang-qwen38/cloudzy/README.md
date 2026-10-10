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

After the VM is online, and only with the new public IPv4:

    cd /Users/rentamac/.local/share/qwen38-cloudzy-builder-src
    bash images/sglang-qwen38/cloudzy/start-from-mac.sh NEW_PUBLIC_IPV4

Alternatively give the IP to the assistant and approve the same remote Mac mini command through SSH-MCP. This runs only on the named new VM, never on existing production VPS.

The launcher pins the current clean Git commit, rejects incorrect hardware/OS or a pre-existing builder, installs official Docker Engine and Buildx, runs offline source checks, constructs a dedicated Docker-container builder with a max of two concurrent BuildKit steps and a 48g memory cap, then triggers a detached systemd one-shot image build. There is no GHCR push, RunPod launch, or automatic VM deletion.

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
