#!/usr/bin/env python3
"""Second approved Qwen38 candidate run; isolate 20 GiB SSD and benchmark baseline.

No production template modifications. Uses exact existing isolated image template,
same model/draft/bootstrap, separate Pod and telemetry. External provider may
have no stock; do not create a more expensive GPU as an automatic fallback.
"""
import base64, datetime as dt, json, os, subprocess, sys, time
from pathlib import Path

RP="/opt/homebrew/bin/runpodctl"
HERE=Path(__file__).resolve().parent
ROOT=Path("/Users/rentamac/.local/share/qwen38-coldstart-tests")
TEMPLATE="fjz0hj6xwc"
NAME="qwen38-imgtest-20261011-run02"
GPU="NVIDIA RTX PRO 6000 Blackwell Server Edition"
IMAGE="ghcr.io/tommyfive/qwen38-sglang:candidate-cloudzy-4ad22cd0b56b"
DIGEST="sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd"
DISK_GB=20
RATE_LIMIT=2.49
TIMEOUT_SEC=2400  # 40 min maximum test
CLOUD="SECURE"
CANDIDATE_DCS=("EU-CZ-1","EU-NL-1","EU-RO-1","EUR-IS-1","EUR-IS-2","US-PA-1","US-NC-2")
EXCLUDE_DCS={"US-NE-1"}  # first host was reported critically unhealthy

def now():return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
def run(*args,timeout=50,explain=False):
    r=subprocess.run([RP,*args],capture_output=True,text=True,timeout=timeout)
    if r.returncode:
        if explain:
            try:
                obj=json.loads(r.stdout)
                print("RUNPOD_FAILURE",str(obj.get("error","unknown"))[:360],flush=True)
            except Exception:
                print("RUNPOD_FAILURE",r.returncode,flush=True)
        raise RuntimeError("RunPod failed: "+" ".join(args[:2]))
    return json.loads(r.stdout)

def main():
    if run("pod","list","-o","json"):raise RuntimeError("There is already an active Pod")
    current=run("user","-o","json")
    if float(current.get("currentSpendPerHr",999))>0.01 or float(current.get("clientBalance",0))<3:
        raise RuntimeError("Account has active spend or low balance")
    ts=run("template","list","--type","user","-o","json")
    match=[x for x in ts if x.get("id")==TEMPLATE]
    if len(match)!=1:raise RuntimeError("Candidate template missing")
    t=match[0]
    if t.get("imageName")!=IMAGE or not t.get("containerRegistryAuthId"):
        raise RuntimeError("Unexpected image or missing GHCR auth")
    env=t.get("env",{})
    for k,v in {"COLDSTART_TRACE":"1","MODEL_STORAGE":"ram","SPEC":"dflash2","SERVE_WEBUI":"0"}.items():
        if env.get(k)!=v:raise RuntimeError(f"Source config drift: {k}")
    if b"QWEN38_DISK_SAMPLE" not in base64.b64decode(env["BOOTSTRAP_B64"]):
        raise RuntimeError("SSD probes missing")
    if not env.get("SGLANG_API_KEY","").startswith("{{ RUNPOD_SECRET_"):
        raise RuntimeError("Missing authenticated API secret reference")
    gpu=[x for x in run("gpu","list","-o","json") if x.get("gpuId")==GPU]
    if len(gpu)!=1 or not gpu[0].get("secureCloud") or gpu[0].get("securePricePerHr",1e9)>RATE_LIMIT:
        raise RuntimeError("GPU or hourly price guard failed")
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    folder=ROOT/NAME
    folder.mkdir(mode=0o700,exist_ok=False)
    pre=now()
    plan={"run_id":"run02","pod_request_at_utc":pre,"template_id":TEMPLATE,
      "name":NAME,"image":IMAGE,"digest":DIGEST,"disk_gb":DISK_GB,
      "model_storage":"ram","cloud":CLOUD,"gpu":GPU,
      "rate_usd_per_hour":gpu[0]["securePricePerHr"],"max_runtime_seconds":TIMEOUT_SEC,
      "benchmark":"qwen38bench --isl 8192 --osl 1024 --runs 5; concurrency=1, 1 discarded warmup",
      "candidate_data_centers":list(CANDIDATE_DCS),"excluded_data_centers":list(EXCLUDE_DCS),
      "reference_pod":"ynuxxmshzbu35k","reference_image_compressed_gb":12.907436335}
    (folder/"plan.json").write_text(json.dumps(plan,indent=2)+"\n")
    os.chmod(folder/"plan.json",0o600)
    pod=None
    # First try preferred DCs, then let RunPod assign location but reject unhealthy US-NE-1.
    attempts=[("preferred",",".join(CANDIDATE_DCS)),("auto",None)]
    for label,dc in attempts:
        cmd=["pod","create","--name",NAME,"--template-id",TEMPLATE,
              "--gpu-id",GPU,"--gpu-count","1","--cloud-type",CLOUD,
              "--container-disk-in-gb",str(DISK_GB),"-o","json"]
        if dc:cmd+=["--data-center-ids",dc]
        print("POD_CREATE_ATTEMPT",label,now(),flush=True)
        try:
            pod=run(*cmd,timeout=100,explain=True)
            break
        except RuntimeError:
            check=run("pod","list","-o","json")
            if any(x.get("name")==NAME for x in check):
                raise RuntimeError("Pod may have been created: refusing duplicate; inspect RunPod")
    if pod is None:raise RuntimeError("No GPUs available for authorized SKU and price")
    podid=pod.get("id")
    if not isinstance(podid,str) or len(podid)<8:
        raise RuntimeError("Pod creation returned no ID; inspect account")
    (folder/"pod-id.txt").write_text(podid+"\n")
    after=now()
    (folder/"creation.json").write_text(json.dumps({
       "before_api_utc":pre,"after_api_utc":after,"pod_id":podid,
       "pod_fields":{k:pod.get(k) for k in ("id","name","createdAt","runtimeStatus","costPerHr","containerDiskInGb")}
    },indent=2)+"\n")
    watcher=HERE/"live-watchdog.py"
    log=open(folder/"watchdog.log","w")
    try:
        proc=subprocess.Popen([sys.executable,str(watcher),"--pod-id",podid,
            "--root",str(folder),"--max-seconds",str(TIMEOUT_SEC),"--interval","15"],
            stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        time.sleep(2)
        if proc.poll() is not None:
            subprocess.run([RP,"pod","stop",podid],capture_output=True,timeout=30)
            raise RuntimeError("Watchdog failed; immediate stop attempted")
    finally:log.close()
    print("RUN02_STARTED",json.dumps({"pod_id":podid,"at_utc":after,
       "data_folder":str(folder),"watchdog_pid":proc.pid,"deadline_seconds":TIMEOUT_SEC,
       "disk_gb":DISK_GB}),flush=True)
if __name__=="__main__":
    try:main()
    except Exception as ex:
        print("RUN02_NOT_STARTED",type(ex).__name__,str(ex)[:280],file=sys.stderr)
        sys.exit(1)
