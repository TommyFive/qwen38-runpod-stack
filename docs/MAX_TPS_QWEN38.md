# Qwen3.8-27B abliterated auf RunPod, auf maximale Decode-Rate ausgelegt

Stand 22.08.2026. Alles hier ist belegt, Quellen stehen an jeder Zahl.

## Kurzfassung

```bash
qwen38fast                 # RTX PRO 6000 Blackwell, NVFP4, DFlash2, 4h Fenster
qwen38bench                # misst, was tatsächlich rauskommt
qwen38fast stop
```

Stack: SGLang auf `lmsysorg/sglang:dev-qwen38-27b-dflash2`, Modell
`sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4`, Draft `incoai/Qwen3.8-27B-DFlash2`,
RunPod Template `bxwo0swnm9`.

## Die vier Entscheidungen und warum

### 1. GPU: RTX PRO 6000 Blackwell 96GB, 1,69 USD/h

| Karte | VRAM | RunPod on-demand | taugt für NVFP4 |
|---|---|---|---|
| RTX 5090 | 32 GB | 0,69 USD/h | ja, aber Kontext gedeckelt |
| **RTX PRO 6000** | **96 GB** | **1,69 USD/h** | **ja, voller 262K-Kontext** |
| H100 SXM | 80 GB | 2,69 USD/h | nein, SM90 hat keine FP4-Tensorcores |
| H200 SXM | 141 GB | 3,59 USD/h | nein, gleicher Grund |
| B200 | 180 GB | 5,98 USD/h | ja, nicht in der Cookbook-Matrix |
| B300 | 288 GB | 6,94 USD/h | ja, Cookbook-Zelle vorhanden |

NVFP4 braucht Blackwell. Damit fallen H100 und H200 für den schnellen Pfad raus,
egal wie viel sie kosten. RTX PRO 6000 und RTX 5090 teilen sich den GB202-Chip und
damit rund 1,79 TB/s Bandbreite, die PRO 6000 hat aber dreimal so viel VRAM, also
passt der volle Kontext rein. Der SGLang-Cookbook validiert genau diese Karte
durchgemessen, die B200 steht gar nicht in der Matrix.

### 2. Checkpoint: uniform NVFP4, nicht mixed-precision

Der populärste abliterierte Build, `orcarouter/Qwen3.8-27B-Uncensored-NVFP4`, ist
**für SGLang unbrauchbar**: sein `format` ist `mixed-precision`, und SGLang lädt
solche compressed-tensors-Checkpoints still **komplett unquantisiert**, ohne das
zu melden (sgl-project/sglang#32736, offen). Der gesamte FP4-Vorteil wäre weg, und
zwar unbemerkt. Dazu ist das Repo gated, der HF-Token hat aktuell keinen Zugriff
(HTTP 403 auf `config.json`).

Genommen wird deshalb:

| Checkpoint | Format | Größe | MTP-Head | gated |
|---|---|---|---|---|
| `sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4` | `nvfp4-pack-quantized` | 20,6 GB | ja, BF16 separat | nein |
| `sakamakismile/Qwen3.8-27B-AEON-ULTIMATE-UNCENSORED-NVFP4` | `nvfp4-pack-quantized` | 20,6 GB | ja | nein |
| `orcarouter/Qwen3.8-27B-Uncensored-NVFP4` | `mixed-precision` | 23,4 GB | ja | **ja, 403** |
| `orcarouter/Qwen3.8-27B-Uncensored-FP8` | block-FP8 | 28,5 GB | ja | ja, Zugriff da |

Die Abliteration stammt von huihui-ai, `sakamakismile` hat nur quantisiert.
Uniform pack-quantized umgeht den SGLang-Bug.

Will man trotzdem den orcarouter-NVFP4: Bedingungen auf der Modellseite akzeptieren
und **vLLM statt SGLang** nehmen, dort ist der mixed-precision-Pfad der dokumentierte:

```bash
--speculative-config '{"method":"mtp","num_speculative_tokens":2}'
# und NICHT --quantization oder --kv-cache-dtype setzen, das steht in config.json
```

### 3. Engine: SGLang, nicht vLLM

Für denselben Checkpoint auf derselben Karte liefert SGLang mit trainierten
Draft-Modellen deutlich mehr als vLLMs MTP. Gemessene Werte aus dem Cookbook
(RTX 5090, ISL 8192 / OSL 1024, Nebenläufigkeit 1):

- DFlash2, bf16-State: **4,92 ms TPOT bei Accept-Länge 4,29** (bestes Ergebnis der Karte)
- NVFP4 + EAGLE/MTP: 152,9 tok/s (fp32-State) bzw. 144,5 (bf16)
- FP8 + EAGLE/MTP: 106,3 bzw. 116,1 tok/s

vLLM mit MTP@3 kommt laut Community-Messung auf einer 5090 von 72,0 auf 117,3 tok/s.
Für die RTX PRO 6000 nennt daily.dev 150 bis 220 tok/s mit SGLang plus
Spekulation und vollem 262K-Kontext.

### 4. Spekulation: DFlash2 als Standard

Drei Optionen, alle Apache 2.0:

| Methode | Draft | Flags |
|---|---|---|
| MTP | im Checkpoint | `--speculative-algorithm EAGLE --speculative-num-steps 3 --speculative-eagle-topk 1 --speculative-num-draft-tokens 4` |
| DFlash2 | `incoai/Qwen3.8-27B-DFlash2` | `--speculative-algorithm DFLASH --speculative-num-draft-tokens 8` |
| DSpark | `RadixArk/Qwen3.8-27B-DSpark` | `--speculative-algorithm DSPARK`, Fenster kommt aus dem Draft (gamma 7) |

Beide Draft-Checkpoints sind auf dem **Base**-Modell trainiert, das Target ist
abliteriert. Vokabular und Architektur sind identisch, es läuft also, die
Accept-Länge kann aber unter dem Cookbook-Wert liegen. Genau dafür misst
`qwen38bench` die tatsächliche Accept-Länge mit.

## Gemessen am 22.08.2026

Pod `mvwerlflspl3h1`, RTX PRO 6000 Blackwell 96GB (Secure Cloud, 2,09 USD/h),
SGLang `dev-qwen38-27b-dflash2`, Checkpoint `sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4`
(NVFP4 uniform), DFlash2-Spekulation, Kontext 262.144, `--mamba-ssm-dtype float32`,
gemessen von Deutschland aus über den RunPod-Proxy, ISL 8192 / OSL 1024, Nebenläufigkeit 1:

Erste Messreihe, kurz nach dem Start:

| Lauf | Decode | TTFT |
|---|---|---|
| 1 | 142,2 tok/s | 1412 ms |
| 2 | 143,3 tok/s | 1207 ms |
| 3 | 167,8 tok/s | 923 ms |

Median 143,3 tok/s, TPOT 6,98 ms.

Zweite Messreihe, rund 20 Minuten später am selben Pod, fünf Läufe:

| Lauf | Decode | TTFT |
|---|---|---|
| 1 | 122,4 tok/s | 855 ms |
| 2 | 148,1 tok/s | 1168 ms |
| 3 | 152,3 tok/s | 1340 ms |
| 4 | 155,6 tok/s | 1086 ms |
| 5 | 150,7 tok/s | 1378 ms |

Median **150,7 tok/s**, TPOT 6,63 ms, `max_running_requests` 48. **Das ist der gültige Wert**,
den auch die SKILL.md nennt.

Lehre aus dem Vergleich: Drei Läufe reichen nicht. Der erste Lauf jeder Reihe fällt ab, obwohl
`qwen38bench` bereits einen Warmlauf verwirft, und die Werte steigen über die ersten Minuten
weiter. Wer eine Zahl festschreibt, fährt fünf Läufe und lässt den Pod vorher ein paar Minuten
laufen.

Einordnung: Der Cookbook nennt für die 5090 mit NVFP4 plus DFlash2 4,92 ms TPOT, also rund
203 tok/s. Wir landen darunter, und zwar aus zwei plausiblen Gründen, die noch nicht getrennt
gemessen sind:

1. **Der Draft passt nicht exakt.** `incoai/Qwen3.8-27B-DFlash2` ist auf dem Base-Modell
   trainiert, das Target ist abliteriert. Die Accept-Länge dürfte unter den 4,29 des
   Cookbooks liegen. Nachmessen scheitert daran, dass der Prometheus-Endpunkt ohne
   `--enable-metrics` leer bleibt, und das SGLang-Image keinen sshd mitbringt.
2. **`--mamba-ssm-dtype`.** Für DFlash2 auf der 5090 ist laut Cookbook `bfloat16` die
   schnellere Wahl. Wir laufen auf `float32`.

Offene Vergleiche für den nächsten Lauf: `--spec mtp` gegen `dflash2`, und `bfloat16`
gegen `float32` für den State. Beides braucht einen Serverneustart, also einen neuen Pod.

## Fallen, die hier konkret warten

| Falle | Symptom | Gegenmittel |
|---|---|---|
| mixed-precision in SGLang | Modell läuft, ist aber lahm, kein Fehler | nur `nvfp4-pack-quantized` nehmen |
| `reasoning_effort` Default | Modell denkt endlos, Antwort kommt nie | `enable_thinking: false` oder niedriger Effort pro Request |
| `--mamba-full-memory-ratio` Default 0,9 | Concurrency wird still gedeckelt | 4,59 für die Standard-Konfiguration |
| falscher Tool-Parser | Tool-Calls kommen als Rohtext | `qwen3_coder`, nicht `hermes` |
| MTP auf FlashInfer | Arity-Fehler im prefill plan | `--attention-backend triton` als Ausweichweg |
| H100 gebucht für NVFP4 | FP4 fällt auf langsamen Marlin-Pfad zurück | Blackwell buchen oder FP8-Checkpoint nehmen |
| Kaltstart gemessen | Zahl 2 bis 10 mal zu schlecht | `qwen38bench` verwirft den ersten Lauf selbst |
| Python-urllib gegen den Proxy | HTTP 403 vom RunPod-Proxy | Browser-User-Agent mitschicken, `curl` ist nicht betroffen |
| SSH auf den Pod | Connection refused | das SGLang-Image bringt keinen sshd mit, anders als `runpod/pytorch` |

## Was nicht stimmt, wenn man es woanders liest

Die viel zitierten **346 bzw. 378 tok/s** aus dem LMSYS-Day-0-Blog gehören zu
**Qwen3.8-2.4T-A95B** auf **TP8 B300**, also dem großen MoE auf acht Karten.
Sie haben mit dem 27B auf einer GPU nichts zu tun.

## Quellen

- SGLang Cookbook Qwen3.8-27B: https://docs.sglang.io/cookbook/autoregressive/Qwen/Qwen3.8-27B
- LMSYS Day-0 (2.4T-Modell): https://www.lmsys.org/blog/2026-08-12-qwen3-8-day0-support
- SGLang mixed-precision Bug: https://github.com/sgl-project/sglang/issues/32736
- vLLM Recipes Qwen3.8-27B: https://recipes.vllm.ai/Qwen/Qwen3.8-27B
- orcarouter Modellkarte: https://huggingface.co/orcarouter/Qwen3.8-27B-Uncensored-NVFP4

## Feste lokale URL: Pod-Wechsel ohne Config-Änderung

Die Pod-URL ändert sich bei jedem Start. Damit Agent-Configs stabil bleiben, läuft lokal ein
Proxy mit fester Adresse davor:

```
pi / OpenCode / was auch immer
        |
        v
http://127.0.0.1:8388/v1        <- diese Zeile ändert sich nie
        |
   qwen38-proxy (LaunchAgent com.qwen38.qwen38-proxy)
        |  liest ~/.runpod/current-pod, hängt den API-Key an
        v
https://<pod>-8000.proxy.runpod.net/v1
```

Teile:

| Datei | Zweck |
|---|---|
| `~/.local/bin/qwen38-proxy` | der Proxy, Port 8388, streamt SSE unverändert durch |
| `~/Library/LaunchAgents/com.qwen38.qwen38-proxy.plist` | hält ihn am Leben, auch nach Reboot |
| `~/.runpod/current-pod` | aktuelle Pod-ID, von `qwen38fast` geschrieben, von `stop` gelöscht |
| `~/.runpod/qwen38.key` | API-Key, einmal erzeugt, danach wiederverwendet |
| `~/.pi/agent/models.json` | Provider `runpod`, Modell `runpod/qwen38-uncensored` |

Läuft kein Pod, antwortet der Proxy mit 503 und dem Hinweis, `qwen38fast` zu starten. Der Agent
zeigt dann eine lesbare Meldung statt Connection refused.

Drei Details, die sonst Zeit kosten:

- **`read1()` statt `read()`** im Proxy. Mit `read()` wartet Python auf einen vollen Block und
  das Token-Streaming kommt in Klumpen an. Verifiziert: 198 Chunks gleichmässig über 6,12 s.
- **Browser-User-Agent Pflicht.** Der RunPod-Proxy antwortet Python-urllib mit 403.
- **`thinkingFormat: "qwen-chat-template"`** in der Pi-Modelldefinition. Nur damit landet der
  Thinking-Schalter dort, wo SGLang ihn liest (`chat_template_kwargs.enable_thinking`).

Der Pod ist ohne `--api-key` aus dem ganzen Internet erreichbar, sobald jemand die Pod-ID kennt.
`qwen38fast` erzeugt deshalb beim ersten Lauf einen Key und übergibt ihn an SGLang und OpenWebUI.

## Welches abliterated ist das stärkste

Stand 22.08.2026, nach publizierten Zahlen:

| Build | Rest-Refusals | Qualitätsverlust | NVFP4 | Geschwindigkeit |
|---|---|---|---|---|
| `huihui-ai` (via sakamakismile-NVFP4) | 1,5 % | KLD 0,0078, erste 15 Layer unangetastet | ja | volle 143 tok/s |
| `OBLITERATUS` (Pliny) V2 | 2 von 842, rund 0,24 % | Ship-Score 92,1 | **nein**, nur BF16 und GGUF | BF16, grob ein Drittel |
| `orcarouter` | 0 bis 6 % | ±1,3 Punkte | ja, aber `mixed-precision` | in SGLang unbrauchbar |

Gewählt ist huihui: härter als orcarouter, sauberer als alles andere mit NVFP4. OBLITERATUS ist
kompromissloser, kostet aber den FP4-Pfad und damit zwei Drittel der Geschwindigkeit.
