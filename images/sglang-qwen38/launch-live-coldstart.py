#!/usr/bin/env python3
"""Start one isolated paid RTX PRO 6000 candidate and immediately attach local watchdog.

Explicit user-approved live GPU experiment. Never changes production templates.
No secrets in files or output; only sanitized host API metadata.
"""
import base64
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RP="/opt/homebrew/bin/runpodctl"
HERE=Path(__file__).resolve().parent
ROOT=Path("/Users/rentamac/.local/share/qwen38-coldstart-tests")
TEMPLATE="fjz0hj6xwc"
GPU="NVIDIA RTX PRO 6000 Blackwell Server Edition"
REGION="AUTO"
NAME="qwen38-imgtest-20261011"
TIMEOUT_SEC=3300

def run(*args,timeout=45):
    v=subprocess.run([RP,*args],capture_output=True,text=True,timeout=timeout)
    if v.returncode:
        import re
        raw=(v.stderr or v.stdout).strip().splitlines()
        first=(raw[0] if raw else "No response")[:450]
        if any(k in first.lower() for k in ("api_key","authkey","hf_token","bootstrap_b64","authorization","--env")):
            first="[redacted env/credential diagnostic]"
        first=re.sub(r"[A-Za-z0-9_+./=-]{48,}","[REDACTED]",first)
        print("RUNPOD_API_FAILURE",first,file=sys.stderr)
        raise RuntimeError("RunPod operation failed: "+ " ".join(args[:2]))
    return json.loads(v.stdout)

def now():return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")

def main():
    pods=run("pod","list","-o","json")
    if pods:
        raise ValueError("Refusing to start: RunPod already has a Pod (do not touch existing workloads)")
    templates=run("template","list","--type","user","-o","json")
    matched=[x for x in templates if x.get("id")==TEMPLATE]
    if len(matched)!=1:raise ValueError("Isolated template missing")
    t=matched[0]
    if t.get("name")!="qwen38-coldstart-isolated-20261011" or t.get("containerRegistryAuthId")!="cmutxmy57004u13i0uprfwtld":
        raise ValueError("Unexpected candidate template")
    if t.get("imageName")!="ghcr.io/tommyfive/qwen38-sglang:candidate-cloudzy-4ad22cd0b56b":
        raise ValueError("Image tag mismatch")
    env=t.get("env",{})
    if env.get("COLDSTART_TRACE")!="1" or env.get("MODEL_STORAGE")!="ram" or env.get("SPEC")!="dflash2":
        raise ValueError("Missing essential trace or model config")
    if b"QWEN38_DISK_SAMPLE" not in base64.b64decode(env["BOOTSTRAP_B64"]):
        raise ValueError("Missing storage disk telemetry before paid launch")
    if not env.get("SGLANG_API_KEY","").startswith("{{ RUNPOD_SECRET_"):
        raise ValueError("API requires secret reference")
    if t.get("containerDiskInGb")!=150:raise ValueError("Unexpected container disk capacity")
    balance=run("user","-o","json")
    if balance.get("clientBalance",0)<4 or balance.get("currentSpendPerHr",999)>0.01:
        raise ValueError("Insufficient balance or other Pod currently spending")
    items=run("gpu","list","-o","json")
    gpu=[x for x in items if x.get("gpuId")==GPU]
    if len(gpu)!=1 or gpu[0].get("communityPricePerHr",1e9)>1.69 or not gpu[0].get("communityCloud"):
        raise ValueError("Target GPU cost/availability unexpected")
    stock={x["dataCenterId"]:x.get("stockStatus") for x in gpu[0].get("dataCenterAvailability",[])}
    if not any(status in ("Medium","High","Low") for status in stock.values()):
        raise ValueError("No Community Cloud GPU stock reported")
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(ROOT,0o700)
    folder=ROOT/(NAME+"-"+dt.datetime.now(dt.timezone.utc).strftime("%H%M%S"))
    folder.mkdir(mode=0o700,exist_ok=False)
    os.chmod(folder,0o700)
    pre=now()
    (folder/"plan.json").write_text(json.dumps({
      "created_utc_start":pre,"target":"coldstart_new_image","region":REGION,
      "gpu":GPU,"cloud":"COMMUNITY","rate_usd_hr":gpu[0]["communityPricePerHr"],
      "container_disk_gb":150,"model_storage":"ram","template_id":TEMPLATE,
      "image_tag":t["imageName"],"manifest_digest":"sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd",
      "coldstart_trace":True,"disk_probe_period_s":15,
      "watchdog_max_seconds":TIMEOUT_SEC,
      "source_baseline_template_id":"g6ey6ire16"
    },indent=2)+"\n")
    print("POD_CREATE_BEGIN",pre,"region",REGION,"price_hour",gpu[0]["communityPricePerHr"],flush=True)
    argv=["pod","create","--name",NAME,"--template-id",TEMPLATE,
      "--gpu-id",GPU,"--gpu-count","1","--cloud-type","COMMUNITY",
      "--container-disk-in-gb","150","-o","json"]
    response=run(*argv,timeout=90)
    pod_id=response.get("id")
    if not isinstance(pod_id,str) or len(pod_id)<6:
        raise RuntimeError("Pod creation response lacks ID; inspect account before retrying")
    after=now()
    (folder/"pod-id.txt").write_text(pod_id+"\n")
    (folder/"creation.json").write_text(json.dumps({
        "before_api_utc":pre,"after_api_utc":after,
        "pod_id":pod_id,
        "fields":{k:response.get(k) for k in ("id","name","cloudType","dataCenterId","gpuId","costPerHr","runtimeStatus","desiredStatus","machineId") if k in response}
    },indent=2)+"\n")
    os.chmod(folder/"pod-id.txt",0o600)
    log=(folder/"watchdog.log").open("w")
    try:
        w=subprocess.Popen([
            sys.executable,str(HERE/"live-watchdog.py"),
            "--pod-id",pod_id,"--root",str(folder),
            "--max-seconds",str(TIMEOUT_SEC),"--interval","15"
        ],stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
        time.sleep(2)
        if w.poll() is not None:
            subprocess.run([RP,"pod","delete",pod_id],capture_output=True,timeout=40)
            raise RuntimeError("Watcher failed on startup; attempted immediate Pod deletion")
    finally:
        log.close()
    print("POD_CREATED",pod_id,"WATCHDOG_PID",w.pid,"CREATED_UTC",after,flush=True)
    print("CAPTURE_ROOT",folder,flush=True)
    print("LOCAL_AUTODELETE_AFTER_SECONDS",TIMEOUT_SEC,flush=True)

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("LAUNCH_FAILED",type(e).__name__,str(e)[:180],file=sys.stderr)
        sys.exit(1)
