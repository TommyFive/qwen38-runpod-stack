# Cost control on RunPod

On 2026-08-15 two forgotten pods ran for 24 hours doing nothing. Everything here
exists because of that.

## Accepted account scope and residual risk (2026-10-10)

**PR #17 merge decision: documented non-blocker, not a resolved safety fix.**
The owner confirmed the account is presently dedicated to QWEN38 pods only.
This is a **precondition**, not an enforced software invariant. If unrelated
workloads are ever added, the existing commands can become destructive.
Track accepted limitation in [#22](https://github.com/TommyFive/qwen38-runpod-stack/issues/22)
and proper future implementation in [#18](https://github.com/TommyFive/qwen38-runpod-stack/issues/18).

### What the current code actually does

| Component | Actual behavior | Limitation |
|---|---|---|
| `qwen38fast stop` / `qwen38pi stop` | Uses `runpodctl pod list` and deletes **all returned Pod IDs** | Account-wide, not current-pod-only |
| `bin/rp` | Adds a server-side `--terminate-after` *only if supported by CLI* | RunPod CLI 2.15.0 on Mac mini lacks this option; requested `2h`/`4h` is **not guaranteed** |
| `bin/runpod-reaper` | Enumerates account pods and deletes those past global default 1h age, except `keep-` names | Account-wide, not a per-pod TTL; may conflict with 4h request |
| `setup.sh` | Installs/loads proxy **and legacy reaper** LaunchAgents on macOS | Do not assume reaper is safely scoped or currently running |
| Mac mini at audit | Reaper LaunchAgent **absent**; `runpodctl 2.15.0` noninteractive API worked | No active local reaper protection demonstrated |

`RUNPOD_MAX_AGE_HOURS` and `rp 6h ...` are requested runtime windows;
they are **not an SLA, auto-delete guarantee or billing limit** in the
installed CLI/runtime configuration. A Mac-side timer can also fail when the
machine sleeps, loses connectivity or cannot authenticate.

### Current operating rule for paid integration tests

1. Use this RunPod account **exclusively** for QWEN38; avoid account-global
   cleanup entirely if any other project begins using the account.
2. Before renting, agree on test scope, hourly rate, maximum intended time and
   exact Pod ID. Require explicit paid-run authorization.
3. Keep the **legacy global reaper disabled** during supervised integration
   tests. Be aware that running `./setup.sh` can reactivate it.
4. Monitor actual spend and Pod state. Terminate only the **verified exact ID**
   with `runpodctl pod delete <exact-pod-id>` or in the RunPod dashboard.
   Recheck active pods and billing after cleanup.
5. A local/manual short timer is not independent shutdown assurance; do not
   rely on one to prevent runaway charges.

### Post-merge engineering

[#18](https://github.com/TommyFive/qwen38-runpod-stack/issues/18)
tracks a project-owned ID registry, atomic per-pod deadlines, headless
authentication, safe stop, read-only identity verification before delete and
observable failures. It is explicitly **deferred** for PR #17 under the
owner's single-project-account assumption. A later change to the account
usage invalidates that assumption and requires reassessment before operation.

## Prices, as of 2026-08-22

From the account's GraphQL API, field `lowestPrice.uninterruptablePrice`. That's
the **cheapest** on-demand price for the card, i.e. the Community Cloud price
where Community is available. Secure is higher: the RTX PRO 6000 ran on
2026-08-22 in Secure for 2.09 USD/h against 1.69 in the table below, about a 24%
markup.

| GPU | VRAM | USD/h | good for NVFP4 |
|---|---|---|---|
| RTX 3090 | 24 GB | 0.22 | no |
| RTX 4090 | 24 GB | 0.34 | no |
| RTX 5090 | 32 GB | 0.69 | yes |
| RTX PRO 6000 | 96 GB | 1.69 | yes |
| H100 PCIe | 80 GB | 1.99 | no, SM90 |
| H100 SXM | 80 GB | 2.69 | no, SM90 |
| H200 SXM | 141 GB | 3.59 | no, SM90 |
| B200 | 180 GB | 5.98 | yes |
| B300 | 288 GB | 6.94 | yes |

Community isn't always available. `qwen38fast` tries Community first and falls
back to Secure automatically, at which point the higher price applies.

Query prices yourself:

```bash
KEY=$(python3 -c "import re;print(re.search(r\"apikey = '([^']+)'\",open('$HOME/.runpod/config.toml').read()).group(1))")
curl -s -X POST "https://api.runpod.io/graphql?api_key=$KEY" -H 'Content-Type: application/json' \
  -d '{"query":"query { gpuTypes { displayName memoryInGb lowestPrice(input:{gpuCount:1}) { uninterruptablePrice } } }"}'
```

`runpodctl gpu list` shows availability and stock status but **no prices**.

## Check running costs

```bash
qwen38fast status                  # pods plus balance plus current rate
runpodctl pod list -a              # including exited pods
runpodctl network-volume list      # volumes cost even without a running pod
```

Exited pods (`desiredStatus: EXITED`) cost nothing as long as no volume is
attached. Network volumes cost continuously, independent of any pod.
