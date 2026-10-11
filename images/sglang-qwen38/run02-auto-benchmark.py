#!/usr/bin/env python3
"""Wait for authenticated SGLang readiness and run exactly one standard benchmark.

Dedicated background helper for the user-approved 20 GiB Qwen38 run02.
No credential printing, no Pod creation/deletion. Stops trying after 25 min;
the separate live-watchdog is responsible for the paid Pod deadline.
"""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time

RP="/opt/homebrew/bin/runpodctl"
POD="fzt7b4jktp5gxj"
FOLDER=Path("/Users/rentamac/.local/share/qwen38-coldstart-tests/qwen38-imgtest-20261011-run02")
HERE=Path(__file__).resolve().parent
BENCH=HERE/"run02-standard-benchmark.py"

def stamp():return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
def ready():
    q=subprocess.run([RP,"pod","get",POD,"-o","json"],capture_output=True,text=True,timeout=25)
    if q.returncode:return False
    data=json.loads(q.stdout)
    if data.get("desiredStatus")!="RUNNING" or data.get("runtimeStatus")!="running":
        return False
    res=subprocess.run([RP,"pod","logs",POD,"--source","container",
        "--tail","1000","--max-wait","2s"],capture_output=True,text=True,timeout=20)
    if res.returncode:return False
    return ("health_generate_ready" in res.stdout or "Application startup complete" in res.stdout)
def main():
    FOLDER.mkdir(mode=0o700,parents=True,exist_ok=True)
    log=FOLDER/"standard-benchmark.log"
    print("COLLECTOR_START",stamp(),flush=True)
    deadline=time.monotonic()+25*60
    while time.monotonic()<deadline:
        try:
            if ready():
                print("HEALTH_READY",stamp(),flush=True)
                cmd=[sys.executable,str(BENCH),"--pod-id",POD,
                     "--output",str(FOLDER/"standard-benchmark.json")]
                for trial in (1,2):
                    res=subprocess.run(cmd,capture_output=True,text=True,timeout=900)
                    with log.open("a") as f:
                        f.write("TRIAL %d at %s\n%s\n" % (trial,stamp(),res.stdout))
                        f.write("EXITCODE %d\n" % res.returncode)
                    os.chmod(log,0o600)
                    print("STANDARD_BENCH_EXIT",res.returncode,"TRIAL",trial,flush=True)
                    if res.returncode==0:return 0
                    time.sleep(15)
                print("BENCHMARK_FAILED_TWICE",stamp(),flush=True)
                return 2
        except Exception as e:
            print("COLLECTOR_CHECK_ERROR",type(e).__name__,stamp(),flush=True)
        time.sleep(20)
    print("BENCHMARK_NEVER_READY",stamp(),flush=True)
    return 3

if __name__=="__main__":
    sys.exit(main())
