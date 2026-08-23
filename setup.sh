#!/usr/bin/env bash
# setup.sh - installiert den Stack fuer den aktuellen Nutzer.
#   1. bin/* nach ~/.local/bin
#   2. LaunchAgents mit dem echten Home-Pfad erzeugen und laden
#   3. Hinweise fuer RunPod-CLI, HF-Token und pi
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "== 1) Skripte nach ~/.local/bin"
mkdir -p "$HOME/.local/bin" "$HOME/.runpod"
cp "$HERE"/bin/* "$HOME/.local/bin/"
chmod +x "$HOME"/.local/bin/qwen38fast "$HOME"/.local/bin/qwen38pi \
         "$HOME"/.local/bin/qwen38bench "$HOME"/.local/bin/qwen38-proxy \
         "$HOME"/.local/bin/rp "$HOME"/.local/bin/runpod-reaper
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *)
  echo "   HINWEIS: ~/.local/bin ist nicht im PATH. In die Shell-Config aufnehmen." ;;
esac

echo "== 2) LaunchAgents (macOS)"
if [ "$(uname)" = "Darwin" ]; then
  LA="$HOME/Library/LaunchAgents"; mkdir -p "$LA"
  for name in proxy reaper; do
    sed "s|__HOME__|$HOME|g" "$HERE/launchagents/com.qwen38.$name.plist.template" > "$LA/com.qwen38.$name.plist"
    launchctl unload "$LA/com.qwen38.$name.plist" 2>/dev/null || true
    launchctl load "$LA/com.qwen38.$name.plist"
    echo "   geladen: com.qwen38.$name"
  done
else
  echo "   uebersprungen (kein macOS). Proxy von Hand starten: qwen38-proxy &"
fi

echo "== 3) Templates in RunPod anlegen"
echo "   ./create-templates.sh   und die IDs exportieren:"
echo "     export QWEN38_TEMPLATE=<id>  QWEN38_TEMPLATE_PI=<id>"

echo "== 4) pi anbinden"
echo "   Den Block aus pi/models.runpod.json in ~/.pi/agent/models.json uebernehmen."

echo
echo "Voraussetzungen: runpodctl eingeloggt, HF-Token in ~/.cache/huggingface/token,"
echo "RunPod-SSH-Key in ~/.runpod/ssh/runpodctl-ssh-key (fuer den Voll-Stack)."
echo "Danach:  qwen38pi   (schlank fuer pi)   oder   qwen38fast   (mit OpenWebUI)"
