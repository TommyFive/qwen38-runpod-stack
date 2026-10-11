#!/usr/bin/env bash
# setup.sh - installs the stack for the current user.
#   1. bin/* into ~/.local/bin
#   2. create LaunchAgents with the real home path and load them
#   3. notes for the RunPod CLI, HF token and pi
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "== 1) scripts into ~/.local/bin"
mkdir -p "$HOME/.local/bin" "$HOME/.runpod"
for f in "$HERE"/bin/*; do
  [[ -f "$f" ]] && cp "$f" "$HOME/.local/bin/"
done
chmod +x "$HOME"/.local/bin/qwen38fast "$HOME"/.local/bin/qwen38pi \
         "$HOME"/.local/bin/qwen38bench "$HOME"/.local/bin/qwen38cold "$HOME"/.local/bin/qwen38-proxy \
         "$HOME"/.local/bin/rp "$HOME"/.local/bin/runpod-reaper
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *)
  echo "   NOTE: ~/.local/bin is not on PATH. Add it to your shell config." ;;
esac

echo "== 1b) bootstrap into ~/.local/share/qwen38-runpod-stack"
BOOTSTRAP_DIR="$HOME/.local/share/qwen38-runpod-stack"
mkdir -p "$BOOTSTRAP_DIR"
install -m 700 \
  "$HERE/scripts/bootstrap-sglang-openwebui.sh" \
  "$BOOTSTRAP_DIR/bootstrap-sglang-openwebui.sh"
install -m 700 "$HERE/scripts/tailscale-runtime.sh" "$BOOTSTRAP_DIR/tailscale-runtime.sh"
install -m 600 "$HERE/scripts/model-storage.py" "$BOOTSTRAP_DIR/model-storage.py"
install -m 600 "$HERE/scripts/benchmark_sglang.py" "$BOOTSTRAP_DIR/benchmark_sglang.py"
install -m 600 "$HERE/scripts/private-template-ports.py" "$BOOTSTRAP_DIR/private-template-ports.py"
install -m 700 \
  "$HERE/scripts/tailscale-runtime.sh" \
  "$BOOTSTRAP_DIR/tailscale-runtime.sh"

echo "== 2) LaunchAgents (macOS)"
if [ "$(uname)" = "Darwin" ]; then
  LA="$HOME/Library/LaunchAgents"; mkdir -p "$LA"
  for name in proxy reaper; do
    sed "s|__HOME__|$HOME|g" "$HERE/launchagents/com.qwen38.$name.plist.template" > "$LA/com.qwen38.$name.plist"
    launchctl unload "$LA/com.qwen38.$name.plist" 2>/dev/null || true
    launchctl load "$LA/com.qwen38.$name.plist"
    echo "   loaded: com.qwen38.$name"
  done
else
  echo "   skipped (not macOS). Start the proxy by hand: qwen38-proxy &"
fi

echo "== 3) choose an SGLang Docker image and create the RunPod templates"
echo "   Custom GPU-tested minimal-v1 (default, private GHCR):"
echo "     ./create-templates.sh --image custom"
echo "   Official upstream public SGLang image:"
echo "     ./create-templates.sh --image official"
echo "   Then launch with the same image selector:"
echo "     qwen38pi --image custom       # or: qwen38pi --image official"
echo "   QWEN38_IMAGE_VARIANT=official is an alternative to both --image flags."
echo "   Distinct template names are auto-discovered; no IDs need exporting."
echo "   Explicit QWEN38_TEMPLATE* IDs remain for advanced manual/rollback use."

echo "== 4) wire up pi"
echo "   copy the block from pi/models.runpod.json into ~/.pi/agent/models.json."

echo
echo "Requirements: runpodctl logged in, HF token in ~/.cache/huggingface/token,"
echo "RunPod SSH key in ~/.runpod/ssh/runpodctl-ssh-key (for the full stack)."
echo "Then:  qwen38pi   (lean, for pi)   or   qwen38fast   (with OpenWebUI)"
