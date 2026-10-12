# Emergency checkpoint — Qwen38 SGLang minimal-v2 CPU candidates

Date: **2026-10-12 China time**. This is a **pre-GPU** CPU-only checkpoint. The original temporary Alibaba ECS `root@8.211.52.85` has now been shut down; no further access or local build artefacts are assumed. The GHCR images and separate GitHub release backup were independently verified after upload. **Storage validation does not imply the final B-image CPU smoke test or any GPU-runtime validation passed.**

**Scope note:** This archived evidence is part of a documentation-only correction. Experimental minimal-v2 scripts and any unvalidated runtime code remain exclusively on the [research branch](https://github.com/TommyFive/qwen38-runpod-stack/tree/research/minimal-v2-kernel-audit). The original stable `main` image and RunPod templates are untouched. [CPU/GPU acceptance issue #46](https://github.com/TommyFive/qwen38-runpod-stack/issues/46) lists all remaining host-dependent work.

## 1. Project and acceptance requirements

- GitHub: `TommyFive/qwen38-runpod-stack`; experimental work retained on branch `research/minimal-v2-kernel-audit`; [PR #42](https://github.com/TommyFive/qwen38-runpod-stack/pull/42) was merged and subsequently **reverted on `main`** to keep unvalidated tools isolated.
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
- **B final OCI load/CPU validation remains NOT VERIFIED**, and now requires another explicitly approved disposable host. Successful builder-stage imports do not prove final-image correctness or GPU runtime compatibility. Follow [issue #46](https://github.com/TommyFive/qwen38-runpod-stack/issues/46).
- Existing `pip check` noted `nixl 1.5.0` refers to nixl-cu12 and Torch 2.13.0 expects NCCL 2.29.7 where stack uses 2.30.7; these are **pre-existing conditions**, not candidate changes.

## 4. GHCR layer-size emergency workaround

**Important:** GHCR has a **10-GB limit per compressed layer** and a **10-minute upload timeout**. Both original scratch-repacked OCI archives exceed the per-layer limit; they cannot be published as-is.

GitHub official documentation: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry

We therefore created `cpu-audit/split-large-oci-layers.py` to stream existing original OCI `tar.gz` filesystem entries in exactly their original order into multiple new bounded OCI gzip layers. It preserves file content, permissions, ownership, hardlink/symlink paths and OCI runtime config fields, while necessarily rewriting OCI `rootfs.diff_ids`, history and manifest digests. No compilation and no changes to the original OCI files.

- A GHCR-safe OCI layout: `/opt/qwen38-v2-build/oci-split-rust/`; successful split into **8 layers** (7 data + unchanged final empty layer), compressed descriptor sum **11,842,557,123** bytes, local manifest `sha256:ec013c2e20528a92d61b6a7a0352ba081e166ef99025a5fbb4be06572381bb1e`.
- B GHCR-safe OCI layout: `/opt/qwen38-v2-build/oci-split-rust-cuda/`; split finished before backup. Its complete archive has 12 SHA256-verified release blocks. The immutable published GHCR manifest digest is recorded below.
- New isolated checkpoint GHCR package, separate from v1 production package: **`ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint`**. Both distinct tags `cpu-rust-20261012-4fb0b652` and `cpu-rust-cuda-20261012-4fb0b652` were **successfully uploaded, remote-manifest-inspected and rechecked** in [successful Actions run #38159273066](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38159273066) (completed 2026-10-12 01:43:59 China time). Package access still requires checking/authentication as appropriate; visibility was not changed.
- Initial upload via dedicated GitHub Actions `qwen38-ghcr-checkpoint.yml`, repository-scoped `GITHUB_TOKEN` with `packages: write`, pinned SSH host key and temporary GitHub Actions SSH secret. The successful run also completed its on-ECS temporary registry-credential cleanup. This is historical evidence only: the original ECS is now gone; do not rerun emergency workflows.

## 5. Full logs and inventory: durable private-encrypted GitHub release asset

A complete raw archive of `/opt/qwen38-audit/` and `/opt/qwen38-v2-build/` (excluding large `*.oci.tar` image files) was backed up, encrypted with `age` to the Mac mini's SSH Ed25519 public key, uploaded as a GitHub release asset, then **re-downloaded from GitHub and verified by SHA256**.

Release: https://github.com/TommyFive/qwen38-runpod-stack/releases/tag/minimal-v2-cpu-checkpoint-20261012

- Asset: `qwen38-checkpoint-logs.tar.gz.age`
- GitHub re-downloaded encrypted asset SHA256: `1b871fa4c2822fbf9a163ea8eb7378b7d594845fac6ded04649866ff85b18f1b`
- Original unencrypted `qwen38-checkpoint-logs.tar.gz` SHA256: `8941363c7612e5f25a8d207f5a1f07af4894e5fb1a8059637e1fe40f248a5bf3`
- **Decrypt ONLY on a trusted host** with the Mac mini's matching `~/.ssh/id_ed25519` private key and the `age` CLI: `age -d -i ~/.ssh/id_ed25519 -o qwen38-checkpoint-logs.tar.gz qwen38-checkpoint-logs.tar.gz.age`. Verify the tar SHA256 above, then extract. Do **not** commit or reveal the private SSH key or upload plaintext logs to public GitHub.
- Separate original first v1-build forensic archive and initial CPU inventory were stored on the Mac mini at `~/.local/share/qwen38-cloudzy-builder-archives/` and `~/.local/share/qwen38-cpu-image-audits/`; the v1 raw build logs were **also encrypted and uploaded** as a separate release asset. No assumption about current Mac mini storage is required for the GitHub copies.
- Further post-split logs were backed up as **`qwen38-checkpoint-after-split.tar.gz.age`**, SHA256 `f4417ae54b429706f52cd85b8905cd76c845e2adfc4bd635870a5833b987edd0`. The release contains **three encrypted forensic assets** in total.
- All experimental CPU audit, pruning, OCI generation, configuration-validation, cryptographic CUDA deduplication and GHCR-safe repacking scripts are preserved on the **[research branch](https://github.com/TommyFive/qwen38-runpod-stack/tree/research/minimal-v2-kernel-audit/images/sglang-qwen38/cpu-audit)**, **not on `main`**. The initial [PR #42](https://github.com/TommyFive/qwen38-runpod-stack/pull/42) was reverted on `main` after being merged; this documentation-only checkpoint is intentionally separate. No 10+GB OCI TAR files are stored as Git blobs.

## 6. Recovery and next steps

Both GHCR uploads were **remote-verified in Actions #38159273066**. On a fresh, approved host:
1. Use the **verified immutable GHCR manifest digests below** (rather than mutable tags) and, if needed, authenticate to GHCR with minimum `read:packages` access. Distinguish original scratch OCI archive checksums from the new split-layout registry manifest digests.
2. On a new authorized host, use `docker pull ghcr.io/tommyfive/qwen38-minimal-v2-cpu@sha256:<REMOTE_DIGEST>` with `read:packages` authentication if the checkpoint package is private. Never change checkpoint package visibility without approval.
3. Run `docker image inspect`, `cpu-audit/verify-repack.py` (adapt reference/labels to split OCI when appropriate), and no-network Python imports for A and B. Preserve exact OCI config and symlinks.
4. Run matched disposable RTX PRO 6000 SM120 tests: actual NVFP4 Qwen3.8 + DFlash2 main/draft, first request/TTFT, 256/512+ tokens, long context, JIT cold/warm/cache, GPU VRAM, API authenticated 200 vs 401, tokens/sec, Tailnet/Lean/SSD/optional Full OpenWebUI.
5. Only promote a **new immutable release tag**, never overwrite v1, after full GPU acceptance.

### Published GHCR results — **verified, not pending**

| CPU candidate | GHCR tag | Immutable remote manifest SHA256 | Remote validation |
|---|---|---|---|
| A — Rust | `cpu-rust-20261012-4fb0b652` | `sha256:ec013c2e20528a92d61b6a7a0352ba081e166ef99025a5fbb4be06572381bb1e` | PASS 2026-10-12 01:31:51 CST |
| B — Rust + CUDA dedup | `cpu-rust-cuda-20261012-4fb0b652` | `sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7` | PASS 2026-10-12 01:43:53 CST |

Registry: `ghcr.io/tommyfive/qwen38-minimal-v2-checkpoint`.

**Independent checks in the same successful GitHub-hosted job:** `skopeo inspect --raw` of each remote tag yielded the above SHA256 manifest digests, followed by authenticated `docker manifest inspect` of *both* tags. [Full immutable run evidence](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38159273066). The two new image manifests differ from the original single-layer OCI tar archives by design: layers were split to comply with registry blob limits; **do not compare them with original tar SHA256**.

Registry visibility was not changed. A full cold pull / Docker runtime inspection on a **new disposable host** is still an open acceptance step, not something evidenced by registry inspection alone.

### Storage checkpoint completion criteria — met

- [x] A and B distinct GHCR tags/manifest digests verified remotely.
- [x] Original v1 build, CPU audit and later post-split logs encrypted and stored as 3 release assets.
- [x] A release fallback: 13 of 13 OCI block assets individually SHA256 verified.
- [x] B release fallback: 12 of 12 OCI block assets individually SHA256 verified.
- [x] Both release block checksum manifests present, 30 total release assets, [backup workflow success](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38158692348) on 2026-10-12 02:15:08 CST.
- [ ] Independently cold-reconstruct/re-pull and validate both **runtime** images on a future approved host ([#46](https://github.com/TommyFive/qwen38-runpod-stack/issues/46)).



## 7. Emergency persistent GitHub Release fallback (GHCR returned 403)

The **initial** GHCR attempts using a temporary repository-scoped Actions token with `packages: write` authenticated successfully but received **HTTP 403 Forbidden on blob upload**. Those earlier runs did *not* publish an image. A later source-linked, newly named checkpoint package passed a separate write-capability probe and **both full images were successfully published and remote verified** in [run #38159273066](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38159273066). Do not mistake the initial 403 for the final state; existing production package visibility and tags were not changed.

Because the ECS will be released automatically, the full **GHCR-safe split OCI layouts** are also archived with all OCI blobs, config, manifest, index and `oci-layout` metadata as ordinary TAR files, cut into `900MiB` independent blocks for GitHub Release Assets. This avoids GHCR package write permissions and the 2-GiB GitHub individual release-asset limit.

- A: **13 sequential blocks** `release-rust.part-aa` through `release-rust.part-am`; checksum manifest `release-rust.parts.sha256`.
- B: **12 sequential blocks** `release-rust-cuda.part-aa` through `release-rust-cuda.part-al`; checksum manifest `release-rust-cuda.parts.sha256`.
- Each block **was uploaded** from the ECS by a short-lived GitHub-hosted runner and checked against the **server-provided `sha256:` release-asset digest**. The workflow also rejected incomplete part sets. [Run #38158692348](https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/38158692348) finished **successfully**, with **13/13 A and 12/12 B**, all SHA256-verified.
- Workflow: `.github/workflows/qwen38-release-backup.yml`; Actions run `38158692348` and later runs if retry is required.
- These blocks contain **complete GHCR-safe OCI layouts**, NOT flattened payload-only tarballs. **All 25 blocks plus both manifest files are present and release-digest-verified.** Reassembling them from GitHub and revalidating the resulting images on a new host is still pending.

### Restore after the original VPS disappears

On a **new, explicitly approved** host with enough SSD capacity, download the release assets matching each candidate, preserving the exact names. With `gh`, `sha256sum`, `tar` and `skopeo` available:

```bash
REPO=TommyFive/qwen38-runpod-stack
RELEASE=minimal-v2-cpu-checkpoint-20261012
mkdir -p qwen38-recovery
cd qwen38-recovery
gh release download "$RELEASE" -R "$REPO" --pattern 'release-rust.part-*' --pattern 'release-rust.parts.sha256'
gh release download "$RELEASE" -R "$REPO" --pattern 'release-rust-cuda.part-*' --pattern 'release-rust-cuda.parts.sha256'
sha256sum -c release-rust.parts.sha256
sha256sum -c release-rust-cuda.parts.sha256
cat release-rust.part-* | tar -xf -
cat release-rust-cuda.part-* | tar -xf -
skopeo inspect --raw oci:oci-split-rust:checkpoint > rust-manifest.json
skopeo inspect --raw oci:oci-split-rust-cuda:checkpoint > rust-cuda-manifest.json
```

Do NOT confuse the compressed OCI payload byte count with the total `tar` container size. After restoration, use `skopeo copy oci:oci-split-rust:checkpoint docker://...` and the analogous B source to publish (requires **authorized** GHCR `write:packages`).

### Second encrypted GitHub checkpoint asset

The original first Alibaba v1 builder archives from the Mac mini were also preserved as `qwen38-original-v1-build-logs.tar.age` on the same GitHub release and remote digest-verified:

`sha256:661ab22b77167df7f76a65461b2a7a0c9d4c73e50ab930f2b214232b77e9f1b3`.

These full raw build logs are encrypted to the same Mac mini SSH Ed25519 recipient as the CPU checkpoint. No private decryption key or token is committed to the repository.

