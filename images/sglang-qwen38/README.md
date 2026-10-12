# Qwen38 SGLang image

**Current: minimal-v2 B, release v0.2.2** — CPU-restored and GPU smoke-tested on
RTX PRO 6000 Blackwell (SM120), NVFP4 + DFlash2, Lean and Full/Tailnet.
This repository cleanup does not build or change an image.

| Role | Immutable linux/amd64 manifest | Compressed layers |
|---|---|---:|
| Current `ghcr.io/tommyfive/qwen38-sglang:v0.2.2` | `sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7` | 10,703,739,835 bytes / 8 |
| Rollback `ghcr.io/tommyfive/qwen38-sglang:v0.2.0` | `sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd` | 12,907,436,335 bytes / 31 |

## Build and release contracts

`upstream.lock.json` pins SGLang `5f55db35e926d50676f75b812640ea2410b0fe0e`,
CUDA 13.0.3, FlashInfer 0.6.17 (including JIT cache), and source-file hashes.
`prepare-source.py` validates those hashes and introduces the empty
`qwen38-minimal` extra; base dependencies remain unchanged.

On an approved dedicated Linux x86_64 build host:

```bash
bash images/sglang-qwen38/build-image.sh --tag ghcr.io/tommyfive/qwen38-sglang:candidate-REVISION
```

This builds the **minimal-v1 source baseline**, not a new v2/v3 image. v2 B was a
verified fresh-filetree repack of v1; its CPU tooling is in `tools/audit/`.
Publishing requires the entrypoint's explicit opt-in. Never build on production
VPN/Passwall hosts. Neither CI nor this command launches a GPU.

`release.json` deliberately describes **v0.2.0**, because the v1 release workflow
consumes it. Do not repurpose it for v2. The separate v2-B promotion workflow
retains the tested checkpoint-source digest and destination invariants.
Git release tags and OCI image tags are different resources.

## Verify without building

```bash
python3 -m unittest discover -s images/sglang-qwen38/tests -v
python3 -m unittest discover -s tests -v
python3 scripts/privacy-check.py
python3 images/sglang-qwen38/tools/inspect-registry.py --reference v0.2.2
```

Registry verification reads manifests/config and HEAD-checks every blob; no
multi-GB layer download. `tools/check-public.py` is the small deployment preflight
used by the regular template flow. `tools/audit-image-config.py` audits v1 build
metadata for secrets using an ephemeral Actions package token. These have
separate contracts and are intentionally retained.

Use the repository-root `create-templates.sh` and `bin/qwen38fast` for supported
Public/Tailnet, Full/Lean and RAM/SSD configurations. The historical one-shot
candidate launchers and release-asset publisher/recovery path are retired.

- [Optimization history, measurements and v3 roadmap](OPTIMIZATION_V3.md)
- [Validation, evidence, recovery and remaining gaps](VALIDATION.md)
- [Published v0.2.2 removal inventories](../../docs/releases/v0.2.2.md)
- [Cleanup and privacy maintenance](../../documentation/image-cleanup/README.md)
