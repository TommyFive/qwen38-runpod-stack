#!/usr/bin/env bash
# Offline CLI/RunPod contract tests. No actual pods, tokens or Docker builds.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/home"
export HOME="$TMP/home"
# Offline fixture: simulate a verified PUBLIC image without contacting GHCR.
# Production script always executes the real anonymous-manifest verifier.
export QWEN38_TEST_REAL_PYTHON="$(command -v python3)"
export PATH="$TMP/bin:$PATH"
cat > "$TMP/bin/python3" <<'PY_WRAPPER'
#!/usr/bin/env bash
if [[ "${1:-}" == */images/sglang-qwen38/tools/check-public.py ]]; then
    exit 0
fi
exec "$QWEN38_TEST_REAL_PYTHON" "$@"
PY_WRAPPER
chmod +x "$TMP/bin/python3"
export TEST_EVENTS="$TMP/events.jsonl"
export TEST_TEMPLATE_DIR="$TMP/templates"
mkdir -p "$TEST_TEMPLATE_DIR"
export QWEN38_TEMPLATE_RESOLVER="$ROOT/scripts/resolve-template-launch.py"

cat > "$TMP/bin/ports-helper" <<'MOCK_PORTS'
#!/usr/bin/env python3
import sys
assert sys.argv[1:3] == ["repair", sys.argv[2]]
assert sys.argv[3:] == ["--delete-on-failure"]
print("PASS: mocked port hardening", file=sys.stderr)
MOCK_PORTS
chmod +x "$TMP/bin/ports-helper"
cat > "$TMP/bin/runpodctl" <<'PY'
#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if args[:2] == ["pod", "list"]:
    print("[]")
elif args[:2] == ["registry", "list"]:
    print(json.dumps([{"id":"test-ghcr-registry","name":"ghcr.io"}]))
elif args[:2] == ["template", "list"]:
    # Minimal offline fixtures: custom + upstream names both resolve.
    res=[]
    for flavor,prefix,image,auth in (
        ("custom","qwen38-v0.2.2",
         "ghcr.io/tommyfive/qwen38-sglang@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7",
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
    from pathlib import Path
    tid=args[2]
    alias={"private-pi":"qwen38-v0.2.2-lean-tailnet",
           "private-full":"qwen38-v0.2.2-full-tailnet",
           "legacy-pi":"qwen38-v0.2.2-lean-public",
           "legacy-full":"qwen38-v0.2.2-full-public"}
    source="template-"+alias[tid] if tid in alias else tid
    d=json.loads((Path(os.environ["TEST_TEMPLATE_DIR"])/(source+".json")).read_text())
    d["id"]=tid
    if tid=="private-pi":
        d["env"]["TS_HOSTNAME"]=os.environ.get("QWEN38_TEST_TEMPLATE_HOSTNAME","template-lean")
    elif "QWEN38_TEST_TEMPLATE_HOSTNAME" in os.environ:
        d["env"]["TS_HOSTNAME"]=os.environ["QWEN38_TEST_TEMPLATE_HOSTNAME"]
    print(json.dumps(d))
elif args[:2] == ["template", "create"]:
    name = args[args.index("--name") + 1]
    public = "--ports" in args
    image = args[args.index("--image") + 1]
    official=name.startswith("qwen38-official-")
    if official:
        assert image=="lmsysorg/sglang:dev-qwen38-27b-dflash2"
        assert "--registry-auth-id" not in args
        expected=150 if os.getenv("QWEN38_MODEL_STORAGE")=="ssd" else 20
        assert int(args[args.index("--container-disk-in-gb")+1])==expected
    else:
        assert image=="ghcr.io/tommyfive/qwen38-sglang@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7"
        assert "--registry-auth-id" not in args, "PUBLIC custom must not attach private GHCR credentials"
        expected=150 if os.getenv("QWEN38_MODEL_STORAGE")=="ssd" else 30
        assert int(args[args.index("--container-disk-in-gb")+1])==expected
    assert "--env" not in args, "large template env must be UPDATEd after creation"
    if public: assert "22/tcp" not in args[args.index("--ports")+1]
    if "tailnet" in name:
        assert not public, "private template must not publish ports"
        assert "--port-labels" not in args
    else:
        assert public and "8000/http" in args[args.index("--ports") + 1]
    print(json.dumps({"id":"template-"+name,"name":name}))
elif args[:2] == ["template", "update"]:
    tid = args[2]
    name=tid.removeprefix("template-") if hasattr(tid,"removeprefix") else tid[len("template-"):]
    env = json.loads(args[args.index("--env") + 1])
    public = "-public" in name
    assert bool(env["TAILSCALE_RUNTIME_B64"])
    assert bool(env["BOOTSTRAP_B64"])
    assert env["NETWORK_MODE"] in ("runpod", "tailnet")
    assert env.get("TS_HOSTNAME")=="llm", "all generated templates must set TS_HOSTNAME=llm"
    if env["SERVE_WEBUI"]=="1":
        assert env["WEBUI_ADMIN_PASSWORD"]=="{{ RUNPOD_SECRET_QWEN38_WEBUI_ADMIN_PASSWORD }}"
        assert "@" in env["WEBUI_ADMIN_EMAIL"]
    else:
        assert "WEBUI_ADMIN_PASSWORD" not in env and "WEBUI_ADMIN_EMAIL" not in env
    secret = os.environ.get("QWEN38_API_SECRET_NAME", "LLM_API_KEY")
    assert env["SGLANG_API_KEY"] == "{{ RUNPOD_SECRET_" + secret + " }}"
    assert env["HF_TOKEN"] == "{{ RUNPOD_SECRET_HF_TOKEN }}"
    assert ("TS_AUTHKEY" in env) == (env["NETWORK_MODE"] == "tailnet")
    assert (env["NETWORK_MODE"] == "runpod") == public
    with open(os.environ["TEST_EVENTS"], "a") as f:
        f.write(json.dumps({"kind":"template","name":name,"mode":env["NETWORK_MODE"],
                            "has_ports":public,"serve_webui":env["SERVE_WEBUI"],
                            "api_secret_ref":env["SGLANG_API_KEY"],
                            "ts_hostname":env["TS_HOSTNAME"]})+"\n")
    from pathlib import Path
    official=name.startswith("qwen38-official-")
    image=("lmsysorg/sglang:dev-qwen38-27b-dflash2" if official else
           "ghcr.io/tommyfive/qwen38-sglang@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7")
    disk=(150 if env["MODEL_STORAGE"]=="ssd" else 20 if official else 30)
    obj={"id":tid,"name":name,"env":env,"imageName":image,"containerDiskInGb":disk,
         "ports":[] if env["NETWORK_MODE"]=="tailnet" else
                  ["8000/http"] if env["SERVE_WEBUI"]=="0" else ["8000/http","8080/http"],
         "portsConfig":[]}
    (Path(os.environ["TEST_TEMPLATE_DIR"])/(tid+".json")).write_text(json.dumps(obj))
    print(json.dumps({"id":tid,"env":env}))
else:
    raise SystemExit(f"Unexpected runpodctl arguments: {args[:3]}")
PY
cat > "$TMP/bin/rp" <<'PY'
#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
assert args[1:3] == ["pod", "create"]
from pathlib import Path
tid=args[args.index("--template-id")+1]
alias={"private-pi":"qwen38-v0.2.2-lean-tailnet",
       "private-full":"qwen38-v0.2.2-full-tailnet",
       "legacy-pi":"qwen38-v0.2.2-lean-public",
       "legacy-full":"qwen38-v0.2.2-full-public"}
source="template-"+alias[tid] if tid in alias else tid
env=dict(json.loads((Path(os.environ["TEST_TEMPLATE_DIR"])/(source+".json")).read_text())["env"])
if tid=="private-pi":
    env["TS_HOSTNAME"]=os.environ.get("QWEN38_TEST_TEMPLATE_HOSTNAME","template-lean")
overrides=json.loads(args[args.index("--env")+1]) if "--env" in args else {}
env.update(overrides)
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
                        "runtime_included":bool(env["TAILSCALE_RUNTIME_B64"]),
                        "override_keys":sorted(overrides),
                        "env_flag_supplied":"--env" in args})+"\n")
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

echo "=== tailnet CLI launch mock ==="
# Template default is authoritative unless the operator explicitly overrides.
unset TS_HOSTNAME || true
export QWEN38_TEMPLATE_TAILNET=private-full
export QWEN38_TEMPLATE_TAILNET_PI=private-pi
export QWEN38_TEMPLATE=legacy-full
export QWEN38_TEMPLATE_PI=legacy-pi
export QWEN38_COLDSTART_TRACE=0
export QWEN38_TAILNET_DOMAIN=example.ts.net
unset TS_AUTHKEY || true
unset QWEN38_HF_SECRET_NAME || true
# Verify the default HF_TOKEN secret reference, not a test-only override.
bash "$ROOT/bin/qwen38fast" --pi --network tailnet > "$TMP/tailnet.out"
grep -Fq 'https://' "$TMP/tailnet.out"
grep -Fq 'https://template-lean.example.ts.net/v1' "$TMP/tailnet.out"
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
assert d["api_url"]=="https://template-lean.example.ts.net/v1"
PY

echo "=== tailnet full stack with deferred web UI ==="
bash "$ROOT/bin/qwen38fast" --network tailnet > "$TMP/tailnet-full.out"
grep -Fq 'https://' "$TMP/tailnet-full.out"
grep -Fq 'https://llm.example.ts.net:8443' "$TMP/tailnet-full.out"

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
assert all(x["ts_hostname"]=="llm" for x in templates), "all Custom templates must use llm"
assert len([x for x in templates if x["mode"]=="tailnet" and not x["has_ports"]])==2
assert len(pods)==3, pods
assert all(p["disk_gib"]==30 for p in pods), "custom v0.2.2 RAM-first Full and Lean use 30 GiB"
private, full, public = pods
assert private["mode"]=="tailnet" and private["disable_runpod_ssh"]
assert private["ts_key_ref"]=="{{ RUNPOD_SECRET_TS_AUTHKEY }}"
assert private["sglang_key_ref"]=="{{ RUNPOD_SECRET_LLM_API_KEY }}"
assert private["hf_key_ref"]=="{{ RUNPOD_SECRET_HF_TOKEN }}"
assert private["has_ts_authkey"] and private["runtime_included"]
assert private["ts_hostname"]=="template-lean", "tailnet CLI must keep selected template hostname"
assert private["template"]=="private-pi" and private["serve_webui"]=="0"
assert full["mode"]=="tailnet" and full["disable_runpod_ssh"]
assert full["has_ts_authkey"] and full["template"]=="private-full"
assert full["ts_hostname"]=="llm", "Full CLI must keep template hostname"
assert full["serve_webui"]=="1"
assert public["mode"]=="runpod" and not public["disable_runpod_ssh"]
assert not public["has_ts_authkey"] and public["template"]=="legacy-pi"
assert public["ts_hostname"]=="llm", "Public CLI must also keep template hostname"
assert public["sglang_key_ref"]=="{{ RUNPOD_SECRET_LLM_API_KEY }}"
assert public["hf_key_ref"]=="{{ RUNPOD_SECRET_HF_TOKEN }}"
print("test-launch-network: ok")
PY

echo "=== no explicit ENV options: no --env flag at all ==="
(unset QWEN38_COLDSTART_TRACE; bash "$ROOT/bin/qwen38fast" --pi --network runpod > "$TMP/zero-overrides.out")
python3 - "$TEST_EVENTS" <<'PY_ZERO'
import json,sys
rows=[json.loads(v) for v in open(sys.argv[1])]
item=rows[-1]
assert item["kind"]=="pod"
assert item["override_keys"]==[],item["override_keys"]
assert item["env_flag_supplied"] is False
assert item["ts_hostname"]=="llm" and item["runtime_included"]
print("zero-override pod: template env preserved, --env omitted")
PY_ZERO

echo "=== explicit hostname overrides only its selected ENV key ==="
baseline="$(grep -c '"kind": "pod"' "$TEST_EVENTS")"
bash "$ROOT/bin/qwen38fast" --pi --network tailnet --ts-hostname override > "$TMP/cli-hostname.out"
grep -Fq 'https://override.example.ts.net/v1' "$TMP/cli-hostname.out"
python3 - "$TEST_EVENTS" <<'PY_HOST'
import json,sys
rows=[json.loads(x) for x in open(sys.argv[1])]
p=rows[-1]
assert p["kind"]=="pod" and p["ts_hostname"]=="override"
assert p["override_keys"]==["COLDSTART_TRACE","TS_HOSTNAME"],p["override_keys"]
PY_HOST
for invalid in '' 'INVALID.HOST'; do
    if QWEN38_TEST_TEMPLATE_HOSTNAME="$invalid" bash "$ROOT/bin/qwen38fast" --pi --network tailnet >"$TMP/invalid-template-hostname.out" 2>&1; then
        echo "FAIL: empty or invalid template hostname accepted" >&2; exit 1
    fi
    grep -Fq 'TEMPLATE-FIRST VALIDATION FAILED' "$TMP/invalid-template-hostname.out"
done
test "$(grep -c '"kind": "pod"' "$TEST_EVENTS")" = "$((baseline+1))"

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
assert all(e["ts_hostname"]=="llm" for e in legacy_templates)
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
assert all(x["ts_hostname"]=="llm" for x in official), "Official templates must use llm"
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

echo "=== SSD checkpoint mode: both template families use 150 GiB by default ==="
QWEN38_MODEL_STORAGE=ssd QWEN38_PORTS_HELPER="$TMP/bin/ports-helper" bash "$ROOT/create-templates.sh" --image custom > "$TMP/custom-ssd-templates.out"
QWEN38_MODEL_STORAGE=ssd QWEN38_PORTS_HELPER="$TMP/bin/ports-helper" bash "$ROOT/create-templates.sh" --image official > "$TMP/official-ssd-templates.out"
if QWEN38_MODEL_STORAGE=ssd QWEN38_FULL_DISK_GB=20    QWEN38_PORTS_HELPER="$TMP/bin/ports-helper" bash "$ROOT/create-templates.sh" > "$TMP/undersized-template.out" 2>&1; then
  echo 'FAIL: accepted 20 GiB Full SSD template' >&2
  exit 1
fi
grep -Fq 'requires at least 50 GiB' "$TMP/undersized-template.out"

echo "=== SSD checkpoint mode: Pod overrides disk to 150 GiB ==="
# Disk-focused tests supply an explicit mock API Secret reference; the
# automatic template Secret reference is exercised separately above.
QWEN38_MODEL_STORAGE=ssd QWEN38_API_SECRET_NAME=LLM_API_KEY bash "$ROOT/bin/qwen38fast" --pi --storage ssd --image official --network runpod > "$TMP/ssd-official.out"
QWEN38_MODEL_STORAGE=ssd QWEN38_API_SECRET_NAME=LLM_API_KEY bash "$ROOT/bin/qwen38fast" --storage ssd --image custom --network runpod > "$TMP/ssd-custom.out"
python3 - "$TEST_EVENTS" <<'PY_SSD'
import json,sys
rows=[json.loads(line) for line in open(sys.argv[1]) if line.strip()]
pods=[r for r in rows if r.get("kind")=="pod"]
assert pods[-2]["disk_gib"]==150 and pods[-2]["template"]=="template-qwen38-official-lean-public"
assert pods[-1]["disk_gib"]==150 and pods[-1]["template"]=="template-qwen38-v0.2.2-full-public"
print("SSD model downloads correctly use 150 GiB for official Lean and Custom Full")
PY_SSD
if QWEN38_FULL_DISK_GB=20 bash "$ROOT/bin/qwen38fast" --storage ssd --image custom > "$TMP/undersized-pod.out" 2>&1; then
  echo 'FAIL: accepted 20 GiB SSD Pod override' >&2
  exit 1
fi
grep -Fq 'SSD requires >=50 GiB Container Disk' "$TMP/undersized-pod.out"
