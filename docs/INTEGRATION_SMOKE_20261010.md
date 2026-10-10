# Integrated RunPod GPU smoke — issues #7, #8, #9, #10, #11

> **Release-gate reclassification (owner decision, 2026-10-10):**
> Tailscale HTTPS Serve #20 is still a mandatory blocker. Safe project-scoped
> Reaper/TTL #18 is **accepted/deferred** because the RunPod account is only
> used for QWEN38 pods (risk tracking #22). Additional cold-start and download
> observability/optimizations (#5, #6, #11; follow-up #23) are **post-merge**,
> not required for PR #17. Current UTC/monotonic host+pod cold-start markers,
> validated GPU inference and benchmark remain in scope. See
> [integration strategy](INTEGRATION_STRATEGY_PR17_20261010.md).

## Test 2 — Private Full Secure, live ACL root-cause confirmation (2026-10-10)

**New live findings:** RunPod Secure RTX PRO 6000, actual $2.49/h, pod
`xyijp8lpaauxqq` (targeted-deleted, 0 active after cleanup). All four
existing template IDs were synchronized **in place** to the same exact
repository bootstrap/Tailscale/storage/benchmark helpers and verified
to preserve RunPod Secret references. Both private templates have zero
public ports. Mac mini checkout updated to `58ecc266` and installed helpers
were synchronized **without `setup.sh`** (legacy global reaper still disabled).

On the live Pod, the Tailscale `PacketFilterRules` admitted Mac mini -> Pod
**TCP/22 only**, with a broad Tailnet -> Pod **TCP/8080** rule; **no
443/8443 admission**. Native SSH via Tailnet IPv4 worked; forced-hostname
HTTPS TCP 443/8443 timed out. Thus #20's **root cause is the actual Tailnet
ACL/grant**, not merely a conjectured Serve configuration problem.
SGLang unauthenticated local API returned **401** and local WebUI
`/api/config` returned **200**. HTTPS Serve must not be labeled PASS for
Private Full until a narrowly scoped Tailnet grant and positive TLS/auth
tests are complete. Dedicated Pod tag + scoped grants and RunPod Secret key
rotation are documented in [TAILNET_ACL_ISSUE20.md](TAILNET_ACL_ISSUE20.md).
No Tailscale ACL or key was changed, and public RunPod ports were not opened.

New Secure cold-start **single observation, NOT a matched cloud comparison**:
creation 10:19:02 UTC, bootstrap 10:20:54.786, combined model+draft
download 10:20:57.436–10:21:10.983 (13.55s), `/health_generate`
10:22:28.344 (~206s after pod creation); region/image cache unknown.
This non-blocking performance evidence is tracked in #23.

---
  
## Test 1 completed — Private Full / Community Cloud, 2026-10-10

**Recorded reproducible evidence:** [Full timeline and validation matrix](https://github.com/TommyFive/qwen38-runpod-stack/blob/feature/19-optional-postload-ram-release/docs/INTEGRATION_FULL_COMMUNITY_20261010.md) (initially added on PR #19's feature branch, now merged into integration). The active test was performed from an isolated worktree pinned to exact commit `bffa632`, not the main integration checkout.

- **Cloud:** COMMUNITY explicitly requested; billed **$1.69/h**, matching RunPod GPU catalog Community price ($1.69/h) instead of Secure ($2.49/h). The CLI does not expose `cloudType`; mark this **rate-inferred, not direct-metadata verified**. Datacenter/region: **unknown**.
- **Measured stages:** Pod creation to downloaded Docker image **4m38s** (includes scheduler/platform delay); main+DFlash2 HF download **3m27.7s**; SGLang process to first authenticated completion **~104s**; end-to-end first inference **~9m59s**. OpenWebUI install **43.17s**; admin created and first observed `/api/config` 200 after **~10m44s**.
- **Optional RAM cleanup PR #19: PASS on paid GPU** with `MODEL_RAM_RELEASE_AFTER_LOAD=1`, `BENCHMARK=0`, `DEBUG=1`, `COLDSTART_TRACE=1`, explicitly supervised `MODEL_RAM_PEAK_FACTOR=1.75`. After authenticated inference, exactly three Safetensors blobs released **22.731 GiB**; authenticated inference passed again and private receipt `verified_after_inference` was created. The production default release flag **remains OFF**.
- **OpenWebUI:** app started, admin account auto-provisioned, `auth=true`, `enable_signup=false`; anonymous chat/user APIs **401**, anonymous signup **403**. Actual authenticated OpenWebUI login not validated due a blocked credential-bearing probe.
- **Network blocker:** local SGLang and OpenWebUI healthy, native Tailscale SSH works, private published RunPod endpoints **404**, but Tailscale Serve 443/8443 **timeouts** despite configured handlers. **[Issue #20](https://github.com/TommyFive/qwen38-runpod-stack/issues/20)**: release gate until end-to-end tailnet HTTPS works and TLS/auth is verified. No ACL change or port exposure was performed.
- **Unexpected RAM overhead:** after weights released, Full OpenWebUI `uv` package cache still consumed ~**7 GiB tmpfs** (`/dev/shm/qwen38-hf/xdg/uv/archive-v0`), in addition to ~0.9 GiB model cache metadata. Treat separately from model download footprint.
- **Clean termination:** exact Pod ID targeted-delete successful; RunPod 0 active, 0 USD/h; local 45-minute kill guard canceled. Detailed nonsecret RunPod and pod markers saved under `~/.runpod/qwen38-pr19-test1-*` as 0600 files.

**Consequences for release status:** RAM cleanup is **live validated** and PR #19 has been **merged into this integration branch** (commit `719681f`), with release switch default OFF. Private Full is **only partially accepted** because tailnet HTTPS and positive authenticated UI login remain open. No matched Secure Cloud run or 5-start cohort exists; the user's Community-vs-Secure speed hypothesis is **not yet confirmed**.

---

## Status nach echten GPU-Integrationstests — 2026-10-10

**Wichtig:** Der ursprüngliche Text unterhalb dieses Abschnitts war der
Testplan *vor* dem ersten GPU-Start. Die folgende Live-Matrix ist die
maßgebliche, aktuelle Bewertung. Tests liefen auf 1× RTX PRO 6000
($1.69/h), privatem Lean-Template syb1a3cqr6, DEBUG=1, RunPod Secrets
und ohne veröffentlichte Ports. Alle bisherigen Test-Pods wurden
gezielt beendet; 0 aktive Pods nach dem letzten Test.

| Bereich | Reale Evidenz | Stand |
|---|---|---|
| Native RunPod CLI | API aus geschützter nativer Konfiguration über SSH-MCP funktionsfähig | PASS |
| Alle vier Templates | In-place auf RunPod Secrets und aktuelle Helper migriert; beide privaten Port-Konfigurationen mehrfach unabhängig leer geprüft | PASS |
| Tailscale | Native SSH im Pod und Serve HTTPS API auf 443 nach Reparatur des noexec-/dev/shm-Problems | PASS Private Lean |
| Datenschutz | Pflicht-Bearer aktiv, authentifizierte Inferenz HTTP 200; fehlender/falscher Bearer HTTP 401; OpenWebUI Signup 403 und anonyme Chat-API 401 | TEILWEISE; positives WebUI-Login und HTTPS Serve #20 offen |
| RAM-only und cgroups | cgroup v1 live erkannt, 57.74 GiB freies tmpfs; Standard 2.5× benötigt 64.90 GiB und bricht korrekt ab, beaufsichtigte 1.75× benötigt 47.83 GiB und läuft | PASS als beaufsichtigter Test; Standard 2.5× absichtlich unverändert |
| Gewichtedownload | Hauptmodell 19.18 GiB + DFlash2 3.58 GiB in etwa 3m26s; tatsächlich gemessener tmpfs-Höchststand 22.777 GiB | PASS |
| VRAM und Inferenz | Hauptmodell 18.81 GB, Draft 3.73 GB im VRAM, KV/Mamba-Caches und CUDA Graphs initialisiert, erfolgreich authentifiziert inferiert | PASS |
| In-Pod Benchmark | 3 Messungen pro Workload nach Warm-up: Technical 135.8, Code 187.1, Code Edit 190.6 tok/s; TTFT circa 62–64 ms | PASS; nur Loopback/Einzelkohorte |
| Manuelle Gewichtsfreigabe | 0 offene mmap/FDs; 3 verifizierte Safetensors-Blobs (~22.73 GiB) entfernt; tmpfs von ~23 GiB auf ~31 MiB; VRAM unverändert; danach eine authentifizierte HTTP-200-Inferenz | PASS als manueller Proof-of-Concept |
| Optionale automatische RAM-Freigabe | PR #19 in Integration gemergt, Schalter MODEL_RAM_RELEASE_AFTER_LOAD=1, Default 0; privater Full-GPU-Test gab 22.731 GiB frei und inferierte danach erfolgreich | PASS für opt-in RAM-Livetest; weitere Betriebsmodi getrennt zu prüfen |
| Cold Start | Mehrere Image-Pulls beobachtet (ein Pull ~7m22s); Haupt- plus Draft-Download und GPU-Ladung separat gemessen | TEILWEISE; keine 5 unabhängigen Starts pro Kohorte |

### Offene Release-Gates (nicht als erledigt kennzeichnen)

- [x] Private SGLang ohne/falschen Bearer 401; RunPod öffentliche 8000/8080-Proxy-Adressen 404, auch nach App-Start. **Tailnet HTTPS 443/8443 weiterhin unerreichbar; fehlende eingehende ACL/Grants bestätigt**, Issue #20.
- [x] Private Full OpenWebUI erfolgreich gestartet, Admin angelegt, Signup 403 / anonymous Chat API 401 und auth=true. **Offen bleiben positives Login und erreichbares Tailnet-HTTPS 8443** (Issue #20).
- [ ] Öffentliche Full/Lean-Varianten gesondert überprüfen; positive Private-Lean-Ergebnisse beweisen deren Sicherheit nicht.
- [ ] Deaktivierte Schalter DEBUG=0 und COLDSTART_TRACE=0 live testen; **BENCHMARK=0 im Private-Full-Run mit Auto-RAM-Freigabe erfolgreich bestätigt**.
- [ ] SSD-Modus bewusst aktivieren und vergleichen; **niemals** stillschweigend RAM→SSD ausweichen.
- [x] PR #19 automatische RAM-Freigabe auf echter RTX PRO 6000 mit BENCHMARK=0 und authentifizierter Inferenz vor/nach Cleanup bestanden. Default OFF und SSD-negative Fall sind CI-verifiziert, noch nicht beide live geprüft. PR #19 in den Integrationsbranch gemergt; Release nach main weiter offen.
- [ ] Nach absichtlich freigegebenen Gewichten Audit/Diagnose für nicht mehr vorhandene Gewichtsdateien bewerten; Neustart/Reload erfordert erneuten Download.
- [ ] **POST-MERGE #23, not an integration release gate:** Independent starts across matched cloud/region/cache cohorts before interpreting median/p95.
- [ ] **POST-MERGE #23, not an integration release gate:** Fix misleading 0.0 MB/s probe (#5) and byte-weighted model download progress (#6).
- [ ] **ACCEPTED/POST-MERGE #18/#22, not an integration release gate:** project-only reaper/TTL/stop. **Only QWEN38 pods may exist in this account.** Legacy global reaper remains disabled for supervised integration tests; do not run `setup.sh` without considering its reaper LaunchAgent side effect.
- [x] PR #19 in den Integrationsbranch gemergt und PRs #12–#16 als durch #17 abgelöst geschlossen. **Offen:** Finale Sicherheits- und Release-Review von PR #17 vor dem Merge nach main.

### Operative Eckpunkte

Der Benchmark-Bericht liegt auf dem Mac mini unter
~/.runpod/qwen38-live04-benchmark.json (0600). Alle vier existierenden
Template-IDs wurden aktualisiert, nicht neu angelegt. Die ursprünglichen
PRs #12–#16 wurden als **superseded by PR #17** geschlossen, da alle
Feature-Commits im Integrationsbranch enthalten sind. Ihre Branches und
Kommentare bleiben erhalten; sie dürfen nicht separat nach main gemergt werden.

Beim Cleanup nur **runpodctl pod delete <EXAKTE_POD_ID>** verwenden.
qwen38fast stop / qwen38pi stop löschen in der aktuellen Version
potenziell alle Pods des RunPod-Kontos. **Der Account ist laut Besitzer
QWEN38-only**; dieses Risiko wird ausdrücklich akzeptiert und in #22
dokumentiert. Temporäre GPU-Tests haben weiterhin keine garantierte
automatische TTL. #18 ist künftig zu beheben, aber kein Merge-Blocker.

---


> **Integration branch:** `integration/issues-7-11-20261010`.
> This is a **partially GPU-verified** pre-release candidate. See the live
> status matrix above: important release gates remain open. Original PRs #12–#16 and `main`
> are preserved as branches, while the older feature PRs are closed as consolidated. All integration CI is mock/offline.

## What is combined

| Priority | Issue / original PR | End-to-end integration contract |
|---|---|---|
| 1 | #7 / #12 | Native Tailscale SSH userspace, HTTPS Serve, verified independent **portless** tailnet templates, public/loopback separation; no TCP/22 Serve forwarding. |
| 2 | #8 / #13 | Mandatory Bearer API key, preprovisioned authenticated OpenWebUI with signup disabled, credential redaction, private tmpfs runtime/UI state, fail-closed behavior. |
| 3 | #10 / #14 | Opt-in bounded authenticated in-pod workload and corrected remote client token accounting; report only non-sensitive bounded metrics. |
| 4 | #9 / #15 | Default verified RAM-only model+selected draft+HF/Xet cache; preflight checks tmpfs/cgroup/host memory, **no silent SSD fallback**, explicit SSD opt-in. |
| 5 | #11 / #16 | Credential-free chronological host/pod markers, authenticated loopback health, actual first successful inference probe; no performance flag changes. |

**Dependencies:** `qwen38fast` passes every relevant setting to RunPod
because `runpodctl --env` **replaces** the template environment; both CLI
and all four templates embed matching bootstrap and runtime helpers. `setup.sh`
installs the workers and `qwen38cold`. The integration tests verify the
cross-feature contracts together, not just individual PR behavior.

## 0. Preflight / local checkout (no paid pod created)

On the workstation from which the pod will be launched:

```bash
git fetch origin
git switch --detach origin/integration/issues-7-11-20261010
git log -1 --format='%h %s'
bash -n bin/qwen38fast scripts/bootstrap-sglang-openwebui.sh create-templates.sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

`git switch --detach` intentionally avoids moving an unrelated local branch.
Alternatively make a dedicated local tracking branch. The launcher needs
`runpodctl`, the local `rp` wrapper and RunPod credentials. Do **not**
paste bearer keys, HF tokens, Tailscale auth keys or web passwords into issues.

## 1. Installed tools and existing templates (historical setup notes)

```bash
./setup.sh
./create-templates.sh
```

`setup.sh` updates the current user's local commands and, on macOS,
may replace/reload qwen38 proxy/reaper LaunchAgents. **Do not enable the old
account-global reaper while Issue #18 is unresolved.** It is **not** a remote
VPS action. `create-templates.sh` calls RunPod to create **four** new
templates: public full/lean and portless tailnet full/lean. Retain the printed
IDs and set **all four** `QWEN38_TEMPLATE`, `QWEN38_TEMPLATE_PI`,
`QWEN38_TEMPLATE_TAILNET`, `QWEN38_TEMPLATE_TAILNET_PI` in your local
shell config/environment as required. **Verify the two private templates have
no `ports` or `port-labels` via actual RunPod template metadata/UI**
before renting a GPU; an offline mock alone cannot prove this.

For direct RunPod-UI pod creation, the current templates have **RunPod Secret
references** for `SGLANG_API_KEY`/`LLAMA_API_KEY`, `HF_TOKEN` and private
`TS_AUTHKEY`; these must resolve to existing RunPod Secrets at pod launch.
For OpenWebUI supply both
`WEBUI_ADMIN_EMAIL` and a strong `WEBUI_ADMIN_PASSWORD` (16+ characters).
Without a server API key startup **refuses** to expose an anonymous server;
without OpenWebUI admin provisioning the UI **stays off**. The four existing template IDs are retained and were updated in place with
`scripts/sync-runpod-secrets.py --refresh-helpers`; no replacements required.

## 2. Select a safe first cohort (paid launch is a separate decision)

Prefer **tailnet-only + lean API** first. The local machine must already
reach the tailnet; use a non-reusable/ephemeral tagged Tailscale key via RunPod Secret
`TS_AUTHKEY` with appropriate ACLs and MagicDNS HTTPS Serve capabilities. Supply
`QWEN38_TAILNET_DOMAIN` as the full `*.ts.net` tailnet DNS suffix. For
instance, after exporting the four new template IDs (not shown here),
set `QWEN38_NETWORK_MODE=tailnet` and run:

```bash
# RunPod Secret TS_AUTHKEY is already referenced by the private template.
# Do not paste a plaintext key into environment, command history or GitHub.
source ~/.config/qwen38/templates.env
export QWEN38_TAILNET_DOMAIN='YOUR-TAILNET.ts.net'

# Deliberately creates a paid RunPod pod. Un-comment only when ready.
# QWEN38_COLDSTART_TRACE=1 qwen38fast 2h --network tailnet --pi --storage ram --benchmark 2>&1 | tee "$HOME/qwen38-integrated-host.log"
```

The example starts a **paid** pod only when explicitly un-commented. All
changes to a remote production VPS or VPN host remain out of scope. Never
build/compile on Salty/Rusty/Cloudzy or another VPN production host.

**RAM caveat:** `MODEL_STORAGE=ram` is not just a cache preference. For
main **plus** DFlash2/DSpark draft, the helper requires space for 2.5× weight
inventory plus operating headroom, and a finite cgroup-v1 **or** cgroup-v2 memory limit and
sufficient `/dev/shm` free capacity. Many RunPod containers have **much less
shared memory than GPU VRAM**: the RAM preflight can refuse the launch before
HF download. It **never silently falls back** to persistent storage. On a
deliberate second cohort, use `--storage ssd` instead and record the storage
difference in cold-start measurements. Do **not** silently lower safety margins or change tmpfs mounts solely to
bypass a failure; the completed GPU run deliberately opted into a measured
1.75× factor, while the 2.5× production default remains unchanged.

**WebUI second cohort:** Repeat a separate controlled full-stack run without
`--pi`. The launcher creates/reuses a strong local password at
`~/.runpod/qwen38-webui-password` (0600); read it only on your local
workstation. Confirm the HTTPS tailnet OpenWebUI on port 8443 rejects
anonymous chat and `/api/config` confirms authentication.

## 3. Evidence and security checks on the *new* pod

- Confirm Tailscale native SSH works and its tailnet IP/name is present.
  RunPod public TCP/22 must **not** be published in private mode; Serve 443
  routes authenticated SGLang and 8443 optional authenticated OpenWebUI.
  Explicitly confirm RunPod's public `-8000.proxy.runpod.net`/`-8080`
  endpoints do **not** work on the portless template.
- Verify authenticated `/v1/models` succeeds and the same path **without**
  Bearer credentials is denied. Do the same for an anonymous OpenWebUI chat
  API request; an accessible login page is insufficient evidence.
- `/workspace/smoke-storage.sh` audits cache mount/symlink location, actual
  filesystem space and authenticated SGLang readiness. Model and selected
  draft must resolve to the selected storage root. Record actual `df`,
  `/proc/self/mountinfo` and cgroup budgets, but do **not** post secrets.
- `/dev/shm/qwen38-runtime/bootstrap.log` contains UTC/monotonic events
  (`QWEN38_COLDSTART`); with `DEBUG=1`, sanitized private SGLang logs are
  under `/dev/shm/qwen38-runtime/sglang.log`. Default `DEBUG=0` discards
  child logs. The `main_download_*` timing currently covers **main + selected
  draft download**, not the main model alone.
- `BENCHMARK=1` runs three fixed workloads (one warmup plus N measured per
  workload) with Bearer auth against **127.0.0.1:8000** and stores
  `/dev/shm/qwen38-benchmark.json` and
  `/dev/shm/qwen38-runtime/benchmark.log`. It must not restart serving.
  `qwen38bench` on the workstation measures a **different** external
  network path; do not compare raw tokens/s directly.
- Repeat `BENCHMARK=0` and disabled `COLDSTART_TRACE=0` to verify opt-outs.
  Cold trace host `first_inference_ok` is more stringent than
  `api_models_ready`; never label mere API readiness as TTFI.

## 4. Record and interpret cold-start data

Save locally the launcher's stdout+stderr log and an **unredacted only if
you accept its sensitivity** copy of the already-redacted bootstrap events.
For a controlled example using a bootstrap log copied from your *test pod*:

```bash
python3 bin/qwen38cold report \
  --host "$HOME/qwen38-integrated-host.log" \
  --bootstrap "$HOME/qwen38-integrated-bootstrap.log" \
  --label integration-01 --cloud community --region UNKNOWN \
  --gpu pro6000 --storage ram --cache unknown --startup cold \
  --output "$HOME/qwen38-integration-01.json"
python3 bin/qwen38cold summary "$HOME"/qwen38-integration-*.json
```

Use truthful region/cache classification. No platform scheduling/image-pull
timing is inferred by the bootstrap; collect independently corroborated
RunPod UI/API evidence before adding `--platform`. Aim for **at least five
independent starts per cohort** before interpreting median/p95. Full GPU
smoke, memory sizing, direct-template visibility, real OpenWebUI provisioning,
TLS/Serve reachability, and true cold-start timings are **not fully verified by CI or the single paid GPU cohort**.

## 5. Cleanup / expected release gates

Only terminate a paid pod deliberately after saving measurements. In the
current stack **`qwen38fast stop` deletes *all* pods in the RunPod account
returned by `runpodctl pod list`**, not just the current integration pod.
Use a targeted `runpodctl pod delete <exact-pod-id>` when other pods must
survive. Remove per-test ephemeral Tailscale nodes/keys via tailnet management
as appropriate.

Keep **PR #17 in Draft** until HTTPS Serve issue #20 and the remaining
functional, authentication, storage and template release gates pass.
Account-wide stop/reaper TTL (#18/#22) is **explicitly accepted/deferred**
under the single-project RunPod account assumption. The current cold-start
instrumentation is accepted for this release; further performance and
observability optimizations (#23, #5, #6, #11) are **non-blocking**.
Original feature PRs #12–#16 are already consolidated and closed. CI passing is necessary but not sufficient.

## Private-template port safety correction

RunPod **defaults to 8888/http and 22/tcp** if the create request omits ports.
The updated template creator explicitly calls REST PATCH with `{"ports":[]}`
after creation, then re-reads the template and fails closed (deleting a newly
created unsafe template on failure). `qwen38fast --network tailnet`
independently GETs the selected live template metadata before paid pod creation
and refuses templates with any published ports, missing ports metadata, or
a mode other than `tailnet`.

To repair the **existing** private template IDs without recreating the four
templates, use the native protected RunPod CLI credentials (no Keychain unlock required):

```bash
python3 scripts/private-template-ports.py repair "$QWEN38_TEMPLATE_TAILNET"
python3 scripts/private-template-ports.py repair "$QWEN38_TEMPLATE_TAILNET_PI"
python3 scripts/private-template-ports.py verify "$QWEN38_TEMPLATE_TAILNET"
python3 scripts/private-template-ports.py verify "$QWEN38_TEMPLATE_TAILNET_PI"
```

If RunPod rejects or ignores explicit empty arrays, **do not deploy privately**.
The CLI itself does not support setting an empty ports list.
