# Emergency checkpoint — Qwen38 SGLang minimal-v2 CPU candidates

Date: **2026-10-12 China time**. This is a **pre-GPU** CPU-only checkpoint. The temporary Alibaba ECS `root@8.211.52.85` is scheduled to be **released around 03:25 China time**. Do not rely on local ECS files past that deadline.

## 1. Project and acceptance requirements

- GitHub: `TommyFive/qwen38-runpod-stack`; work branch `research/minimal-v2-kernel-audit`, draft PR [#42](https://github.com/TommyFive/qwen38-runpod-stack/pull/42).
- Scope: reduce OCI compressed image size from the validated public `ghcr.io/tommyfive/qwen38-sglang:v0.2.0` **without** hurting RTX PRO 6000 Blackwell SM120, SGLang, NVFP4 Qwen3.8 model, DFlash2, cold start, throughput, 20-GiB RAM-first Lean, optional OpenWebUI/Tailscale or API authentication.
- Baseline immutable image digest: `sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd`; compressed manifest layer bytes **12,907,436,335** (~12.907 GB). This tag/digest and live templates were **not changed**.
- Current optimization is CPU-only; full GPU acceptance/benchmarks remain outstanding. No production VPS was used as a build host.

## 2. Original, complete image artifacts

The following original single-large-layer OCI archives were generated and retained unmodified on the temporary ECS as of this checkpoint:

| Candidate | Archive on ECS | SHA256 of original full archive | Compressed OCI bytes | Saving vs v1 |
|---|---|---|---:|---:|
| A — Rust intermediates removed | `/opt/qwen38-v2-build/minimal-v2-rust.oci.tar` | `3b18e589e9cd05f82080efc42c635a1a07e749dfd1edc530573c206ef6fdf998` | 11,921,733,430 | 985,702,905 bytes (7.637%) |
| B — Rust + SHA-equal CUDA copies symlinked | `/opt/qwen38-v2-build/minimal-v2-rust-cuda.oci.tar` | `345d444fc33f14b4521c04d1f1c18aac633c80d1d992a486fcc891d9ca80f8db` | 10,777,962,784 | 2,129,473,551 bytes (16.498%) |

- A removed **1,192 Rust `.rlib`/`.rmeta` files**, **1,665,334,510 logical bytes**.
- B additionally replaced **11 separately verified SHA256-identical CUDA Python-wheel copies** with relative symlinks to system CUDA files, removing **1,679,571,048 logical bytes** from its merged filesystem, without changing system NCCL/cuDNN mismatches.
- These image sizes are measured from OCI layer descriptors, not extrapolated from logical file sizes.

## 3. CPU validation already passed

- The original v1 and B *prune builder stage* successfully imported `torch==2.13.0+cu130`, `flashinfer==0.6.17`, `sglang` and `transformers==5.12.1` in no-network CPU-only test containers with ephemeral cache tmpfs. The original image needed writable JIT caches even to import.
- The **final, scratch-repacked A OCI** was imported into Docker and checked: original ENV, ENTRYPOINT, CMD, working directory, labels etc. preserved; targeted Rust intermediates absent; all four Python imports successful. Final validation exit status **0**.
- **B final OCI load/CPU validation** remains to be completed if disk/time allow. Existing builder-stage successful imports do not prove a repacked artifact or GPU runtime correctness.
- Existing `pip check` noted `nixl 1.5.0` refers to nixl-cu12 and Torch 2.13.0 expects NCCL 2.29.7 where stack uses 2.30.7; these are **pre-existing conditions**, not candidate changes.

## 4. GHCR layer-size emergency workaround

**Important:** GHCR has a **10-GB limit per compressed layer** and a **10-minute upload timeout**. Both original scratch-repacked OCI archives exceed the per-layer limit; they cannot be published as-is.

GitHub official documentation: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry

We therefore created `cpu-audit/split-large-oci-layers.py` to stream existing original OCI `tar.gz` filesystem entries in exactly their original order into multiple new bounded OCI gzip layers. It preserves file content, permissions, ownership, hardlink/symlink paths and OCI runtime config fields, while necessarily rewriting OCI `rootfs.diff_ids`, history and manifest digests. No compilation and no changes to the original OCI files.

- A GHCR-safe OCI layout: `/opt/qwen38-v2-build/oci-split-rust/`; successful split into **8 layers** (7 data + unchanged final empty layer), compressed descriptor sum **11,842,557,123** bytes, local manifest `sha256:ec013c2e20528a92d61b6a7a0352ba081e166ef99025a5fbb4be06572381bb1e`.
- B GHCR-safe OCI layout: `/opt/qwen38-v2-build/oci-split-rust-cuda/`; splitting in progress at time of initial checkpoint.
- New isolated checkpoint GHCR package, separate from v1 production package: `ghcr.io/tommyfive/qwen38-minimal-v2-cpu`. Intended **new tags**: `cpu-rust-20261012-4fb0b652` and `cpu-rust-cuda-20261012-4fb0b652`. **These are target names, not proof of successful publication**; remote digests must be checked and added to this document after successful push.
- Upload via dedicated GitHub Actions `qwen38-ghcr-checkpoint.yml`, repository-scoped `GITHUB_TOKEN` with `packages: write`, pinned SSH host key and temporary GitHub Actions SSH secret. Do not reuse/leave temporary SSH credentials after the backup.

## 5. Full logs and inventory: durable private-encrypted GitHub release asset

A complete raw archive of `/opt/qwen38-audit/` and `/opt/qwen38-v2-build/` (excluding large `*.oci.tar` image files) was backed up, encrypted with `age` to the Mac mini's SSH Ed25519 public key, uploaded as a GitHub release asset, then **re-downloaded from GitHub and verified by SHA256**.

Release: https://github.com/TommyFive/qwen38-runpod-stack/releases/tag/minimal-v2-cpu-checkpoint-20261012

- Asset: `qwen38-checkpoint-logs.tar.gz.age`
- GitHub re-downloaded encrypted asset SHA256: `1b871fa4c2822fbf9a163ea8eb7378b7d594845fac6ded04649866ff85b18f1b`
- Original unencrypted `qwen38-checkpoint-logs.tar.gz` SHA256: `8941363c7612e5f25a8d207f5a1f07af4894e5fb1a8059637e1fe40f248a5bf3`
- **Decrypt ONLY on a trusted host** with the Mac mini's matching `~/.ssh/id_ed25519` private key and the `age` CLI: `age -d -i ~/.ssh/id_ed25519 -o qwen38-checkpoint-logs.tar.gz qwen38-checkpoint-logs.tar.gz.age`. Verify the tar SHA256 above, then extract. Do **not** commit or reveal the private SSH key or upload plaintext logs to public GitHub.
- Separate original first v1-build forensic archive and initial CPU inventory remain on the Mac mini at `~/.local/share/qwen38-cloudzy-builder-archives/` and `~/.local/share/qwen38-cpu-image-audits/`.
- All scripts to reproduce the CPU analysis, pruning, image generation, local OCI manifest inspection, runtime metadata validation, cryptographic CUDA dedup and GHCR-safe repacking are committed in this PR under `images/sglang-qwen38/cpu-audit/`; no 10+GB OCI tar files committed into Git.

## 6. Recovery and next steps

Once both GHCR uploads are **actually remote-verified**:
1. Record the new remote manifest SHA256 digests and matching config/layer digests below, do not confuse original scratch OCI digests with new split OCI digests.
2. On a new authorized host, use `docker pull ghcr.io/tommyfive/qwen38-minimal-v2-cpu@sha256:<REMOTE_DIGEST>` with `read:packages` authentication if the checkpoint package is private. Never change checkpoint package visibility without approval.
3. Run `docker image inspect`, `cpu-audit/verify-repack.py` (adapt reference/labels to split OCI when appropriate), and no-network Python imports for A and B. Preserve exact OCI config and symlinks.
4. Run matched disposable RTX PRO 6000 SM120 tests: actual NVFP4 Qwen3.8 + DFlash2 main/draft, first request/TTFT, 256/512+ tokens, long context, JIT cold/warm/cache, GPU VRAM, API authenticated 200 vs 401, tokens/sec, Tailnet/Lean/SSD/optional Full OpenWebUI.
5. Only promote a **new immutable release tag**, never overwrite v1, after full GPU acceptance.

### Published GHCR results (must fill only after remote inspection)

- Candidate A remote registry manifest digest: **PENDING**
- Candidate B remote registry manifest digest: **PENDING**
- Registry visibility: default GHCR package setting; **no changes requested or made**.
