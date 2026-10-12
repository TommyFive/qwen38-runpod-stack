# Image cleanup and ongoing privacy protection

## Purpose and scope

Consolidate the v1/v2 image knowledge and CPU tooling into a reproducible v3
starting point; sanitize the current repository without rewriting published
history or changing any production OCI image. Work started from current `main`,
with selective reviewed imports, not merges of historic research commits.

Source heads recorded before changes:

| Reference | SHA |
|---|---|
| main | `2d613e40fcb4638c7c397658280edde4c51cec49` |
| feature/minimal-v2-gpu-full-tailnet-live-test | `b2c40c00676c3560418fd8984ad7f07f1654a107` |
| research/minimal-v2-kernel-audit | `b1b5bbfae8627eaffd98a658cb4b141bbb451469` |

## Layout, dependencies and entrypoints

`images/sglang-qwen38/` has three documents: README (current status/build),
OPTIMIZATION_V3 (all measured optimization knowledge/risks) and VALIDATION
(procedures, evidence chronology and remaining gaps). Five evidence JSON files
retain CPU/GPU results, original checksums and separate run contexts. Generic
registry/size/cold-start/watchdog tools live in `tools/`; forensic/repack tools in
`tools/audit/`. Unit tests remain under `tests/` at both image and repository level.

Distinct helpers retained beyond the suggested minimal tree:
`check-public.py` is a deployment preflight; `subtree-report.py` and
`verify-duplicates.py` provide subtree/bounded general hash analyses, unlike the
fixed CUDA pair comparison. The release-specific fallback downloader is removed:
its only remote source is the retired CPU GitHub release. Local OCI verification
and historical restore/hash evidence remain. No active release process requires
those 30 assets. Large release artifacts are not copied or republished elsewhere.

The provider-specific build orchestration and one-shot candidate template
launchers are removed. Durable JSONL/fsync monitoring is folded into
`tools/watch-build.py --output FILE`; process-group guardrails remain tested.
Publishing telemetry now requires both an explicit `QWEN38_STATUS_PR` and token;
there is no default historical PR target. Build workflow is manual-dispatch only,
retaining capacity and isolated-process watchdog gates. No build is run by this cleanup.

Runtime bootstrap/template fixes already on `main` are preserved; only the missing
strict Tailnet `qwen38bench --api-base` support is imported from the feature branch.
Tests for one-shot launchers/provider reattachment are retired with that architecture;
regular template dry-run, portless/private auth, immutable pins, storage, runtime
bootstrap, resource-pressure/process isolation and complete inventory tests remain.

`release.json` remains the v1 contract. v2-B promotion remains separate with its
original source/config/layer pins. Published removal inventories are byte-identical.
The historical checkpoint package is still a promotion source and provenance
reference: **do not delete it without separate approval and dependency retirement**.

## Privacy scanning

`python3 scripts/privacy-check.py` scans every tracked textual file and path;
`--commits BASE..HEAD` additionally scans new author/committer data and messages.
It flags personal home paths, private Tailnet identifiers, personal devices,
cloud-instance IDs, literal SSH targets/credential URLs, infrastructure IPv4
addresses and literal resource identifiers. It prints categories/locations only.

`gitleaks dir --redact --no-banner .` uses upstream default rules and the exact
non-secret `SENTINEL_...` test-fixture allowlist in `.gitleaks.toml`. There are no
file-wide exclusions. `.github/workflows/privacy.yml` runs both scanners for every
push and PR and pins Gitleaks 8.30.1. The check scans the current tree and **new**
commits; it does not falsely certify legacy reachable history as clean.

Reviewed exceptions: loopback, unspecified bind addresses, RFC 5737 documentation
ranges; example Tailnet names; hosted-runner paths; the exact OpenCV wheel version
`4.10.0.84` (not an IP). Public GitHub noreply identities are allowed for new commit
metadata. Account/host details belong in environment variables or private notes,
never in public examples. New fixtures must use documentation/example values.

| Finding class | Treatment |
|---|---|
| Personal paths and workstation/server descriptions | `$HOME`, neutral role labels, generic tooling |
| Private Tailnet hostname/IP and host names | Explicit example names/RFC 5737 IPs; functional runtime discovery unchanged |
| Historic pod/template IDs and filenames | Stable neutral historical resource labels, references updated |
| Personal account balances | Removed; bounded historical rate/debit observations retain their uncertainty |
| Historical provider tag in v1 release metadata | Redundant candidate field removed; immutable digest preserved |
| Git history/author identities, PR refs/logs and immutable OCI labels | Private audit and local rewrite rehearsal; **not remotely sanitized** |

## Operation, validation and rollback

Requirements: Python >=3.11 for source pin tests (`tomllib`), Bash, Git; ShellCheck,
actionlint and Gitleaks for static checks. Linux tmpfs integration tests execute on
GitHub's Linux runners, not on production hosts. For OCI repacking, a separately
approved Linux host additionally needs Docker/Buildx and pigz; read-only registry
inspection itself uses Python standard library only.

Run image and root unittest discovery, all shell `bash -n` checks, JSON/YAML parse,
actionlint, ShellCheck, privacy/secret checks, and Linux bootstrap/privacy/Tailnet/
storage tests. No GPU test or Docker rebuild is needed for these repository changes.
Registry helper inputs are tag/digest/repository, output is verified JSON descriptor
metadata; config output is optional and should be private because historical labels
can identify infrastructure. HEAD verifies blob availability and length, not a fresh
whole-layer digest download.

Recovery pulls the production image by immutable digest; keep v0.2.0 rollback.
Source changes can be reverted through review, but reverting anonymization may
republish private data. Do not recreate the retired CPU release assets to roll back
repository changes. Production images and live templates are untouched.

## Private audit artifacts and history approval boundary

A private mirror includes all advertised branches/tags and accessible PR refs;
independent no-hardlink restoration and full `git fsck` validate Git recovery.
Private source snapshots and a per-original-path KEEP/MOVE/MERGE/DELETE decision
matrix include source SHA256 and dependencies. These files intentionally are not
committed because original paths/identities may themselves be private.

A separate local `git-filter-repo --sensitive-data-removal` rehearsal covers paths,
blob text, commit messages, identities and annotated tags; its private rules,
commit/ref mappings and `changed-refs` are retained for explicit review. No remote
force push, protection change, tag recreation or historical branch deletion is
part of the current integration. Rewriting an ancestor changes published release
Git-tag commit SHAs even when the current filetree is unchanged. That needs
separate approval; OCI tags/digests must remain unchanged.

Residuals: GitHub PR refs/diffs/caches may need Support; old Actions logs/artifacts,
release bodies, forks, external clones and signed-object verification require
separate coordinated cleanup. Git history rewriting does not alter GHCR config
labels, nor erase others' clones. Do not call the entire project historically
private until every remaining reachable reference and external surface is reviewed.

Related: [image overview](../../images/sglang-qwen38/README.md),
[v3 matrix](../../images/sglang-qwen38/OPTIMIZATION_V3.md),
[validation](../../images/sglang-qwen38/VALIDATION.md),
[release inventories](../../docs/releases/v0.2.2.md).
