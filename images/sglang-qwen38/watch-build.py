#!/usr/bin/env python3
"""No-secret, durable GitHub Actions resource telemetry for an explicit image build.

Only numeric BuildKit step identifiers and machine resource statistics are
published to ONE PR comment. Never publish raw build output, credentials, paths
to model weights, or environment variables. Safe to run without a token.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import signal
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

GIB = 1024 ** 3
MARKER = "<!-- qwen38-image-resource-watch -->"


def mem_available_bytes(path="/proc/meminfo"):
    try:
        for line in Path(path).read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def oom_kills(path="/sys/fs/cgroup/memory.events"):
    try:
        for line in Path(path).read_text().splitlines():
            if line.startswith("oom_kill "):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def last_buildkit_step(path):
    try:
        with open(path, "rb") as log:
            log.seek(0, os.SEEK_END)
            length = log.tell()
            log.seek(max(0, length - 131072))
            data = log.read().decode("utf-8", errors="replace")
        steps = re.findall(r"(?m)^#([0-9]{1,5})(?:[ \t]|$)", data)
        return int(steps[-1]) if steps else None
    except OSError:
        return None


def snapshot(log_path, disk="/var/lib/docker"):
    disk_bytes = shutil.disk_usage(disk).free
    mem = mem_available_bytes()
    return {
        "time_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "disk_free_gib": round(disk_bytes / GIB, 2),
        "mem_available_gib": round(mem / GIB, 2) if mem is not None else None,
        "cgroup_oom_kill": oom_kills(),
        "buildkit_step_number": last_buildkit_step(log_path),
        "build_log_bytes": log_path.stat().st_size if log_path.exists() else 0,
    }


def make_comment(s, run_id, state):
    # No raw logs are embedded in public PR comments; counters only.
    return "\n".join([
        MARKER,
        "### Qwen38 image build: durable resource checkpoint",
        f"Run: https://github.com/TommyFive/qwen38-runpod-stack/actions/runs/{run_id}",
        f"State: **{state}**",
        f"Last checkpoint: {s['time_utc']}",
        f"Free disk: **{s['disk_free_gib']:.2f} GiB**",
        f"Available RAM: **{s['mem_available_gib']:.2f} GiB**" if s["mem_available_gib"] is not None else "Available RAM: unknown",
        f"cgroup oom_kill: {s['cgroup_oom_kill'] if s['cgroup_oom_kill'] is not None else 'unknown'}",
        f"Last BuildKit step ID: {s['buildkit_step_number'] if s['buildkit_step_number'] is not None else 'unknown'}",
        f"Build log size: {s['build_log_bytes']} bytes (contents **not** published here)",
        "",
        "This is a point-in-time heartbeat, **not proof of success**. "
        "If it stops updating and Actions marks the job failed, the last "
        "checkpoint remains available even when GitHub job logs are lost.",
    ])


def github_comment(body, previous_id=None):
    token = os.environ.get("GH_TOKEN")
    if not token:
        print("Diagnostic API token absent; keeping local telemetry only", file=sys.stderr, flush=True)
        return previous_id
    base = "https://api.github.com/repos/TommyFive/qwen38-runpod-stack/issues"
    if previous_id is None:
        method = "POST"
        url = f"{base}/21/comments"
    else:
        method = "PATCH"
        url = f"https://api.github.com/repos/TommyFive/qwen38-runpod-stack/issues/comments/{previous_id}"
    req = urllib.request.Request(
        url, data=json.dumps({"body": body}).encode("utf-8"), method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "qwen38-image-runner-telemetry",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            payload = json.load(response)
            return int(payload["id"])
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError) as exc:
        # Never log tokens, URLs or raw error bodies.
        status = getattr(exc, "code", "network")
        print(f"Diagnostic PR checkpoint unavailable (HTTP/status: {status})", file=sys.stderr, flush=True)
        return previous_id


def process_exists(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def stop_build(pid, reason):
    # The build is launched with setsid: signal ONLY that build process group.
    print(f"::error::Proactively stopping build: {reason}", flush=True)
    try:
        if os.getpgid(pid) != pid:
            print("::error::Refusing to signal a non-isolated process group", flush=True)
            return
        os.killpg(pid, signal.SIGINT)
    except (ProcessLookupError, PermissionError):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--run-id", type=int, required=True)
    ap.add_argument("--disk", default="/var/lib/docker")
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--heartbeat", type=int, default=120)
    ap.add_argument("--min-free-disk-gib", type=float, default=12.0)
    ap.add_argument("--min-available-ram-gib", type=float, default=1.5)
    args = ap.parse_args()
    if args.pid <= 1 or args.run_id <= 0 or args.interval < 5 or args.heartbeat < args.interval:
        ap.error("Invalid PID, run ID, sampling interval, or heartbeat interval")
    comment_id = None
    last_heartbeat = -args.heartbeat
    consecutive_low_mem = 0
    stopped = False
    while process_exists(args.pid):
        try:
            s = snapshot(args.log, args.disk)
        except OSError as exc:
            print(f"::warning::Resource sample unavailable ({type(exc).__name__})", flush=True)
            time.sleep(args.interval)
            continue
        now = time.monotonic()
        state = "building"
        if s["disk_free_gib"] < args.min_free_disk_gib:
            state = "stopping: low disk"
            stopped = True
        if s["mem_available_gib"] is not None and s["mem_available_gib"] < args.min_available_ram_gib:
            consecutive_low_mem += 1
        else:
            consecutive_low_mem = 0
        if consecutive_low_mem >= 3:
            state = "stopping: low RAM"
            stopped = True
        if now - last_heartbeat >= args.heartbeat or stopped:
            print("Resource checkpoint: " + json.dumps(s, sort_keys=True), flush=True)
            comment_id = github_comment(make_comment(s, args.run_id, state), comment_id)
            last_heartbeat = now
        if stopped:
            stop_build(args.pid, state)
            return 1
        time.sleep(args.interval)
    try:
        s = snapshot(args.log, args.disk)
        print("Last resource checkpoint: " + json.dumps(s, sort_keys=True), flush=True)
        github_comment(make_comment(s, args.run_id, "build process ended (result unknown)"), comment_id)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
