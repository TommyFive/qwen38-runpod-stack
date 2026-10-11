#!/usr/bin/env python3
"""Durable local 30s resource telemetry. Never reads credentials or calls APIs."""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import signal
import time
from pathlib import Path

GIB = 1024 ** 3


def snapshot(build_log):
    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, val = line.partition(":")
        if key in ("MemTotal", "MemAvailable"):
            mem[key] = int(val.split()[0]) * 1024 / GIB
    disk = shutil.disk_usage("/var/lib/docker")
    try:
        with open(build_log, "rb") as src:
            src.seek(0, os.SEEK_END)
            src.seek(max(0, src.tell() - 131072))
            output = src.read().decode("utf-8", errors="replace")
        steps = re.findall(r"(?m)^#([0-9]{1,5})(?:[ \t]|$)", output)
    except OSError:
        steps = []
    return {
        "at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ram_total_gib": round(mem.get("MemTotal", 0), 2),
        "ram_used_gib": round(mem.get("MemTotal", 0) - mem.get("MemAvailable", 0), 2),
        "ram_available_gib": round(mem.get("MemAvailable", 0), 2),
        "ssd_total_gib": round(disk.total / GIB, 2),
        "ssd_used_gib": round(disk.used / GIB, 2),
        "ssd_free_gib": round(disk.free / GIB, 2),
        "buildkit_step_id": int(steps[-1]) if steps else None,
    }


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def guarded_stop(pid):
    try:
        if os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGINT)
    except (ProcessLookupError, PermissionError):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--interval", default=30, type=int)
    a = parser.parse_args()
    if a.pid <= 1 or a.interval < 10:
        parser.error("Invalid pid or interval")
    low = 0
    while alive(a.pid):
        try:
            result = snapshot(a.log)
            line = json.dumps(result, sort_keys=True)
            print("QWEN38_RESOURCE " + line, flush=True)
            with a.output.open("a", encoding="utf-8") as target:
                target.write(line + "\n")
                target.flush()
                os.fsync(target.fileno())
            free_ram = result["ram_available_gib"]
            low = low + 1 if free_ram < 4 else 0
            if free_ram < 2.5 or low >= 2 or result["ssd_free_gib"] < 30:
                print("ERROR: stopping isolated build due to critical resources", flush=True)
                guarded_stop(a.pid)
                break
        except (OSError, ValueError) as error:
            print(f"Resource probe skipped ({type(error).__name__})", flush=True)
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
