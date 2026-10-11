#!/usr/bin/env python3
"""Enable SSH on ONLY the isolated run02 Pod, preserving the entire env.

This is an explicitly recorded intervention AFTER the cold-start healthcheck.
No secret value or original full env is printed or saved. Pod may require restart.
"""
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys

POD="fzt7b4jktp5gxj"
RP="/opt/homebrew/bin/runpodctl"
OUT=Path("/Users/rentamac/.local/share/qwen38-coldstart-tests/qwen38-imgtest-20261011-run02")

def run(*a):
    return subprocess.run([RP,*a],capture_output=True,text=True,timeout=75)
def main():
    r=run("pod","get",POD,"-o","json")
    if r.returncode:raise RuntimeError("Pod read failed")
    d=json.loads(r.stdout)
    if d.get("id")!=POD or d.get("name")!="qwen38-imgtest-20261011-run02":
        raise RuntimeError("Unexpected pod identity")
    if d.get("runtimeStatus")!="running" or d.get("containerDiskInGb")!=20:
        raise RuntimeError("Not the running 20-GB Pod")
    env=d.get("env") or {}
    if env.get("COLDSTART_TRACE")!="1" or env.get("MODEL_STORAGE")!="ram" or env.get("SPEC")!="dflash2":
        raise RuntimeError("Unexpected model or tracing config")
    if not env.get("PUBLIC_KEY"):raise RuntimeError("No RunPod public SSH key injected")
    if env.get("ENABLE_SSH")=="1":
        print("SSH_ALREADY_ENABLED")
        return
    if env.get("ENABLE_SSH")!="0":raise RuntimeError("Unexpected SSH setting")
    when=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    env["ENABLE_SSH"]="1"
    rec={"at_utc":when,"pod_id":POD,"action":"enable_ssh_then_restart",
         "reason":"standard qwen38bench API authentication on isolated run02",
         "preexisting_coldstart_healthcheck_remains_valid":True,
         "separate_restart_measurement":True}
    (OUT/"interventions.jsonl").open("a").write(json.dumps(rec)+"\n")
    r=run("pod","update",POD,"--env",json.dumps(env,separators=(",",":")),"-o","json")
    if r.returncode:
        print("POD_ENV_UPDATE_FAILED",r.returncode)
        sys.exit(2)
    val=json.loads(r.stdout)
    if val.get("id")!=POD:raise RuntimeError("Unexpected update response")
    print("ISOLATED_POD_SSH_ENABLED",when,"RESTART_MAY_BE_REQUIRED")
if __name__=="__main__":
    try:main()
    except Exception as ex:
        print("ENABLE_SSH_FAILED",type(ex).__name__,file=sys.stderr)
        sys.exit(1)
