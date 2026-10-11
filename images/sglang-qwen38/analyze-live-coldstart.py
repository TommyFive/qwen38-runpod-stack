#!/usr/bin/env python3
"""Summarize locally recorded RunPod cold-start phases and SSD usage.

Offline, read-only, no credentials. Input must be one test folder containing
plan.json, creation.json, pod-events.jsonl and pod-status.jsonl.
Outputs short JSON, optionally writes a private derived summary.
"""
import argparse
import datetime as dt
import json
import re
from pathlib import Path

DISK=re.compile(r"QWEN38_DISK_SAMPLE\s+at=(\S+)\s+mount=(\S+)\s+total_bytes=(\d+)\s+used_bytes=(\d+)\s+free_bytes=(\d+)\s+used_percent=(\S+)")
PHASES=[
    ("first_image_download",re.compile(r"Downloading|fetching image",re.I)),
    ("first_image_extract",re.compile(r"Extracting",re.I)),
    ("container_create",re.compile(r"^create container ghcr\.io/",re.I)),
    ("container_boot",re.compile(r"start container|container started|container running|=== bootstrap",re.I)),
    ("network_probe",re.compile(r"network check|download probe",re.I)),
    ("model_fetch_start",re.compile(r"fetching weights|starting model download|model download start|MODEL_DOWNLOAD_START|HF.*download",re.I)),
    ("model_fetch_complete",re.compile(r"downloaded to|MODEL_DOWNLOAD_DONE|model downloaded",re.I)),
    ("cuda_start",re.compile(r"^--- starting SGLang|CUDA.*graph|capturing CUDA",re.I)),
    ("api_ready",re.compile(r"Uvicorn running|Application startup complete|Server is ready|SGLang is ready",re.I)),
    ("first_inference",re.compile(r"QWEN38_AUTHENTICATED_INFERENCE_SUCCESS",re.I)),
]
def when(s):
    if not s:return None
    if s.endswith("Z"):s=s[:-1]+"+00:00"
    try:return dt.datetime.fromisoformat(s)
    except ValueError:return None
def read_jsonl(path):
    if not path.exists():return []
    rows=[]
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:rows.append(json.loads(line))
            except (json.JSONDecodeError,TypeError):continue
    return rows
def summarize(folder):
    plan=json.loads((folder/"plan.json").read_text())
    creation=json.loads((folder/"creation.json").read_text()) if (folder/"creation.json").exists() else {}
    # The separate container --follow stream is needed because image-pull
    # events may displace the container tail in combined RunPod log queries.
    logs=read_jsonl(folder/"pod-events.jsonl")+read_jsonl(folder/"container-stream.jsonl")
    statuses=read_jsonl(folder/"pod-status.jsonl")
    events={}
    coldstart_events={}
    disk={}
    start=when(creation.get("before_api_utc") or plan.get("created_utc_start"))
    for log in logs:
        line=log.get("line") or ""
        at=when(log.get("ts") or log.get("captured_at_utc"))
        if not at:continue
        if line.startswith("QWEN38_COLDSTART "):
            try:
                item=json.loads(line.split(" ",1)[1])
                event_name=item.get("event")
                if isinstance(event_name,str) and event_name not in coldstart_events:
                    coldstart_events[event_name]={
                        "at_utc":item.get("utc"),"monotonic_s":item.get("mono"),
                        "since_pod_created_s":round((when(item.get("utc"))-start).total_seconds(),2) if start and when(item.get("utc")) else None
                    }
            except (json.JSONDecodeError,TypeError,ValueError):
                pass
        for label,regex in PHASES:
            if label not in events and regex.search(line):
                events[label]={"at_utc":at.isoformat(),"since_create_s":round((at-start).total_seconds(),1) if start else None,
                               "source":log.get("source")}
        m=DISK.search(line)
        if m:
            timestamp,mount,total,used,free,pct=m.groups()
            x=disk.setdefault(mount,{"samples":0,"peak_used_bytes":0,"min_free_bytes":None,
                                     "max_total_bytes":0,"first_at_utc":timestamp,"last_at_utc":timestamp})
            x["samples"]+=1
            x["peak_used_bytes"]=max(x["peak_used_bytes"],int(used))
            x["min_free_bytes"]=int(free) if x["min_free_bytes"] is None else min(x["min_free_bytes"],int(free))
            x["max_total_bytes"]=max(x["max_total_bytes"],int(total))
            x["last_at_utc"]=timestamp
    for log in statuses:
        k="runtime_"+str(log.get("runtimeStatus") or "unknown")
        if k not in events and when(log.get("at_utc")):
            at=when(log["at_utc"])
            events[k]={"at_utc":at.isoformat(),"since_create_s":round((at-start).total_seconds(),1) if start else None,"source":"RunPod API"}
    return {"schema":1,"created_utc":creation.get("before_api_utc"),"pod_id":creation.get("pod_id"),
            "image":plan.get("image_tag"),"image_digest":plan.get("manifest_digest"),
            "cloud":plan.get("cloud"),"gpu":plan.get("gpu"),
            "region_requested":plan.get("region"),"container_disk_gb":plan.get("container_disk_gb"),
            "cost_per_hour_usd":plan.get("rate_usd_hr"),"events":events,
            "native_coldstart_events":coldstart_events,"disk_mount_usage":disk,"log_events":len(logs),"status_samples":len(statuses),
            "note":"No timing assumes image cache cold; download and extract logs must be interpreted. Actual GPU readiness requires authenticated inference marker."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("folder",type=Path)
    p.add_argument("--write",action="store_true")
    a=p.parse_args()
    output=summarize(a.folder)
    blob=json.dumps(output,indent=2,ensure_ascii=False)+"\n"
    if a.write:
        (a.folder/"summary.json").write_text(blob,encoding="utf-8")
    print(blob)
if __name__=="__main__":main()
