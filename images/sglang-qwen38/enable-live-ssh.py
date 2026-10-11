#!/usr/bin/env python3
"""Enable SSH for *second diagnostic phase* on ONLY the pinned active test Pod.

First cold-start has already been captured externally. This may restart the
container and must not be confused with first-start timing. Do not print env.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RP="/opt/homebrew/bin/runpodctl"
POD_ID="ynuxxmshzbu35k"
TEMPLATE_ID="fjz0hj6xwc"
DIR=Path("/Users/rentamac/.local/share/qwen38-coldstart-tests/qwen38-imgtest-20261011-060057")
def run(*args):
    result=subprocess.run([RP,*args],text=True,capture_output=True,timeout=45)
    if result.returncode:
        raise RuntimeError("RunPod command failed: "+" ".join(args[:2]))
    return json.loads(result.stdout)

pod=run("pod","get",POD_ID,"-o","json")
if pod.get("name")!="qwen38-imgtest-20261011" or pod.get("imageName")!="ghcr.io/tommyfive/qwen38-sglang:candidate-cloudzy-4ad22cd0b56b":
    raise SystemExit("Refusing to change unexpected Pod")
templates=run("template","list","--type","user","-o","json")
matched=[t for t in templates if t.get("id")==TEMPLATE_ID]
if len(matched)!=1:raise SystemExit("Missing isolated template")
env=dict(matched[0]["env"])
if env.get("ENABLE_SSH")!="0" or env.get("COLDSTART_TRACE")!="1" or env.get("MODEL_STORAGE")!="ram":
    raise SystemExit("Unexpected measurement configuration")
env["ENABLE_SSH"]="1"
before=datetime.now(timezone.utc).isoformat()
(DIR/"diagnostic-phase.json").write_text(json.dumps({
    "phase":"second_phase_ssh_enabled","update_requested_utc":before,
    "pod_id":POD_ID,"first_cold_start_immutable_summary":"first-cold-summary.json",
    "note":"This configuration update may restart container; do not blend timings with original cold start"
},indent=2)+"\n")
try:
    out=run("pod","update",POD_ID,"--env",json.dumps(env,separators=(",",":")),"-o","json")
except (RuntimeError,subprocess.TimeoutExpired):
    print("POD_ENV_UPDATE_FAILED; no automatic retry",file=sys.stderr)
    raise SystemExit(2)
if out.get("id")!=POD_ID:raise SystemExit("Unexpected API response ID")
print("TEST_POD_DIAGNOSTIC_SSH_UPDATE_ACCEPTED",POD_ID,"at",before)
print("No other Pod or template modified.")
