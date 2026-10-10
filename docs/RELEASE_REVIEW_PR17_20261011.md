# PR #17 — Final release review / GO–NO-GO (2026-10-11)

**Decision: NO-GO for merge to `main` today.** The actual network/TLS blocker is fixed and live verified. Remaining **positive authentication acceptance gates** have not been demonstrated; neither green offline CI nor a passing negative-auth test substitutes for a positive login. This review does not approve merging and does not create a paid Pod.

**Code basis at review start:** `ad481c4eabed78378464c3802c75cf0e73f061a7` on `integration/issues-7-11-20261010`, PR [#17](https://github.com/TommyFive/qwen38-runpod-stack/pull/17), `main` at `6e25ce80a17d19d3dd46dc146ad9a2173bf39885`. GitHub reports mergeable (no conflicts), Draft; 38 changed paths, both CI workflows `Bootstrap integrity` and `Benchmark regression` successful at that SHA; no submitted PR reviews or unresolved review threads. The main branch was reported unprotected by GitHub's branch API; GitHub mergeability is NOT security approval.

## Release-gate disposition

| Gate | Status | Verified evidence / explicit gap |
|---|---|---|
| **G1: Tailnet HTTPS and native SSH** | **PARTIAL — network/TLS PASS; positive external auth pending** | [Live Private Full Pod `s5titot9ae0zzv`](runs/20261010T163129Z_s5titot9ae0zzv.md): HTTPS TLS hostname verification passes on TCP 443 & 8443, `ssl_verify_result=0`, native Tailscale SSH, zero RunPod published ports; `tailscaled --state=mem: --statedir=/dev/shm/.../state` certificates on tmpfs; API without/wrong Bearer 401. Positive **external** valid-Bearer API status not tested. See #20. |
| **G2: Four template/config parity** | **PASS for documented tested scope** | Public Full `9zmcmzwu4b`, Public Lean `g6ey6ire16`, Private Full `aa7z98qnzs`, Private Lean `syb1a3cqr6`: previously synchronized in place, RunPod Secrets retained, private port list empty; last live Pod ran #29 helper. No template recreation. |
| **G3: Authentication / privacy** | **PARTIAL — release blocker** | SGLang HTTPS API wrong/missing Bearer 401; in-pod trusted OpenWebUI prerequisite request to `/v1/models` returned 200 with configured key; WebUI `auth=true`, `enable_signup=false`, anonymous chats 401. **Still missing**: an independent external API 200 with valid Bearer **and successful HTTPS WebUI admin credential login**. The attempts to read a protected secret via SSH-MCP were blocked by the safety gate and intentionally not circumvented. A negative result plus an application's config page does not demonstrate a real login. |
| **G4: Storage, settings, benchmark** | **PASS for scoped initial release**, optional combinations deferred | RAM-only verified for main and draft, cgroup capacity guard, no silent SSD fallback; independent Public Full opt-in SSD audit passed, optional post-load RAM release recovered 22.731 GiB with subsequent authorized inference, default OFF; benchmark regression and real GPU throughput tested. Public Lean GPU launch and exhaustive opt-out/combinatorial modes not independently sampled; require **explicit owner's residual-coverage acceptance**, not an invented PASS. |
| **G5: Final review and CI** | **PARTIAL — evidence reviewed, final GO pending** | Current PR change set (38 paths) and sensitive flows examined; no new observed critical code regression from this scope. Both CI suites green at audited SHA; reviewed related issue policy; remaining gaps and accepted risks documented. Formal PR review and final owner GO/merge authorization absent. Refresh CI evidence if any release-doc/code revision changes the PR head. |

## Existing, accepted non-blocking work

- **#18 / #22**: Account-global `qwen38fast stop`, reaper, absent reliable per-Pod TTL; owner explicitly accepted the **single-project account** limitation until later. Legacy reaper off. **Never run account-wide cleanup if unrelated Pods are added.**
- **#5 / #6 / #11 / #23**: Better speed probe, byte-accurate HF/Xet download progress, provider scheduling/region/cache metadata, larger cold-start cohorts, image optimization. Existing UTC/monotonic markers and two detailed new Pod records are accepted baseline; not gating merge.
- **#21**: Pinned smaller custom image remains separate from initial integration; no need to await its build before PR #17.
- **#7–#11**: Features implemented in integration and supported by tests/live evidence, but GitHub issues remaining `open` do not automatically mean unimplemented; do not close until owner accepts the applicable issue criteria.

## Security / code review caveats

- The public SGLang/OpenWebUI modes intentionally expose network ports and must retain Bearer/WebUI authentication. Tailnet wildcard source ACL applies **within the tailnet only** and reflects the owner's decision, not a new public RunPod exposure.
- `WEBUI_ADMIN_PASSWORD` is passed to RunPod in the launcher's `--env` JSON and SGLang API key appears in process arguments inside the Pod; these documented provider/process-visibility limitations are **not** removed by tmpfs or redaction. Handle only test/non-sensitive data unless the cloud trust boundary is acceptable; no credentials should enter PR bodies, logs or this report.
- Current RunPod key availability must be verified before another launch. For a safe manual acceptance test, set up a matching client Bearer secret **without posting its value to GitHub/ChatGPT**. An independent HTTPS API request with the correct token must return 200 and usable model metadata; the same endpoint with incorrect/missing token must return 401.
- Over HTTPS on 8443, an authorized operator must sign in with the existing OpenWebUI administrator password and verify an authenticated session accesses a protected API, while anonymous requests remain 401 and signup is disabled. Evidence should include sanitized UTC/HTTP status/hostname, not credentials, cookies or raw private prompts. Browser shared-tab access is currently absent; do not attempt to bypass SSH-MCP credential safety checks.
- The RunPod Pod for the latest HTTPS test was deleted by exact ID. A new paid Pod should **not** be started until the operator can complete these positive checks promptly; each new Pod requires a fresh cost approval plus a complete cold-start/evidence record.

## GO criteria before PR #17 reaches `main`

1. **External API positive:** actual Tailnet HTTPS valid-Bearer `GET /v1/models` 200; verify the public/anonymous 401 negative path remains.
2. **Positive WebUI admin session:** HTTPS login succeeds; authenticated protected read works, anonymous access and signup remain denied.
3. **Risk disposition:** Owner explicitly accepts untested Public Lean GPU and exhaustive configuration combinations if these are deferred (alternatively validate them), plus previously accepted #18/#22 account-only risk.
4. **Release record:** Update #20, refresh stale status/checklists in strategy/ACL/smoke documents, ensure both CI suites green on final PR #17 head, record formal reviewer/owner GO and explicit merge authorization.
5. **Then and only then:** remove Draft / merge PR #17 to `main`. Do not conflate an approval to investigate or run tests with authorization to bypass unverified release gates.

**Current decision: HOLD / NO-GO.** No paid Pod started for this review. The preceding owner-approved test Pod was terminated with 0 active Pods / 0 USD/h verified. Further development/benchmark replays are unnecessary until the two positive auth checks are coordinated.
