# Qwen38 minimal-v2: independent post-VPS recovery runbook

**Status: storage verified; restored runtime **NOT YET** verified.** The disposable Aliyun ECS is shut down. This runbook requires a separately approved, disposable Linux AMD64 test host with sufficient storage; it is documentation only and **does not authorize** host changes, GPU spend, package visibility changes, production deployment or RunPod template changes.

Source of truth: [minimal-v2 checkpoint](MINIMAL_V2_CHECKPOINT_2026-10-12.md), [closed-loop GHCR upload proof](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38159273066), [GitHub release fallback](https://github.com/TommyFive/qwen38-runpod-stack/releases/tag/minimal-v2-cpu-checkpoint-20261012), [25/25 part validation log](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38158692348), and [remaining acceptance issue #46](https://github.com/TommyFive/qwen38-runpod-stack/issues/46).

## Primary: immutable GHCR manifests (no rebuild)

Both were published and remotely inspected on **2026-10-12, 01:43 China time**:

| Candidate | Pinned image reference | Status |
|---|---|---|
| A — remove Rust intermediates | `ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint@sha256:ec013c2e20528a92d61b6a7a0352ba081e166ef99025a5fbb4be06572381bb1e` | Remote manifest / tag verified |
| B — remove Rust intermediates + SHA-equal CUDA duplicate symlinks | `ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7` | Remote manifest / tag verified |

If the checkpoint package is private, authenticate with a narrowly scoped read-only GHCR credential; do not copy tokens into terminal history. Do not change visibility to recover the images. On an approved target, download by **digest**, not mutable tags. Use `docker image inspect`, `docker history`, a no-network CPU import smoke, exact runtime config comparison and symlink targets to establish actual image recoverability. **No full cold pull or runtime smoke is claimed by the original backup logs.**

The original `minimal-v2-rust*.oci.tar` archives consisted of oversized single filesystem layers. For GHCR upload they were repacked into multiple smaller OCI layers, preserving intended filesystem contents and relevant runtime config; the resulting `manifest`, layer digests, `rootfs.diff_ids`, and `history` necessarily differ. Their original TAR checksums **must not** match the GHCR manifest hashes.

## Secondary: complete GitHub release OCI-layout archives

If GHCR is unavailable, the release contains **all** 13 A parts + 12 B parts and the two checksum-manifest files (plus three encrypted raw-log archives). The GitHub Actions worker individually uploaded and compared each Release Asset's **server-provided SHA256** before reporting success.

- A: `release-rust.part-aa` through `release-rust.part-am`; `release-rust.parts.sha256` (13 SHA256 entries).
- B: `release-rust-cuda.part-aa` through `release-rust-cuda.part-al`; `release-rust-cuda.parts.sha256` (12 SHA256 entries).
- Release A stored part bytes: **11,842,600,960**; B: **10,703,779,840** (archive/TAR bytes, not OCI compressed layer descriptor sums).
- Release asset SHA256 for A checksum manifest: `101d0e21ab45a18a64cf330e5772ce9802b4e34a0f596bcbbcecf819d6d65cf9`.
- Release asset SHA256 for B checksum manifest: `99271b1e267d20c946a42a7a4fafac58a09df4cf5d2636feb0b65030a0eec8a3`.

On a **future explicitly approved** Linux host with `gh`, `sha256sum`, `tar` and `skopeo` available, a single shell can restore both layouts:

```bash
set -euo pipefail
REPO=TommyFive/qwen38-runpod-stack
RELEASE=minimal-v2-cpu-checkpoint-20261012
mkdir -p qwen38-checkpoint-recovery
cd qwen38-checkpoint-recovery

gh release download "$RELEASE" -R "$REPO" \
  --pattern 'release-rust.part-*' --pattern 'release-rust.parts.sha256' \
  --pattern 'release-rust-cuda.part-*' --pattern 'release-rust-cuda.parts.sha256'

# Verify 25 full part hashes before reconstructing either layout.
test "$(ls release-rust.part-?? | wc -l | tr -d ' ')" = 13
test "$(ls release-rust-cuda.part-?? | wc -l | tr -d ' ')" = 12
sha256sum -c release-rust.parts.sha256
sha256sum -c release-rust-cuda.parts.sha256

# Extract complete OCI layout archives; never substitute original TAR hashes here.
cat release-rust.part-?? | tar -xf -
cat release-rust-cuda.part-?? | tar -xf -
skopeo inspect --raw oci:oci-split-rust:checkpoint > recovered-A-manifest.json
skopeo inspect --raw oci:oci-split-rust-cuda:checkpoint > recovered-B-manifest.json
sha256sum recovered-A-manifest.json recovered-B-manifest.json
```

The last two manifest hashes are expected to match **the pinned GHCR digests above**, if both storage representations have exactly the same manifest bytes. That comparison is a **future validation step**; it was not performed by this runbook. Also run the committed `cpu-audit/verify-split-oci.py` only when the original single-layer TAR and split layout are both available. Verify the recovered layers' SHA256 descriptors and original intended OCI runtime metadata before treating either as a working image.

Storage for downloading both release layouts plus extracted layers can greatly exceed the ~22.5 GB of Release parts; preflight available space on the approved host.

## Private audit logs and decryption

The release also has three independent encrypted archives:

| Asset | Release SHA256 |
|---|---|
| `qwen38-checkpoint-logs.tar.gz.age` | `1b871fa4c2822fbf9a163ea8eb7378b7d594845fac6ded04649866ff85b18f1b` |
| `qwen38-checkpoint-after-split.tar.gz.age` | `f4417ae54b429706f52cd85b8905cd76c845e2adfc4bd635870a5833b987edd0` |
| `qwen38-original-v1-build-logs.tar.age` | `661ab22b77167df7f76a65461b2a7a0c9d4c73e50ab930f2b214232b77e9f1b3` |

Download only to a trusted host and decrypt with the matching **Mac mini SSH Ed25519 private key**, using `age -d -i ~/.ssh/id_ed25519`; never upload/print the private key or raw unredacted logs. Check the encrypted SHA256 first; only the first CPU raw-log archive has a separately documented unencrypted TAR checksum in the [checkpoint](MINIMAL_V2_CHECKPOINT_2026-10-12.md).

## Validation gates not fulfilled by storage backup

1. Fresh GHCR cold pull and OCI-runtime metadata comparison for both candidates on an approved host.
2. Final B image CPU import smokes (the B builder stage did pass; final B remains untested), target link integrity, A parity and exit-code proof.
3. Matched paid GPU RTX PRO 6000 Blackwell SM120 NVFP4 + DFlash2 runtime/security/performance tests.
4. Production promotion only after correctness and performance acceptance **and explicit separate owner approval**.

**Do not rerun the now-obsolete emergency GitHub Actions ECS-upload workflows.** Their historical success/failure logs and source remain recoverable in Git history. Only [issue #46](https://github.com/TommyFive/qwen38-runpod-stack/issues/46) authorizes tracking these deferred acceptance tasks; it does not itself approve infrastructure modifications.
