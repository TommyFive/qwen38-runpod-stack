# qwen38-runpod-stack

Ein Befehl startet Qwen3.8-27B (abliterated, NVFP4) auf einer gemieteten
Blackwell-GPU bei RunPod und bindet es lokal an einen Coding-Agenten wie
[pi](https://pi.dev) an. Feste lokale URL, automatischer Abschalttimer, kein
manuelles Nachtragen von Pod-Adressen.

Gemessen am 23.08.2026: rund 150 tok/s auf einer RTX PRO 6000 mit SGLang plus
DFlash2-Spekulation. Details in `docs/MAX_TPS_QWEN38.md`.

## Was drin ist

| Datei | Zweck |
|---|---|
| `bin/qwen38fast` | Voll-Stack: SGLang-API plus OpenWebUI, startet und wartet bis nutzbar |
| `bin/qwen38pi` | Schlank: nur die SGLang-API, für pi. Kein OpenWebUI, schneller fertig |
| `bin/qwen38bench` | misst Decode-Rate, TTFT und Accept-Länge (mit Warmlauf) |
| `bin/qwen38-proxy` | lokaler Proxy auf `127.0.0.1:8388`, zeigt immer auf den laufenden Pod |
| `bin/rp` | runpodctl-Wrapper, hängt jedem Pod einen Abschalttimer an |
| `bin/runpod-reaper` | LaunchAgent-Backstop, killt vergessene Pods nach 1h |
| `scripts/bootstrap-sglang-openwebui.sh` | läuft im Pod, lädt Gewichte und startet SGLang (plus optional OpenWebUI) |
| `launchagents/*.template` | macOS-LaunchAgents für Proxy und Reaper, `__HOME__` wird beim Setup gefüllt |
| `pi/models.runpod.json` | der Provider-Block für `~/.pi/agent/models.json` |
| `create-templates.sh` | legt die zwei RunPod-Templates an und nennt die IDs |
| `setup.sh` | installiert alles für den aktuellen Nutzer |

## Voraussetzungen

- `runpodctl` installiert und eingeloggt
- HF-Token in `~/.cache/huggingface/token` (das Modell selbst ist nicht gated,
  der Token beschleunigt aber die Downloads)
- RunPod-SSH-Key in `~/.runpod/ssh/runpodctl-ssh-key` (nur für den OpenWebUI-Neustart im Voll-Stack)
- Python 3, `base64`, `curl`
- Für pi: [pi](https://pi.dev) installiert

## Installation

```bash
./setup.sh                      # bin nach ~/.local/bin, LaunchAgents laden
./create-templates.sh           # RunPod-Templates anlegen, gibt zwei IDs aus
export QWEN38_TEMPLATE=<id>      # die Voll-ID
export QWEN38_TEMPLATE_PI=<id>   # die pi-ID
# den Block aus pi/models.runpod.json in ~/.pi/agent/models.json übernehmen
```

Die Template-IDs kann man auch fest in `bin/qwen38fast` eintragen, dann braucht
es die Env-Variablen nicht.

## Benutzung

Für pi, der schlanke Weg:

```bash
qwen38pi                                 # startet, fertig sobald die API antwortet
pi --model runpod/qwen38-uncensored      # damit arbeiten
qwen38pi stop                            # Pod aus
```

Mit Weboberfläche:

```bash
qwen38fast                               # startet, öffnet OpenWebUI im Browser
qwen38fast status                        # was läuft, was kostet es
qwen38fast stop
```

## Wie es zusammenhängt

`qwen38fast` startet den Pod, schreibt die Pod-ID nach `~/.runpod/current-pod`
und legt beim ersten Lauf einen API-Key in `~/.runpod/qwen38.key` an. Der Proxy
liest beides und leitet pi automatisch auf den gerade laufenden Pod. Die
Pod-URL wechselt bei jedem Start, die lokale Adresse `127.0.0.1:8388` bleibt
gleich. Läuft kein Pod, antwortet der Proxy mit 503.

## Kostenkontrolle

Drei Schichten verhindern vergessene Pods: der serverseitige `--terminate-after`
Timer (setzt `rp`), der `rp`-Wrapper selbst, und der `runpod-reaper` als
LaunchAgent. Details in `docs/KOSTENKONTROLLE.md`.

## Sicherheit

Keine Keys, Tokens oder persönlichen Pfade im Repo. `qwen38fast` erzeugt den
API-Key lokal und übergibt ihn an SGLang, damit der öffentlich erreichbare
Pod-Port nicht offen im Netz steht. Die `.gitignore` hält Keys, Tokens und den
Pod-Zustand draußen.

## Modell

Standard ist `sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4`, ein uniform
`nvfp4-pack-quantized` Checkpoint. Andere gehen über `--model` oder die
`QWEN38_MODEL`-Variable. Warum nicht jeder NVFP4-Checkpoint mit SGLang läuft,
steht in `docs/MAX_TPS_QWEN38.md`.

## Lizenz

MIT, siehe LICENSE. Das Modell selbst steht unter Apache 2.0.
