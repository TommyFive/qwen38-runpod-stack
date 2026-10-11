#!/usr/bin/env python3
"""Isolated RunPod cold-start recorder (persistent local files, auto-delete test Pod).

No secrets are recorded. Uses runpodctl API; no external dependencies.
Only the exact user-authorized Qwen38 test Pod ID is allowed.
A verified max runtime guarantees local watchdog kill even if chat closes.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PREFIX="qwen38-imgtest-"
RP="/opt/homebrew/bin/runpodctl"
SENSITIVE=re.compile(r"(?i)(HF_TOKEN|SGLANG_API_KEY|TS_AUTHKEY|AUTHORIZATION|API_KEY|token|password)\s*[:=]\s*[^\s,;]+")
BEARER=re.compile(r"(?i)Bearer\s+[A-Za-z0-9._+/-]{12,}")
LONG_B64=re.compile(r"[A-Za-z0-9+/]{180,}={0,2}")

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")

def safe(line):
    return LONG_B64.sub("[REDACTED_BASE64]",BEARER.sub("Bearer [REDACTED]",SENSITIVE.sub(lambda m:m.group(1)+"=[REDACTED]",str(line))))[:5000]

def call(*args,timeout=12):
    try:
        r=subprocess.run([RP,*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as e:
        return False,"",type(e).__name__
    return r.returncode==0,r.stdout,safe(r.stderr[:220])

def append(folder,name,record):
    with (folder/name).open("a",encoding="utf-8") as f:
        f.write(json.dumps(record,ensure_ascii=False,separators=(",",":"))+"\n")
        f.flush()

def snapshot(folder,pod_id,seen):
    at=utc()
    ok,txt,error=call("pod","get",pod_id,"-o","json",timeout=15)
    if ok:
        try:
            v=json.loads(txt)
            values={k:v.get(k) for k in [
                "id","name","gpuId","gpuCount","cloudType","dataCenterId",
                "containerDiskInGb","volumeInGb","runtimeStatus","runtimeStatusReason",
                "desiredStatus","lastStatusChange","costPerHr","startTime"
            ] if k in v}
            append(folder,"pod-status.jsonl",{"at_utc":at,**values})
        except (json.JSONDecodeError,TypeError):
            append(folder,"errors.jsonl",{"at_utc":at,"op":"get","error":"non-json pod response"})
    else:
        append(folder,"errors.jsonl",{"at_utc":at,"op":"get","error":error})
    ok,txt,error=call("pod","logs",pod_id,"--tail","1000","--max-wait","2s",timeout=16)
    if ok:
        for line in txt.splitlines():
            try:
                v=json.loads(line)
            except json.JSONDecodeError:
                continue
            source=v.get("source")
            t=v.get("ts")
            msg=safe(v.get("line",""))
            key=hashlib.sha256((str(source)+"\0"+str(t)+"\0"+msg).encode()).hexdigest()
            if key in seen:continue
            seen.add(key)
            append(folder,"pod-events.jsonl",{"captured_at_utc":at,"source":source,"ts":t,"line":msg})
    else:
        append(folder,"errors.jsonl",{"at_utc":at,"op":"logs","error":error})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pod-id",required=True)
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--max-seconds",type=int,default=3300)
    p.add_argument("--interval",type=int,default=15)
    a=p.parse_args()
    if a.max_seconds < 300 or a.max_seconds > 7200: p.error("max-seconds must be 300..7200")
    if a.interval < 5 or a.interval > 120: p.error("interval must be 5..120")
    if not re.fullmatch(r"[a-z0-9]{8,32}",a.pod_id):p.error("invalid RunPod id")
    if not str(a.root).startswith("/Users/rentamac/.local/share/qwen38-coldstart-tests/"):
        p.error("Only private telemetry root on Mac mini is allowed")
    folder=a.root
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(folder,0o700)
    with (folder/"watchdog.pid").open("w") as f:f.write(str(os.getpid())+"\n")
    print("watchdog_started",utc(),"pod_id",a.pod_id,"timeout_s",a.max_seconds,flush=True)
    start=time.monotonic()
    seen=set()
    try:
        while time.monotonic()-start < a.max_seconds:
            snapshot(folder,a.pod_id,seen)
            time.sleep(a.interval)
    finally:
        snapshot(folder,a.pod_id,seen)
        append(folder,"watchdog-events.jsonl",{"at_utc":utc(),"action":"deadline-delete-attempt","pod_id":a.pod_id})
        ok,txt,err=call("pod","delete",a.pod_id,timeout=35)
        append(folder,"watchdog-events.jsonl",{
            "at_utc":utc(),"action":"deadline-delete-result",
            "pod_id":a.pod_id,"ok":ok,"error":err if not ok else ""
        })
        print("watchdog_finished",utc(),"auto_deleted",ok,flush=True)

if __name__=="__main__":
    main()
