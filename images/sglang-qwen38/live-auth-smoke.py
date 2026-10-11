#!/usr/bin/env python3
"""In-pod GPU and Bearer-authenticated inference smoke on Qwen38 candidate.

No secret values, generated text or prompts are printed/saved. API key is only
read into process memory, and requests are to localhost:8000. No installs,
downloads or server restarts. Intended only on user-authorized test Pod.
"""
import importlib
import json
import os
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API="http://127.0.0.1:8000/v1"
MODEL="qwen38-uncensored"
def auth_key():
    key=os.environ.get("SGLANG_API_KEY","")
    if not key or key.startswith("{{ "):
        try:
            raw=open("/proc/1/environ","rb").read()
            for item in raw.split(b"\x00"):
                if item.startswith(b"SGLANG_API_KEY="):
                    key=item.split(b"=",1)[1].decode("utf-8")
                    break
        except OSError:
            pass
    if not key or key.startswith("{{ "):
        raise RuntimeError("SGLANG_API_KEY not accessible to diagnostic process")
    return key

def req(url, key=None, data=None, timeout=15):
    headers={"Content-Type":"application/json"}
    if key:headers["Authorization"]="Bearer "+key
    return urllib.request.urlopen(urllib.request.Request(
        url,data=json.dumps(data).encode() if data is not None else None,
        headers=headers),timeout=timeout)

def benchmark_stream(key,max_tokens):
    body={"model":MODEL,"messages":[{"role":"user","content":
           "List basic colors separated by commas until the response limit."}],
          "temperature":0,"max_tokens":max_tokens,"stream":True,
          "stream_options":{"include_usage":True},
          "chat_template_kwargs":{"enable_thinking":False}}
    t0=time.monotonic()
    first=None
    usage=None
    delta_count=0
    with req(API+"/chat/completions",key,body,timeout=180) as res:
        for raw in res:
            line=raw.decode("utf-8","replace").strip()
            if not line.startswith("data: "):continue
            data=line[6:]
            if data=="[DONE]":break
            try:msg=json.loads(data)
            except ValueError:continue
            choices=msg.get("choices",[])
            if choices:
                delta=choices[0].get("delta") or {}
                if delta.get("content") or delta.get("reasoning_content"):
                    delta_count+=1
                    if first is None:first=time.monotonic()
            if msg.get("usage"):usage=msg["usage"]
    t1=time.monotonic()
    tokens=usage.get("completion_tokens") if isinstance(usage,dict) else None
    return {"ttft_s":round(first-t0,4) if first else None,
            "total_s":round(t1-t0,4),"completion_tokens":tokens,
            "stream_chunks":delta_count,
            "decode_tokens_per_s":round((tokens-1)/(t1-first),2)
                                  if first and isinstance(tokens,int) and tokens>1 and t1>first else None}

def main():
    result={"schema":1,"at_utc":datetime.now(timezone.utc).isoformat(),
            "test":"qwen38-candidate-inpod-bearer-smoke","model":MODEL}
    key=auth_key()
    try:
        req(API+"/models",timeout=10)
        result["unauthenticated_status"]="unexpected_success"
    except urllib.error.HTTPError as exc:
        result["unauthenticated_status"]=exc.code
    with req(API+"/models",key,timeout=12) as response:
        doc=json.load(response)
        result["authorized_models_http"]=response.status
        result["model_count"]=len(doc.get("data",[]))
    for package in ["torch","sglang","flashinfer"]:
        try:result["import_"+package]="ok" if importlib.import_module(package) else "unexpected"
        except Exception as exc:result["import_"+package]="error:"+type(exc).__name__
    try:
        import torch
        result["torch_version"]=torch.__version__
        result["cuda_available"]=bool(torch.cuda.is_available())
        if result["cuda_available"]:
            result["cuda_capability"]=list(torch.cuda.get_device_capability(0))
            result["cuda_device_name"]=torch.cuda.get_device_name(0)
    except Exception as exc:
        result["torch_cuda_error"]=type(exc).__name__
    out=subprocess.run(["nvidia-smi","--query-gpu=memory.total,memory.used",
                       "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=8)
    if out.returncode==0:
        result["vram_before_mb"]=out.stdout.strip().splitlines()[0]
    # A short authenticated warmup and five comparable streaming requests.
    try:
        result["warmup"]=benchmark_stream(key,32)
        result["runs"]=[benchmark_stream(key,128) for _ in range(5)]
        for name in ("ttft_s","decode_tokens_per_s","total_s"):
            v=[x[name] for x in result["runs"] if isinstance(x.get(name),(float,int))]
            result["median_"+name]=round(statistics.median(v),3) if v else None
        result["authenticated_first_inference"]="success"
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ValueError,KeyError) as exc:
        result["authenticated_first_inference"]="error:"+type(exc).__name__
        result["error_http_status"]=exc.code if isinstance(exc,urllib.error.HTTPError) else None
    out=subprocess.run(["nvidia-smi","--query-gpu=memory.total,memory.used",
                        "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=8)
    if out.returncode==0:result["vram_after_mb"]=out.stdout.strip().splitlines()[0]
    result["finished_utc"]=datetime.now(timezone.utc).isoformat()
    print("QWEN38_AUTHENTICATED_SMOKE "+json.dumps(result,sort_keys=True))
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("QWEN38_AUTHENTICATED_SMOKE "+json.dumps({"status":"failed","error_type":type(exc).__name__}))
        raise SystemExit(1)
