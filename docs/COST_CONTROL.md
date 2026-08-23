# Cost control on RunPod

On 2026-08-15 two forgotten pods ran for 24 hours doing nothing. Everything here
exists because of that.

## The rule

**Never create a pod without a shutdown timer. No exception, not even "just a
quick test".** `qwen38fast` sets it itself. If you create a pod by hand, use `rp`:

```bash
rp pod create ...                  # sets --terminate-after to now+1h
RUNPOD_MAX_AGE_HOURS=6 rp pod create ...   # longer window
rp 6h pod create ...                       # same, shorter
```

`rp` lives in `~/.local/bin/rp` and passes everything through to `runpodctl`
unchanged. Only on `pod create` does it check whether `--terminate-after` or
`--stop-after` is present, and adds the timer otherwise.

If you call `runpodctl pod create` directly, add the flag by hand:

```bash
runpodctl pod create ... --terminate-after "$(date -u -v+1H '+%Y-%m-%dT%H:%M:%SZ')"
```

## The three layers

| Layer | What | Fires when |
|---|---|---|
| 1. `--terminate-after` | server-side at RunPod | always, even with the Mac asleep or the session gone |
| 2. `rp` wrapper | sets layer 1 automatically | you forget the flag |
| 3. `runpod-reaper` | LaunchAgent, every 10 min, kills anything over 1h | pod came from the web console or elsewhere |

Layer 1 is the only one that works without a running Mac, so it's mandatory.
Conversely: **layer 1 can't be verified.** `pod get` returns no `terminateAfter`,
so you never actually see whether RunPod stored the timer. That's exactly why
layer 3 stays active instead of trusting the timer.

**To keep a pod alive on purpose:** start its name with `keep-`, then the reaper
leaves it alone. The layer-1 timer still applies and must be set explicitly. `rp`
does both automatically once the window is longer than one hour.

Check the reaper by hand:

```bash
RUNPOD_REAPER_DRY_RUN=1 runpod-reaper && cat ~/.runpod/reaper.log
```

The reaper only writes to the log on errors or kills. A quiet log means all is
well, not that it isn't running. Whether it runs shows in
`launchctl list | grep runpod`.

## What RunPod can't do

**There is no global auto-terminate setting.** An idle timeout exists only for
serverless endpoints, not for pods, neither in the CLI nor in account settings.
`runpodctl user` is read-only. The only account-wide cap is the spend limit, but
that only bites once the month is already burned.

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
