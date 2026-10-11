#!/usr/bin/env python3
"""Add read-only 15-second disk-capacity probe to the ISOLATED cold-start template.

This changes only an existing test template, never the production baseline.
Only the original bootstrap receives a tiny metrics prefix. No model/start flags
are changed. Does not launch a GPU or display env/secret values.
"""
import base64,json,subprocess,sys

RP="/opt/homebrew/bin/runpodctl"
TARGET="fjz0hj6xwc"
def run(*args):
    return subprocess.run([RP,*args],text=True,capture_output=True,timeout=50)
r=run("template","list","--type","user","-o","json")
if r.returncode:sys.exit("Cannot list templates")
items=json.loads(r.stdout)
found=[x for x in items if x.get("id")==TARGET]
if len(found)!=1 or found[0].get("name")!="qwen38-coldstart-isolated-20261011":
    sys.exit("Candidate test template not found")
t=found[0]
if t.get("containerRegistryAuthId")!="cmutxmy57004u13i0uprfwtld":
    sys.exit("Unexpected registry auth")
env=dict(t["env"])
raw=base64.b64decode(env["BOOTSTRAP_B64"])
if b"QWEN38_DISK_SAMPLE" in raw:
    sys.exit("Instrumentation already applied")
probe=b'''#!/usr/bin/env bash
# Only collect space measurements; prints no credentials or environment.
(
  while :; do
    stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    df -B1 -P / /workspace /dev/shm 2>/dev/null | awk -v at="$stamp" 'NR>1 {printf "QWEN38_DISK_SAMPLE at=%s mount=%s total_bytes=%s used_bytes=%s free_bytes=%s used_percent=%s\\n", at,$6,$2,$3,$4,$5}'
    sleep 15
  done
) &
'''
env["BOOTSTRAP_B64"]=base64.b64encode(probe+raw).decode()
r=run("template","update",TARGET,"--env",json.dumps(env,separators=(",",":")),"-o","json")
if r.returncode:
    print("Disk probe update rejected; no Pod started",file=sys.stderr)
    sys.exit(2)
updated=json.loads(r.stdout)
if updated.get("id")!=TARGET or updated.get("env",{}).get("COLDSTART_TRACE")!="1":
    sys.exit("Unexpected template response")
print("ISOLATED_TEMPLATE_DISK_PROBE_READY",TARGET,"interval=15s","mounts=/,/workspace,/dev/shm","coldtrace=1")
