# PR #17: Final integration strategy and release gates (2026-10-10)

> **UPDATED RELEASE VERDICT (2026-10-11): NO-GO / HOLD.** See [final release review](RELEASE_REVIEW_PR17_20261011.md), based on integration `ad481c4e`. The formerly confirmed tailnet ACL timeout and Tailscale certificate-state problem are **fixed and verified live** on Pod `s5titot9ae0zzv`: trusted TLS 443/8443, native SSH, private portless templates, negative API/WebUI auth tests all pass. **Outstanding release gates:** independent *external* positive SGLang valid-Bearer call, positive OpenWebUI admin session, explicit residual coverage acceptance, final GO and merge authorization. The initial strategy and old root-cause text below are historical where superseded; do not act on the dedicated-tag suggestion. No paid Pod running after exact-ID cleanup.

> **Status:** Proposed merge criteria; no merge into `main` without explicit
> owner approval. This is a **reconstructed, consolidated strategy** based on
> issues #7–#11, existing PRs #12–#16, PR #19 and live integration reports.
> The earlier standalone "Integration Strategy / Backlog" Markdown file could
> **not** be located in the currently available 13 GitHub branch tips or the
> local integration checkout. Do not misrepresent this as the original source.

## 1. Baseline, provenance and scope

- Repository: `TommyFive/qwen38-runpod-stack`; PR [#17](https://github.com/TommyFive/qwen38-runpod-stack/pull/17) targets `main`.
- Head at the audit: `84672f280cdb7f23746b00199809c2059438e7b0`.
- Source PRs #12–#16 were consolidated/superseded; #19 (optional RAM release,
  default `0`) merged into integration. The main branch remains untouched.
- Both offline GitHub workflows passed on the audited head.
- Mac mini local checkout matched that commit with clean Git status; installed
  `qwen38fast`, bootstrap and model-storage helper did **not** match checkout
  bytes. This local helper drift was resolved on the Mac mini
  using targeted file installs, not `setup.sh`; the old reaper remains off.
- Live validation so far: RTX PRO 6000 Private Lean, Private Full and Public Full/SSD,
  authenticated SGLang + DFlash2 inference, RAM-backed main+draft, native
  Tailscale SSH, absent public RunPod proxy exposure for portless templates,
  OpenWebUI negative authentication tests, benchmarks and automatic weight
  cleanup when explicitly enabled.
- Defaults must stay `MODEL_RAM_RELEASE_AFTER_LOAD=0`,
  `MODEL_RAM_PEAK_FACTOR=2.5`, `BENCHMARK=0`, `DEBUG=0`,
  `MODEL_STORAGE=ram`, with no silent SSD fallback.

## 2. Blocking merge gates (functional/security)

| Gate | Required proof | Current status | Priority |
|---|---|---|---|
| **G1: Tailscale HTTPS Serve #20** | Tailnet trusted TLS 443/8443, API 401/200, WebUI auth and positive login, native SSH and zero public RunPod ports | **PARTIAL**: TLS, ACL, 443/8443, SSH and 401 negative paths **PASS** on `s5titot9ae0zzv`; *independent external valid-Bearer 200* and *positive WebUI admin login* still unverified (SSH credential access blocked). See [release review](RELEASE_REVIEW_PR17_20261011.md) | P0 |
| **G2: Four template/config parity** | Read-only metadata GET for all existing public/private Full/Lean IDs; validate network mode, ports (private `[]`), embedded bootstrap/helper SHA or byte identity, RunPod Secret references and defaults; no credentials logged | **PASS (template parity 2026-10-10):** all four existing IDs read via RunPod, public port configs correct, private ports empty, all RunPod Secret references kept, bootstrap/storage/TS/benchmark helpers refreshed in place and byte SHA verified | P1 |
| **G3: Auth/privacy negative and positive flows** | No anonymous API/Chat; authenticated UI admin login and fail-closed privacy | **PARTIAL / RELEASE BLOCKER**: HTTPS missing/wrong Bearer 401, in-Pod authorized `/v1/models` 200, WebUI auth=true/signup=false/anonymous chat 401. **External positive auth and positive login missing**; Public Lean GPU not independently tested and requires owner risk acceptance or targeted validation | P1 |
| **G4: Storage/settings integration** | RAM and cgroup preflight, main/draft on verified tmpfs, opt-in SSD and failure pathways, release-after-inference guarded and default OFF; read-only audit of generated paths and no silent fallback | RAM + release-opt-in and Public Full **SSD snapshot root** passed live; DEBUG=0/COLDSTART_TRACE=0/BENCHMARK=0 selected in paid SSD cohort. Full combinatorial switch matrix not exhaustively live checked | P1 |
| **G5: Final review/CI** | Audit release diff and residual risks; CI at final SHA, owner GO | **PARTIAL**: static diff/security review and [GO/NO-GO document](RELEASE_REVIEW_PR17_20261011.md) created; CI was green at `ad481c4e`, no reviews recorded, current **NO-GO** until positive auth and explicit GO / merge authorization; rerun CI after changes | P1 |

A **minimal paid cohort** after no-cost diagnosis should combine G1, G2–G4
where possible. Previously validated benchmark throughput **must not** be
rerun without a specific regression. A proper positive auth check must not
print credentials. All paid tests require a separate owner cost approval.

## 3. Explicitly accepted and non-blocking

### Account-wide pod stop/reaper/TTL — #18, risk register #22

Owner's operating assumption (2026-10-10): this RunPod account is **only**
used for QWEN38 pods, with no unrelated pods to protect. Existing
`qwen38fast stop` / `qwen38pi stop` can delete all account pods. The legacy
reaper also selects from all pods, has global 1h age logic, and is **not
currently installed** as a LaunchAgent on audited Mac mini. `setup.sh`
would activate it. Installed CLI 2.15.0 cannot be relied upon for
`--terminate-after`; requested 2h/4h runtimes are **not** guaranteed TTL.
For supervised paid tests, target exact Pod ID for termination, verify no
ongoing spend, and avoid using the global reaper. There is **no hard cost cap**.
If the account begins hosting other workloads, this accepted risk must be
reassessed before using stop/reaper. Implement project-scoped identity and TTL
post-merge in #18. This limitation is **not a blocker** for PR #17.

### Additional performance/observability — #23 (with #5, #6, #11 and PR #21)

Already in integration: `COLDSTART_TRACE=1` default with UTC and monotonic
host/pod event markers; launcher pod creation, authenticated API-ready,
first successful inference, optional OpenWebUI readiness; bootstrap events
for network probe, combined main+draft download, SGLang startup and
`/health_generate`; `qwen38cold report/summary` with explicit observed
platform events and unknown/null phases; separate opt-in benchmark with
server-reported token accounting. Real RTX PRO 6000 measured technical
135.8, code 187.1, code-edit 190.6 tok/s; automatic RAM cleanup released
22.731 GiB and inference survived. In a Community-*requested* Full pod,
Docker image available at ~4m38s after creation (includes scheduling),
combined main+draft download ~207.66s, TTFI ~9m59s and OpenWebUI ready
~10m44s; actual region/cache/cloud metadata remain unverified.

Deferrals: accurate connectivity/speed probe (#5), byte-based HF/Xet
progress (#6), independently attributed scheduling/layer image-pull and
GPU/CUDA timings (#11), matched Secure vs Community with credible
sample sizes and cache/region control, and candidate smaller SGLang image
(#21, dedicated builder only). All are **not merge blockers**.

## 4. Implementation sequence / integration procedure

1. **Free/read-only:** inspect Tailscale ACL/grants, HTTPS Serve config and
   known failure logs; determine whether the issue is port permissions,
   userspace Serve listener, SNI/TLS or relay path. Do not widen ACLs or open
   RunPod ports as workaround.
2. **Isolated fixes:** small feature PR(s) into
   `integration/issues-7-11-20261010`, CI on each change. Include a real
   external HTTPS reachability assertion (configured Serve state alone
   is not sufficient).
3. **Parity and offline matrix:** inspect all four existing RunPod template
   IDs and SHA/embedded-helper/settings against integration checkout. Keep
   the same IDs and RunPod Secrets. Verify public authentication, debug,
   RAM/SSD/preflight/opt-out behavior as far as possible with mocks. Do not
   run `setup.sh` blindly (legacy reaper activation).
4. **One combined authorized paid GPU validation** after preparing focused
   tests: portless Private Full first to prove HTTPS :443/:8443 with TLS and
   positive+negative credentials; collect detailed cold-start markers and
   RAM/storage evidence. If needed, a focused public/SSD test verifies
   unvalidated modes without repeating benchmark runs.
5. **Final PR update:** merge tested small PRs into integration only;
   rerun both workflows at exact final SHA, review no new secrets/ports or
   SGLang/NCCL package regression, capture residual risks, then submit
   Go/No-Go report to owner. **Never merge PR #17 into main without explicit
   final approval.**

## 5. Deferred post-merge issue links

- #18 / #22 — safely project-scoped stop/reaper/TTL and accepted single-project
  limitation.
- #23 / #5 / #6 / #11 — observability/performance after baseline integration.
- #21 — candidate minimal image on approved build host; not part of #17.
- #20 — **TLS/ACL defect is fixed and live verified**; full security release gate still requires independent valid-Bearer API 200 and positive admin UI login.

Related evidence:
[smoke](INTEGRATION_SMOKE_20261010.md),
[Full Community](INTEGRATION_FULL_COMMUNITY_20261010.md),
[security](SECURITY.md),
[cold start](COLD_START.md),
[cost control](COST_CONTROL.md).
