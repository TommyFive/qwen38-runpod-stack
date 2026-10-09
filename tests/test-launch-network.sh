#!/usr/bin/env bash
# Offline CLI/RunPod contract tests. No actual pods, tokens or Docker builds.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/home"
export HOME="$TMP/home"
export PATH="$TMP/bin:$PATH"
export TEST_EVENTS="$TMP/events.jsonl"

cat > "$TMP/bin/runpodctl" <<'PY'
#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if args[:2] == ["pod", "list"]:
    print("[]")
elif args[:2] == ["template", "create"]:
    name = args[args.index("--name") + 1]
    env = json.loads(args[args.index("--env") + 1])
    public = "--ports" in args
    assert bool(env["TAILSCALE_RUNTIME_B64"])
    assert bool(env["BOOTSTRAP_B64"])
    assert env["NETWORK_MODE"] in ("runpod", "tailnet")
    if env["NETWORK_MODE"] == "tailnet":
        assert not public, "private template must not publish ports"
        assert "--port-labels" not in args
    else:
        assert public and "8000/http" in args[args.index("--ports") + 1]
    with open(os.environ["TEST_EVENTS"], "a") as f:
        f.write(json.dumps({"kind":"template","name":name,"mode":env["NETWORK_MODE"],
                            "has_ports":public,"serve_webui":env["SERVE_WEBUI"]})+"\n")
    print(json.dumps({"id":"template-"+name}))
else:
    raise SystemExit(f"Unexpected runpodctl arguments: {args[:3]}")
PY
cat > "$TMP/bin/rp" <<'PY'
#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
assert args[1:3] == ["pod", "create"]
env = json.loads(args[args.index("--env") + 1])
with open(os.environ["TEST_EVENTS"], "a") as f:
    f.write(json.dumps({"kind":"pod","mode":env["NETWORK_MODE"],
                        "has_ts_authkey":"TS_AUTHKEY" in env,
                        "ts_hostname":env["TS_HOSTNAME"],
                        "ts_enable_ssh":env["TS_ENABLE_SSH"],
                        "template":args[args.index("--template-id")+1],
                        "disable_runpod_ssh":"--ssh=false" in args,
                        "serve_webui":env["SERVE_WEBUI"],
                        "runtime_included":bool(env["TAILSCALE_RUNTIME_B64"])})+"\n")
print(json.dumps({"id":"pod-ci"}))
PY
cat > "$TMP/bin/curl" <<'MOCK'
#!/usr/bin/env bash
case " $* " in
  *"/models"*) echo '{"data":[{"id":"qwen38-uncensored"}]}' ;;
  *"/api/config"*) echo '{"features":{"auth":true}}' ;;
  *) echo OK ;;
esac
MOCK
cat > "$TMP/bin/date" <<'MOCK'
#!/usr/bin/env bash
echo '12:34'
MOCK
chmod +x "$TMP/bin/"*

echo "=== create templates ==="
bash "$ROOT/create-templates.sh" > "$TMP/templates.output"
grep -Fq 'QWEN38_TEMPLATE_TAILNET_PI=' "$TMP/templates.output"

echo "=== tailnet CLI launch mock ==="
export QWEN38_TEMPLATE_TAILNET=private-full
export QWEN38_TEMPLATE_TAILNET_PI=private-pi
export QWEN38_TEMPLATE=legacy-full
export QWEN38_TEMPLATE_PI=legacy-pi
export QWEN38_BOOTSTRAP="$ROOT/scripts/bootstrap-sglang-openwebui.sh"
export QWEN38_TAILSCALE_RUNTIME="$ROOT/scripts/tailscale-runtime.sh"
export QWEN38_STORAGE_HELPER="$ROOT/scripts/model-storage.py"
export QWEN38_BENCHMARK_SCRIPT="$ROOT/scripts/benchmark_sglang.py"
export QWEN38_COLDSTART_TRACE=0
export QWEN38_TAILNET_DOMAIN=tailc8dece.ts.net
export TS_AUTHKEY=tskey-auth-fixture-not-real
bash "$ROOT/bin/qwen38fast" --pi --network tailnet > "$TMP/tailnet.out"
grep -Fq 'https://' "$TMP/tailnet.out"
grep -Fq '.tailc8dece.ts.net/v1' "$TMP/tailnet.out"
test "$(stat -c %a "$HOME/.runpod/current-endpoint.json")" = 600
python3 - "$HOME/.runpod/current-endpoint.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d["api_url"].startswith("https://qwen38-")
assert d["api_url"].endswith(".tailc8dece.ts.net/v1")
PY

echo "=== tailnet full stack with deferred web UI ==="
export TS_AUTHKEY=tskey-auth-fixture-not-real
bash "$ROOT/bin/qwen38fast" --network tailnet > "$TMP/tailnet-full.out"
grep -Fq 'https://' "$TMP/tailnet-full.out"
grep -Fq '.tailc8dece.ts.net:8443' "$TMP/tailnet-full.out"

echo "=== public CLI without TS_AUTHKEY ==="
unset TS_AUTHKEY
bash "$ROOT/bin/qwen38fast" --pi --network runpod > "$TMP/public.out"
grep -Fq 'https://pod-ci-8000.proxy.runpod.net/v1' "$TMP/public.out"

echo "=== assert events ==="
python3 - "$TEST_EVENTS" <<'PY'
import json,sys
events=[json.loads(line) for line in open(sys.argv[1])]
templates=[x for x in events if x["kind"]=="template"]
pods=[x for x in events if x["kind"]=="pod"]
assert len(templates)==4, templates
assert len([x for x in templates if x["mode"]=="tailnet" and not x["has_ports"]])==2
assert len(pods)==3, pods
private, full, public = pods
assert private["mode"]=="tailnet" and private["disable_runpod_ssh"]
assert private["has_ts_authkey"] and private["runtime_included"]
assert private["template"]=="private-pi" and private["serve_webui"]=="0"
assert full["mode"]=="tailnet" and full["disable_runpod_ssh"]
assert full["has_ts_authkey"] and full["template"]=="private-full"
assert full["serve_webui"]=="1"
assert public["mode"]=="runpod" and not public["disable_runpod_ssh"]
assert not public["has_ts_authkey"] and public["template"]=="legacy-pi"
print("test-launch-network: ok")
PY
