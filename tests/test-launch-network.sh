#!/usr/bin/env bash
# Offline CLI/RunPod contract tests. No actual pods, tokens or Docker builds.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/home" "$TMP/templates-store"
export QWEN38_TEST_TEMPLATE_STORE="$TMP/templates-store"
export HOME="$TMP/home"
# Offline fixture: simulate a verified PUBLIC image without contacting GHCR.
# Production script always executes the real anonymous-manifest verifier.
export QWEN38_TEST_REAL_PYTHON="$(command -v python3)"
export PATH="$TMP/bin:$PATH"
cat > "$TMP/bin/python3" <<'PY_WRAPPER'
#!/usr/bin/env bash
if [[ "${1:-}" == */images/sglang-qwen38/check-public.py ]]; then
    exit 0
fi
exec "$QWEN38_TEST_REAL_PYTHON" "$@"
PY_WRAPPER
chmod +x "$TMP/bin/python3"
export TEST_EVENTS="$TMP/events.jsonl"

cat > "$TMP/bin/ports-helper" <<'MOCK_PORTS'
#!/usr/bin/env python3
import sys
if sys.argv[1] == "preflight":
    assert sys.argv[2:] == []
    sys.exit(0)
assert sys.argv[1:3] == ["repair", sys.argv[2]]
assert sys.argv[3:] == ["--delete-on-failure"] if len(sys.argv) > 3 else True
print("PASS: mocked port hardening", file=sys.stderr)
MOCK_PORTS
chmod +x "$TMP/bin/ports-helper"
cat > "$TMP/bin/runpodctl" <<'PY'
#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
store = Path(os.environ["QWEN38_TEST_TEMPLATE_STORE"])
if args[:2] == ["pod", "list"]:
    print("[]")
elif args[:2] == ["registry", "list"]:
    print(json.dumps([{"id":"test-ghcr-registry","name":"ghcr.io"}]))
elif args[:2] == ["template", "list"]:
    if os.getenv("QWEN38_MOCK_EXISTING"):
        print(json.dumps([json.loads(p.read_text()) for p in store.glob("*.json")]))
        sys.exit(0)
    # Minimal offline fixtures: custom + upstream names both resolve.
    res=[]
    for flavor,prefix,image,auth in (
        ("custom","qwen38-v0.2.0",
         "ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd",
         None),
        ("official","qwen38-official","lmsysorg/sglang:dev-qwen38-27b-dflash2",None),
    ):
        for profile in ("lean-public","full-public","lean-tailnet","full-tailnet"):
            name=prefix+"-"+profile
            mode="tailnet" if "tailnet" in profile else "runpod"
            item={"id":"template-"+name,"name":name,"imageName":image,
                  "env":{"NETWORK_MODE":mode,"SGLANG_API_KEY":"{{ RUNPOD_SECRET_LLM_API_KEY }}"},
                  "ports":[] if mode=="tailnet" else ["8000/http"]}
            if auth:item["containerRegistryAuthId"]=auth
            res.append(item)
    print(json.dumps(res))
elif args[:2] == ["template", "get"]:
    tid = args[2]
    if os.getenv("QWEN38_MOCK_EXISTING"):
        path = store / (tid + ".json")
        if not path.exists():
            sys.exit(1)
        print(path.read_text())
        sys.exit(0)
    if tid.startswith("template-qwen38-official-"):
        print(json.dumps({"id":tid,"imageName":"lmsysorg/sglang:dev-qwen38-27b-dflash2",
           "ports":[],"portsConfig":[],
           "env":{"NETWORK_MODE":"tailnet" if "tailnet" in tid else "runpod",
                  "SGLANG_API_KEY":"{{ RUNPOD_SECRET_LLM_API_KEY }}"}}))
    else:
        print(json.dumps({"id": tid, "ports": [], "portsConfig": [],
                          "env": {"NETWORK_MODE": "tailnet"}}))
elif args[:2] == ["template", "create"]:
    name = args[args.index("--name") + 1]
    public = "--ports" in args
    image = args[args.index("--image") + 1]
    official=name.startswith("qwen38-official-")
    if official:
        assert image=="lmsysorg/sglang:dev-qwen38-27b-dflash2"
        assert "--registry-auth-id" not in args
        expected=int(os.getenv("QWEN38_FULL_DISK_GB" if "-full-" in name else "QWEN38_LEAN_DISK_GB", "100" if os.getenv("QWEN38_MODEL_STORAGE")=="ssd" else "20"))
        assert int(args[args.index("--container-disk-in-gb")+1])==expected
    else:
        assert image=="ghcr.io/tommyfive/qwen38-sglang@sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd"
        assert "--registry-auth-id" not in args, "PUBLIC custom must not attach private GHCR credentials"
        expected=int(os.getenv("QWEN38_FULL_DISK_GB" if "-full-" in name else "QWEN38_LEAN_DISK_GB", "100" if os.getenv("QWEN38_MODEL_STORAGE")=="ssd" else "20"))
        assert int(args[args.index("--container-disk-in-gb")+1])==expected
    assert "--env" not in args, "large template env must be UPDATEd after creation"
    if "tailnet" in name:
        assert not public, "private template must not publish ports"
        assert "--port-labels" not in args
    else:
        assert public and "8000/http" in args[args.index("--ports") + 1]
    ident="template-"+name
    disk=int(args[args.index("--container-disk-in-gb")+1])
    ports=[] if not public else args[args.index("--ports")+1].split(",")
    (store / (ident+".json")).write_text(json.dumps({
        "id":ident,"name":name,"imageName":image,"containerDiskInGb":disk,
        "ports":ports,"env":{}}))
    print(json.dumps({"id":ident,"name":name}))
elif args[:2] == ["template", "update"]:
    tid = args[2]
    name=tid.removeprefix("template-") if hasattr(tid,"removeprefix") else tid[len("template-"):]
    env = json.loads(args[args.index("--env") + 1])
    public = "-public" in name
    assert bool(env["TAILSCALE_RUNTIME_B64"])
    assert bool(env["BOOTSTRAP_B64"])
    assert env["NETWORK_MODE"] in ("runpod", "tailnet")
    secret = os.environ.get("QWEN38_API_SECRET_NAME", "LLM_API_KEY")
    assert env["SGLANG_API_KEY"] == "{{ RUNPOD_SECRET_" + secret + " }}"
    assert env["HF_TOKEN"] == "{{ RUNPOD_SECRET_HF_TOKEN }}"
    assert ("TS_AUTHKEY" in env) == (env["NETWORK_MODE"] == "tailnet")
    assert (env["NETWORK_MODE"] == "runpod") == public
    path=store / (tid+".json")
    state=json.loads(path.read_text())
    state["env"]=env
    path.write_text(json.dumps(state))
    with open(os.environ["TEST_EVENTS"], "a") as f:
        f.write(json.dumps({"kind":"template","name":name,"mode":env["NETWORK_MODE"],
                            "has_ports":public,"serve_webui":env["SERVE_WEBUI"],
                            "api_secret_ref":env["SGLANG_API_KEY"]})+"\n")
    print(json.dumps({"id":tid,"env":env}))
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
                        "disk_gib":int(args[args.index("--container-disk-in-gb")+1]),
                        "has_ts_authkey":"TS_AUTHKEY" in env,
                        "ts_key_ref":env.get("TS_AUTHKEY"),
                        "sglang_key_ref":env.get("SGLANG_API_KEY"),
                        "hf_key_ref":env.get("HF_TOKEN"),
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
QWEN38_PORTS_HELPER="$TMP/bin/ports-helper" bash "$ROOT/create-templates.sh" > "$TMP/templates.output"
grep -Fq 'QWEN38_TEMPLATE_TAILNET_PI=' "$TMP/templates.output"

echo "=== resume must reuse four exact matching templates without duplicate creates ==="
QWEN38_MOCK_EXISTING=1 QWEN38_PORTS_HELPER="$TMP/bin/ports-helper" \
  bash "$ROOT/create-templates.sh" --image custom --resume > "$TMP/resume.output"
grep -Fq 'QWEN38_TEMPLATE_TAILNET_PI=template-qwen38-v0.2.0-lean-tailnet' "$TMP/resume.output"
python3 - "$TEST_EVENTS" <<'PY_RESUME'
import json,sys
rows=[json.loads(s) for s in open(sys.argv[1])]
assert len([r for r in rows if r["kind"]=="template"])==4, "resume created duplicates"
print("Resume reused all four templates without creating duplicates")
PY_RESUME

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
unset TS_AUTHKEY || true
unset QWEN38_HF_SECRET_NAME || true
# Verify the default HF_TOKEN secret reference, not a test-only override.
bash "$ROOT/bin/qwen38fast" --pi --network tailnet > "$TMP/tailnet.out"
grep -Fq 'https://' "$TMP/tailnet.out"
grep -Fq '.tailc8dece.ts.net/v1' "$TMP/tailnet.out"
grep -Fq 'no guaranteed auto-stop' "$TMP/tailnet.out"
grep -Fq 'runpodctl pod delete pod-ci' "$TMP/tailnet.out"
if grep -Fq 'then RunPod terminates it itself' "$ROOT/bin/qwen38fast"; then
  echo 'FAIL: false RunPod timer guarantee' >&2
  exit 1
fi
test "$(stat -c %a "$HOME/.runpod/current-endpoint.json")" = 600
python3 - "$HOME/.runpod/current-endpoint.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d["api_url"].startswith("https://qwen38-")
assert d["api_url"].endswith(".tailc8dece.ts.net/v1")
PY

echo "=== tailnet full stack with deferred web UI ==="
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
assert all(p["disk_gib"]==20 for p in pods), "RAM-first Full and Lean must use 20 GiB"
private, full, public = pods
assert private["mode"]=="tailnet" and private["disable_runpod_ssh"]
assert private["ts_key_ref"]=="{{ RUNPOD_SECRET_TS_AUTHKEY }}"
assert private["sglang_key_ref"]=="{{ RUNPOD_SECRET_LLM_API_KEY }}"
assert private["hf_key_ref"]=="{{ RUNPOD_SECRET_HF_TOKEN }}"
assert private["has_ts_authkey"] and private["runtime_included"]
assert private["template"]=="private-pi" and private["serve_webui"]=="0"
assert full["mode"]=="tailnet" and full["disable_runpod_ssh"]
assert full["has_ts_authkey"] and full["template"]=="private-full"
assert full["serve_webui"]=="1"
assert public["mode"]=="runpod" and not public["disable_runpod_ssh"]
assert not public["has_ts_authkey"] and public["template"]=="legacy-pi"
assert public["sglang_key_ref"]=="{{ RUNPOD_SECRET_LLM_API_KEY }}"
assert public["hf_key_ref"]=="{{ RUNPOD_SECRET_HF_TOKEN }}"
print("test-launch-network: ok")
PY

echo "=== legacy LLAMA_API_KEY override remains supported in Qwen38 only ==="
QWEN38_API_SECRET_NAME=LLAMA_API_KEY QWEN38_PORTS_HELPER="$TMP/bin/ports-helper" \
  bash "$ROOT/create-templates.sh" > "$TMP/legacy-templates.out"
QWEN38_API_SECRET_NAME=LLAMA_API_KEY \
  bash "$ROOT/bin/qwen38fast" --pi --network runpod > "$TMP/legacy-pod.out"
python3 - "$TEST_EVENTS" <<'PY_LEGACY'
import json,sys
events=[json.loads(line) for line in open(sys.argv[1])]
legacy_templates=[e for e in events if e["kind"]=="template"][4:]
assert len(legacy_templates)==4, legacy_templates
assert all(e["api_secret_ref"]=="{{ RUNPOD_SECRET_LLAMA_API_KEY }}" for e in legacy_templates)
assert events[-1]["kind"]=="pod"
assert events[-1]["sglang_key_ref"]=="{{ RUNPOD_SECRET_LLAMA_API_KEY }}"
print("legacy override test: ok")
PY_LEGACY

echo "=== malformed secret selector rejected before any RunPod call ==="
if QWEN38_API_SECRET_NAME='BAD }}' QWEN38_PORTS_HELPER="$TMP/bin/ports-helper" \
     bash "$ROOT/create-templates.sh" > "$TMP/bad-api-name.out" 2>&1; then
    echo 'FAIL: unsafe API Secret name was accepted' >&2
    exit 1
fi
grep -Fq 'QWEN38_API_SECRET_NAME must be a nonempty RunPod secret identifier' "$TMP/bad-api-name.out"

echo "=== official image choice: all four RAM-first templates use 20 GiB ==="
QWEN38_PORTS_HELPER="$TMP/bin/ports-helper" bash "$ROOT/create-templates.sh" --image official > "$TMP/official-templates.out"
grep -Fq 'Image variant: official' "$TMP/official-templates.out"
python3 - "$TEST_EVENTS" <<'PY_OFFICIAL'
import json,sys
items=[json.loads(line) for line in open(sys.argv[1]) if line.strip()]
official=[x for x in items if x.get("kind")=="template" and x.get("name","").startswith("qwen38-official-")]
assert len(official)==4, official
assert sum(x["mode"]=="tailnet" and not x["has_ports"] for x in official)==2
assert sum(x["mode"]=="runpod" and x["has_ports"] for x in official)==2
print("official templates: 4 distinct modes, all RAM-first 20 GiB")
PY_OFFICIAL
echo "=== official image selection: auto-resolve correct upstream template without actual pod ==="
unset QWEN38_TEMPLATE QWEN38_TEMPLATE_PI QWEN38_TEMPLATE_TAILNET QWEN38_TEMPLATE_TAILNET_PI
bash "$ROOT/bin/qwen38fast" --pi --image official --network runpod > "$TMP/official-launch.out"
python3 - "$TEST_EVENTS" <<'PY_SELECTION'
import json,sys
rows=[json.loads(line) for line in open(sys.argv[1]) if line.strip()]
assert rows[-1]["kind"]=="pod", rows[-1]
assert rows[-1]["template"]=="template-qwen38-official-lean-public"
print("Official launcher resolves distinct official Lean template")
PY_SELECTION

echo "=== SSD checkpoint mode: both template families use 100 GiB by default ==="
QWEN38_MODEL_STORAGE=ssd QWEN38_PORTS_HELPER="$TMP/bin/ports-helper" bash "$ROOT/create-templates.sh" --image custom > "$TMP/custom-ssd-templates.out"
QWEN38_MODEL_STORAGE=ssd QWEN38_PORTS_HELPER="$TMP/bin/ports-helper" bash "$ROOT/create-templates.sh" --image official > "$TMP/official-ssd-templates.out"
if QWEN38_MODEL_STORAGE=ssd QWEN38_FULL_DISK_GB=20    QWEN38_PORTS_HELPER="$TMP/bin/ports-helper" bash "$ROOT/create-templates.sh" > "$TMP/undersized-template.out" 2>&1; then
  echo 'FAIL: accepted 20 GiB Full SSD template' >&2
  exit 1
fi
grep -Fq 'requires at least 50 GiB' "$TMP/undersized-template.out"

# The safety minimum stays 50 GiB: explicit 50-GiB SSD templates must pass.
QWEN38_MODEL_STORAGE=ssd QWEN38_FULL_DISK_GB=50 QWEN38_LEAN_DISK_GB=50 \
  QWEN38_PORTS_HELPER="$TMP/bin/ports-helper" bash "$ROOT/create-templates.sh" --image official > "$TMP/minimum-ssd-templates.out"

echo "=== SSD checkpoint mode: Pod overrides disk to 100 GiB ==="
# Disk-focused tests supply an explicit mock API Secret reference; the
# automatic template Secret reference is exercised separately above.
QWEN38_MODEL_STORAGE=ssd QWEN38_API_SECRET_NAME=LLM_API_KEY bash "$ROOT/bin/qwen38fast" --pi --storage ssd --image official --network runpod > "$TMP/ssd-official.out"
QWEN38_MODEL_STORAGE=ssd QWEN38_API_SECRET_NAME=LLM_API_KEY bash "$ROOT/bin/qwen38fast" --storage ssd --image custom --network runpod > "$TMP/ssd-custom.out"
python3 - "$TEST_EVENTS" <<'PY_SSD'
import json,sys
rows=[json.loads(line) for line in open(sys.argv[1]) if line.strip()]
pods=[r for r in rows if r.get("kind")=="pod"]
assert pods[-2]["disk_gib"]==100 and pods[-2]["template"]=="template-qwen38-official-lean-public"
assert pods[-1]["disk_gib"]==100 and pods[-1]["template"]=="template-qwen38-v0.2.0-full-public"
print("SSD model downloads correctly use 100 GiB for official Lean and Custom Full")
PY_SSD
if QWEN38_FULL_DISK_GB=20 bash "$ROOT/bin/qwen38fast" --storage ssd --image custom > "$TMP/undersized-pod.out" 2>&1; then
  echo 'FAIL: accepted 20 GiB SSD Pod override' >&2
  exit 1
fi
grep -Fq 'SSD model downloads require >=50 GiB' "$TMP/undersized-pod.out"

# Preserve an explicit 50-GiB SSD Pod override, without changing the default.
QWEN38_LEAN_DISK_GB=50 QWEN38_MODEL_STORAGE=ssd QWEN38_API_SECRET_NAME=LLM_API_KEY \
  bash "$ROOT/bin/qwen38fast" --pi --storage ssd --image official --network runpod > "$TMP/minimum-ssd-pod.out"
python3 - "$TEST_EVENTS" <<'PY_SSD_MIN'
import json,sys
rows=[json.loads(line) for line in open(sys.argv[1]) if line.strip()]
pod=[r for r in rows if r.get("kind")=="pod"][-1]
assert pod["disk_gib"]==50 and pod["template"]=="template-qwen38-official-lean-public"
print("SSD explicit 50 GiB minimum remains accepted")
PY_SSD_MIN

