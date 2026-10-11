#!/usr/bin/env python3
"""Read-only in-pod checks for an authorized Qwen38 candidate. No secret output."""
import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime,timezone

def df(path):
    try:
        x=os.statvfs(path)
        return {"path":path,"total_bytes":x.f_frsize*x.f_blocks,
                "free_bytes":x.f_frsize*x.f_bavail,
                "used_bytes":x.f_frsize*(x.f_blocks-x.f_bfree)}
    except OSError as exc:return {"path":path,"error":type(exc).__name__}

result={"at_utc":datetime.now(timezone.utc).isoformat(),"disk":[df(p) for p in ("/","/workspace","/dev/shm")]}
result["secrets_present_but_not_printed"]={
  "SGLANG_API_KEY":bool(os.environ.get("SGLANG_API_KEY")),
  "HF_TOKEN":bool(os.environ.get("HF_TOKEN"))
}
try:
    key=os.environ.get("SGLANG_API_KEY","")
    hdr={"Authorization":"Bearer "+key} if key else {}
    req=urllib.request.Request("http://127.0.0.1:8000/v1/models",headers=hdr)
    with urllib.request.urlopen(req,timeout=4) as res:
        model=json.load(res)
        result["authenticated_models"]={
            "status":res.status,
            "count":len(model.get("data",[])),
            "names":[str(x.get("id",""))[:150] for x in model.get("data",[])][:5]
        }
except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ValueError,OSError) as exc:
    result["authenticated_models"]={"error_type":type(exc).__name__}
try:
    out=subprocess.run(["nvidia-smi","--query-gpu=name,memory.total,memory.used","--format=csv,noheader"],
                       text=True,capture_output=True,timeout=5)
    result["nvidia_smi"]=out.stdout.strip()[:500] if out.returncode==0 else "unavailable"
except (OSError,subprocess.TimeoutExpired):
    result["nvidia_smi"]="unavailable"
print("QWEN38_PRIVATE_DIAGNOSTIC "+json.dumps(result,sort_keys=True))
