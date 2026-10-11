#!/usr/bin/env python3
"""Exact existing qwen38bench through proxy, adding Bearer auth outside the benchmark.

Uses unmodified qwen38bench.one_run: prompt, ISL8192 OSL1024, sampling,
single-stream, warmup, token counting remain unchanged. Auth key stays in RAM.
"""
import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys

EXPECTED_POD="fzt7b4jktp5gxj"
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
BENCH=REPO/"bin"/"qwen38bench"
SSH_KEY=Path("/Users/rentamac/.runpod/ssh/runpodctl-ssh-key")
RP="/opt/homebrew/bin/runpodctl"

def utc(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")

def read_key(ip,port):
    script="import sys; e=open('/proc/1/environ','rb').read().split(b'\\0'); v=[s.split(b'=',1)[1] for s in e if s.startswith(b'SGLANG_API_KEY=')]; sys.stdout.buffer.write(v[0] if len(v)==1 else b'')"
    argv=["ssh","-i",str(SSH_KEY),"-o","BatchMode=yes",
          "-o","StrictHostKeyChecking=accept-new","-o","ConnectTimeout=12",
          "-p",str(port),"root@"+ip,"/opt/sglang/bin/python3","-c",script]
    p=subprocess.run(argv,capture_output=True,timeout=25)
    key=p.stdout.decode("ascii",errors="replace").strip()
    if p.returncode or len(key)<24 or any(v in key for v in ("\n","\r"," ")):
        raise RuntimeError("Failed to retrieve API key from Pod privately")
    return key

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--pod-id",default=EXPECTED_POD)
    a.add_argument("--output",required=True,type=Path)
    a=a.parse_args()
    if a.pod_id!=EXPECTED_POD: raise RuntimeError("Pod mismatch")
    if not str(a.output).startswith("/Users/rentamac/.local/share/qwen38-coldstart-tests/qwen38-imgtest-20261011-run02/"):
        raise RuntimeError("Invalid private output location")
    r=subprocess.run([RP,"ssh","info",a.pod_id,"-o","json"],capture_output=True,text=True,timeout=20,check=True)
    endpoint=json.loads(r.stdout)
    if endpoint.get("id")!=a.pod_id:raise RuntimeError("SSH identity mismatch")
    token=read_key(endpoint["ip"],endpoint["port"])
    spec=importlib.util.spec_from_file_location("qwen38bench_reference",BENCH)
    q=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    q.HEADERS["Authorization"]="Bearer "+token
    del token
    api=f"https://{a.pod_id}-8000.proxy.runpod.net/v1"
    with q.get(f"{api}/models") as response:
        model=json.load(response)["data"][0]["id"]
    output={"schema":2,"benchmark":"bin/qwen38bench unmodified one_run",
            "run_id":"run02","pod_id":a.pod_id,"transport":"RunPod HTTPS proxy",
            "model":model,"isl_target":8192,"osl":1024,"runs":5,"warmup_discarded":True,
            "concurrency":1,"temperature":0.6,"top_p":0.95,"enable_thinking":False,
            "created_utc":utc(),"results":[]}
    print("STD_BENCH_BEGIN",output["created_utc"],flush=True)
    warm=q.one_run(api,model,8192,1024)
    output["warmup"]={**warm,"discarded":True}
    print("WARMUP_DISCARDED",round(warm["tps"],2),flush=True)
    for i in range(5):
        result=q.one_run(api,model,8192,1024)
        output["results"].append({"index":i+1,**result})
        print("STD_RUN",i+1,"TPS",round(result["tps"],3),
              "TTFT_MS",round(result["ttft"]*1000,1),
              "OUT_TOKENS",result["out_tokens"],flush=True)
    values=[x["tps"] for x in output["results"]]
    output["median_tps"]=statistics.median(values)
    output["median_ttft_ms"]=1000*statistics.median([x["ttft"] for x in output["results"]])
    output["tpot_ms"]=1000/output["median_tps"]
    server=q.server_info(api)
    output["server_info"]={k:server[k] for k in (
      "speculative_algorithm","avg_spec_accept_length","accept_length","max_running_requests",
      "context_length","max_total_tokens"
    ) if k in server}
    output["finished_utc"]=utc()
    a.output.write_text(json.dumps(output,indent=2)+"\n")
    os.chmod(a.output,0o600)
    print("STD_BENCH_DONE","MEDIAN_TPS",round(output["median_tps"],3),
          "TTFT_MS",round(output["median_ttft_ms"],1),flush=True)

if __name__=="__main__":
    try: main()
    except Exception as err:
        print("STD_BENCH_FAILED",type(err).__name__,file=sys.stderr)
        sys.exit(1)
