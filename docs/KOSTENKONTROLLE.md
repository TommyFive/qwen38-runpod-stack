# Kostenkontrolle auf RunPod

Am 15.08.2026 liefen zwei vergessene Pods 24 Stunden ohne Nutzung durch. Alles hier existiert
wegen dieses Vorfalls.

## Die Regel

**Es wird nie ein Pod ohne Abschalttimer angelegt. Keine Ausnahme, auch nicht "nur kurz zum
Testen".** `qwen38fast` setzt ihn selbst. Wer von Hand einen Pod anlegt, nimmt `rp`:

```bash
rp pod create ...                  # setzt --terminate-after auf jetzt+1h
RUNPOD_MAX_AGE_HOURS=6 rp pod create ...   # längeres Fenster
rp 6h pod create ...                       # dasselbe kürzer
```

`rp` liegt in `~/.local/bin/rp` und reicht alles unverändert an `runpodctl` durch. Nur bei
`pod create` prüft es, ob `--terminate-after` oder `--stop-after` dabei ist, und hängt sonst
den Timer an.

Wird `runpodctl pod create` direkt genutzt, muss das Flag von Hand mit rein:

```bash
runpodctl pod create ... --terminate-after "$(date -u -v+1H '+%Y-%m-%dT%H:%M:%SZ')"
```

## Die drei Schichten

| Schicht | Was | Greift wenn |
|---|---|---|
| 1. `--terminate-after` | serverseitig bei RunPod | immer, auch bei zugeklapptem Mac oder beendeter Session |
| 2. `rp`-Wrapper | setzt Schicht 1 automatisch | man vergisst das Flag |
| 3. `runpod-reaper` | LaunchAgent, alle 10 Min, killt alles über 1h | Pod kam aus der Web-Konsole oder von woanders |

Schicht 1 ist die einzige, die ohne laufenden Mac funktioniert, deshalb ist sie Pflicht.
Umgekehrt gilt: **Schicht 1 lässt sich nicht überprüfen.** `pod get` gibt kein `terminateAfter`
zurück, man sieht also nie, ob RunPod den Timer wirklich gespeichert hat. Genau deshalb bleibt
Schicht 3 aktiv, statt sich auf den Timer zu verlassen.

**Soll ein Pod bewusst länger leben:** Namen mit `keep-` beginnen lassen, dann rührt der Reaper
ihn nicht an. Der Timer aus Schicht 1 gilt trotzdem und muss dann explizit gesetzt werden.
`rp` macht beides automatisch, sobald das Fenster länger als eine Stunde ist.

Reaper von Hand prüfen:

```bash
RUNPOD_REAPER_DRY_RUN=1 runpod-reaper && cat ~/.runpod/reaper.log
```

Der Reaper schreibt nur bei Fehlern oder Kills ins Log. Ein stilles Log heißt, dass alles in
Ordnung ist, nicht dass er nicht läuft. Ob er läuft, zeigt `launchctl list | grep runpod`.

## Was RunPod nicht kann

**Eine globale Auto-Terminate-Einstellung gibt es nicht.** Ein Idle-Timeout existiert nur für
Serverless-Endpoints, für Pods weder in der CLI noch in den Account-Settings. `runpodctl user`
ist read-only. Der einzige kontoweite Deckel ist das Spend-Limit, aber das greift erst, wenn der
Monat schon verbrannt ist.

## Preise, Stand 22.08.2026

Aus der GraphQL-API des Kontos, Feld `lowestPrice.uninterruptablePrice`. Das ist der
**günstigste** on-demand-Preis für die Karte, also der Community-Cloud-Preis, wo Community
verfügbar ist. Secure liegt darüber: die RTX PRO 6000 lief am 22.08.2026 in Secure für
2,09 USD/h gegen 1,69 hier in der Tabelle, also rund 24 Prozent Aufschlag.

| GPU | VRAM | USD/h | taugt für NVFP4 |
|---|---|---|---|
| RTX 3090 | 24 GB | 0,22 | nein |
| RTX 4090 | 24 GB | 0,34 | nein |
| RTX 5090 | 32 GB | 0,69 | ja |
| RTX PRO 6000 | 96 GB | 1,69 | ja |
| H100 PCIe | 80 GB | 1,99 | nein, SM90 |
| H100 SXM | 80 GB | 2,69 | nein, SM90 |
| H200 SXM | 141 GB | 3,59 | nein, SM90 |
| B200 | 180 GB | 5,98 | ja |
| B300 | 288 GB | 6,94 | ja |

Community ist nicht immer verfügbar. `qwen38fast` versucht Community zuerst und fällt
automatisch auf Secure zurück, dann gilt der höhere Preis.

Preise selbst abfragen:

```bash
KEY=$(python3 -c "import re;print(re.search(r\"apikey = '([^']+)'\",open('$HOME/.runpod/config.toml').read()).group(1))")
curl -s -X POST "https://api.runpod.io/graphql?api_key=$KEY" -H 'Content-Type: application/json' \
  -d '{"query":"query { gpuTypes { displayName memoryInGb lowestPrice(input:{gpuCount:1}) { uninterruptablePrice } } }"}'
```

`runpodctl gpu list` zeigt Verfügbarkeit und Stock-Status, aber **keine Preise**.

## Laufende Kosten prüfen

```bash
qwen38fast status                  # Pods plus Guthaben plus aktuelle Rate
runpodctl pod list -a              # auch beendete Pods
runpodctl network-volume list      # Volumes kosten auch ohne laufenden Pod
```

Beendete Pods (`desiredStatus: EXITED`) kosten nichts, solange kein Volume dranhängt.
Network-Volumes kosten dauerhaft, unabhängig von jedem Pod.
