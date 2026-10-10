# Integrated RunPod GPU smoke — issues #7, #8, #9, #10, #11

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
| Datenschutz | Pflicht-Bearer konfiguriert, positive authentifizierte Inferenz HTTP 200, DEBUG=1 inklusive Log-Redaktion und RAM-Laufzeit | TEILWEISE; negative Zugangstests und Full-UI offen |
| RAM-only und cgroups | cgroup v1 live erkannt, 57.74 GiB freies tmpfs; Standard 2.5× benötigt 64.90 GiB und bricht korrekt ab, beaufsichtigte 1.75× benötigt 47.83 GiB und läuft | PASS als beaufsichtigter Test; Standard 2.5× absichtlich unverändert |
| Gewichtedownload | Hauptmodell 19.18 GiB + DFlash2 3.58 GiB in etwa 3m26s; tatsächlich gemessener tmpfs-Höchststand 22.777 GiB | PASS |
| VRAM und Inferenz | Hauptmodell 18.81 GB, Draft 3.73 GB im VRAM, KV/Mamba-Caches und CUDA Graphs initialisiert, erfolgreich authentifiziert inferiert | PASS |
| In-Pod Benchmark | 3 Messungen pro Workload nach Warm-up: Technical 135.8, Code 187.1, Code Edit 190.6 tok/s; TTFT circa 62–64 ms | PASS; nur Loopback/Einzelkohorte |
| Manuelle Gewichtsfreigabe | 0 offene mmap/FDs; 3 verifizierte Safetensors-Blobs (~22.73 GiB) entfernt; tmpfs von ~23 GiB auf ~31 MiB; VRAM unverändert; danach eine authentifizierte HTTP-200-Inferenz | PASS als manueller Proof-of-Concept |
| Optionale automatische RAM-Freigabe | Separater Draft PR #19 mit Schalter MODEL_RAM_RELEASE_AFTER_LOAD=1, Standard 0; CI grün | LIVE-REGRESSION OFFEN |
| Cold Start | Mehrere Image-Pulls beobachtet (ein Pull ~7m22s); Haupt- plus Draft-Download und GPU-Ladung separat gemessen | TEILWEISE; keine 5 unabhängigen Starts pro Kohorte |

### Offene Release-Gates (nicht als erledigt kennzeichnen)

- [ ] Private Endpunkte **ohne** Bearer authentifiziert ablehnen; öffentliches RunPod-Proxy-Routing auf portlosen Pods explizit negativ testen.
- [ ] Vollständige OpenWebUI-Kohorte im privaten Full-Template inklusive Admin-Vorprovisionierung, deaktiviertem Signup und anonymem Chat-Ablehnungstest.
- [ ] Öffentliche Full/Lean-Varianten gesondert überprüfen; positive Private-Lean-Ergebnisse beweisen deren Sicherheit nicht.
- [ ] Deaktivierte Schalter DEBUG=0, BENCHMARK=0 und COLDSTART_TRACE=0 live testen.
- [ ] SSD-Modus bewusst aktivieren und vergleichen; **niemals** stillschweigend RAM→SSD ausweichen.
- [ ] PR #19 separat live testen (automatischer Cleanup nach erfolgreicher Inferenz/Benchmark, kein Cleanup mit Default 0 oder SSD), bevor er in die Integration übernommen wird.
- [ ] Nach absichtlich freigegebenen Gewichten Audit/Diagnose für nicht mehr vorhandene Gewichtsdateien bewerten; Neustart/Reload erfordert erneuten Download.
- [ ] Fünf unabhängige Starts pro zu vergleichender Kohorte, Region/Cache/Host klassifizieren; Median/p95 erst danach interpretieren.
- [ ] Fehlleitende Netzwerkprobe mit 0.0 MB/s und Download-Fortschrittsanzeige in GiB/ETA beheben (separat erfasst).
- [ ] Sicherer, ausschließlich QWEN38-Pods erfassender Reaper und TTL (Issue #18); globalen Reaper **nicht** aktivieren.
- [ ] Finale Review aller ursprünglichen PRs und des integrierten Draft PR #17, dann erst Merge nach Freigabe.

### Operative Eckpunkte

Der Benchmark-Bericht liegt auf dem Mac mini unter
~/.runpod/qwen38-live04-benchmark.json (0600). Alle vier existierenden
Template-IDs wurden aktualisiert, nicht neu angelegt. Die ursprünglichen
Feature-Branches #12–#16 sind als eigenständige Drafts **nicht**
identisch mit dem getesteten Integrationsstand; deren PR-Diskussionen
müssen die Integrationserkenntnisse ausdrücklich referenzieren.

Beim Cleanup nur **runpodctl pod delete <EXAKTE_POD_ID>** verwenden.
qwen38fast stop / qwen38pi stop löschen in der aktuellen Version
potenziell alle Pods des RunPod-Kontos. Temporäre GPU-Tests haben
keine garantierte automatische TTL, solange Issue #18 offen ist.

---


> **Integration branch:** `integration/issues-7-11-20261010`.
> This is a **partially GPU-verified** pre-release candidate. See the live
> status matrix above: important release gates remain open. Original PRs #12–#16 and `main`
> remain independent; see the PR audit. All integration CI is mock/offline.

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

## 1. Install user tools and create *new* templates

```bash
./setup.sh
./create-templates.sh
```

`setup.sh` updates the current user's local commands and, on macOS,
replaces/reloads its qwen38 proxy/reaper LaunchAgents. It is **not** a remote
VPS action. `create-templates.sh` calls RunPod to create **four** new
templates: public full/lean and portless tailnet full/lean. Retain the printed
IDs and set **all four** `QWEN38_TEMPLATE`, `QWEN38_TEMPLATE_PI`,
`QWEN38_TEMPLATE_TAILNET`, `QWEN38_TEMPLATE_TAILNET_PI` in your local
shell config/environment as required. **Verify the two private templates have
no `ports` or `port-labels` via actual RunPod template metadata/UI**
before renting a GPU; an offline mock alone cannot prove this.

For direct RunPod-UI pod creation, the new templates deliberately contain
**no credentials**. Inject a nonempty `SGLANG_API_KEY`, `HF_TOKEN` when
required, `TS_AUTHKEY` for private mode, and for OpenWebUI both
`WEBUI_ADMIN_EMAIL` and a strong `WEBUI_ADMIN_PASSWORD` (16+ characters).
Without a server API key startup **refuses** to expose an anonymous server;
without OpenWebUI admin provisioning the UI **stays off**. The four existing template IDs are retained and were updated in place with
`scripts/sync-runpod-secrets.py --refresh-helpers`; no replacements required.

## 2. Select a safe first cohort (paid launch is a separate decision)

Prefer **tailnet-only + lean API** first. The local machine must already
reach the tailnet; use a non-reusable/ephemeral tagged Tailscale key with the
appropriate ACLs and MagicDNS HTTPS Serve capabilities. Supply
`QWEN38_TAILNET_DOMAIN` as the full `*.ts.net` tailnet DNS suffix. For
instance, after exporting the four new template IDs (not shown here),
set `QWEN38_NETWORK_MODE=tailnet` and run:

```bash
# Local shell; input hidden. DO NOT echo the key or put it in command history.
read -r -s -p 'Tailscale auth key: ' TS_AUTHKEY; printf '\n'
export TS_AUTHKEY
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
difference in cold-start measurements. Do **not** lower safety margins or
change tmpfs mounts solely to bypass a failure.

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

Keep this PR in **Draft**, and original feature PRs open, until the paid
GPU security + RAM/SSD correctness + benchmark + cold-start end-to-end
smoke has been verified. CI passing is necessary but not sufficient.

## Private-template port safety correction

RunPod **defaults to 8888/http and 22/tcp** if the create request omits ports.
The updated template creator explicitly calls REST PATCH with `{"ports":[]}`
after creation, then re-reads the template and fails closed (deleting a newly
created unsafe template on failure). `qwen38fast --network tailnet`
independently GETs the selected live template metadata before paid pod creation
and refuses templates with any published ports, missing ports metadata, or
a mode other than `tailnet`.

To repair the **existing** private template IDs without recreating the four
templates, run locally with Keychain credentials sourced:

```bash
python3 scripts/private-template-ports.py repair "$QWEN38_TEMPLATE_TAILNET"
python3 scripts/private-template-ports.py repair "$QWEN38_TEMPLATE_TAILNET_PI"
python3 scripts/private-template-ports.py verify "$QWEN38_TEMPLATE_TAILNET"
python3 scripts/private-template-ports.py verify "$QWEN38_TEMPLATE_TAILNET_PI"
```

If RunPod rejects or ignores explicit empty arrays, **do not deploy privately**.
The CLI itself does not support setting an empty ports list.
