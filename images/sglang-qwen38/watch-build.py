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


def memory_bytes(path="/proc/meminfo"):
    """Return (total, available) in bytes or (None, None) if unavailable."""
    values = {}
    try:
        for line in Path(path).read_text().splitlines():
            key, _, value = line.partition(":")
            if key in ("MemTotal", "MemAvailable"):
                values[key] = int(value.split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        return None, None
    return values.get("MemTotal"), values.get("MemAvailable")


def mem_available_bytes(path="/proc/meminfo"):
    """Keep simple compatibility with existing offline tests."""
    return memory_bytes(path)[1]


def should_publish(elapsed_seconds, since_last_seconds, before=120, after=30, switch_at=1800):
    """Two-minute heartbeat first, then 30-second heartbeat after minute 30."""
    if since_last_seconds is None:
        return True
    period = after if elapsed_seconds >= switch_at else before
    return since_last_seconds >= period


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
    disk_stat = shutil.disk_usage(disk)
    mem_total, mem_available = memory_bytes()
    return {
        "time_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "disk_free_gib": round(disk_stat.free / GIB, 2),
        "disk_used_gib": round(disk_stat.used / GIB, 2),
        "disk_total_gib": round(disk_stat.total / GIB, 2),
        "disk_used_percent": round(100 * disk_stat.used / disk_stat.total, 1) if disk_stat.total else None,
        "mem_available_gib": round(mem_available / GIB, 2) if mem_available is not None else None,
        "mem_used_gib": round((mem_total - mem_available) / GIB, 2) if mem_total is not None and mem_available is not None else None,
        "mem_total_gib": round(mem_total / GIB, 2) if mem_total is not None else None,
        "mem_used_percent": round(100 * (mem_total - mem_available) / mem_total, 1) if mem_total and mem_available is not None else None,
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
        f"Build elapsed: **{s.get('elapsed_seconds', 0) // 60} min {s.get('elapsed_seconds', 0) % 60:02d} s**",
        "PR update cadence: 120 s until minute 30, then 30 s; resource samples in Actions every 30 s.",
        (
            f"SSD used: **{s['disk_used_gib']:.2f} / {s['disk_total_gib']:.2f} GiB** "
            f"({s['disk_used_percent']:.1f} %), free: **{s['disk_free_gib']:.2f} GiB**"
        ),
        (
            f"RAM used: **{s['mem_used_gib']:.2f} / {s['mem_total_gib']:.2f} GiB** "
            f"({s['mem_used_percent']:.1f} %), available: **{s['mem_available_gib']:.2f} GiB**"
            if s["mem_used_gib"] is not None and s["mem_total_gib"] is not None
               and s["mem_used_percent"] is not None and s["mem_available_gib"] is not None
            else "RAM: unknown"
        ),
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


def memory_critical(available_gib, low_samples, low_threshold=2.5, hard_threshold=1.25):
    """Fail early before hosted runner OOM: immediate hard limit, or 2 samples."""
    if available_gib is None:
        return False, 0
    if available_gib < hard_threshold:
        return True, low_samples + 1
    if available_gib < low_threshold:
        count = low_samples + 1
        return count >= 2, count
    return False, 0


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
    ap.add_argument("--heartbeat-after-30m", type=int, default=30)
    ap.add_argument("--fast-start-seconds", type=int, default=1800)
    ap.add_argument("--min-free-disk-gib", type=float, default=12.0)
    ap.add_argument("--min-available-ram-gib", type=float, default=1.5)
    args = ap.parse_args()
    if (args.pid <= 1 or args.run_id <= 0 or args.interval < 5
            or args.heartbeat < args.interval
            or args.heartbeat_after_30m < args.interval or args.fast_start_seconds < 0):
        ap.error("Invalid PID, run ID, sampling interval, or heartbeat interval")
    # When Actions preflight has already proved comment rights, reuse its
    # comment instead of creating a second one. Never use arbitrary user text.
    try:
        comment_id = int(os.environ.get("QWEN38_STATUS_COMMENT_ID", "0")) or None
    except ValueError:
        ap.error("Invalid PR status comment ID")
    if comment_id is not None and comment_id <= 0:
        ap.error("Invalid PR status comment ID")
    started = time.monotonic()
    last_heartbeat = None
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
        elapsed = now - started
        s["elapsed_seconds"] = int(elapsed)
        state = "building"
        if s["disk_free_gib"] < args.min_free_disk_gib:
            state = "stopping: low disk"
            stopped = True
        # 16 GiB hosted runner ran from 2.33 GiB to 0.10 GiB available
        # between telemetry samples in failed run #38049903745. Three
        # consecutive samples at 1.5 GiB was too slow to prevent shutdown.
        mem_critical, consecutive_low_mem = memory_critical(
            s["mem_available_gib"], consecutive_low_mem,
            low_threshold=max(args.min_available_ram_gib, 2.5)
        )
        if mem_critical:
            state = "stopping: critically low RAM"
            stopped = True
        # Emit machine usage to the Actions console every 30 seconds; publish
        # one redacted PR comment every 2 minutes, switching to 30 seconds at 30m.
        print("Resource sample: " + json.dumps(s, sort_keys=True), flush=True)
        since_last = None if last_heartbeat is None else now - last_heartbeat
        if should_publish(elapsed, since_last, args.heartbeat,
                          args.heartbeat_after_30m, args.fast_start_seconds) or stopped:
            comment_id = github_comment(make_comment(s, args.run_id, state), comment_id)
            last_heartbeat = now
        if stopped:
            stop_build(args.pid, state)
            return 1
        time.sleep(args.interval)
    try:
        s = snapshot(args.log, args.disk)
        s["elapsed_seconds"] = int(time.monotonic() - started)
        print("Last resource checkpoint: " + json.dumps(s, sort_keys=True), flush=True)
        github_comment(make_comment(s, args.run_id, "build process ended (result unknown)"), comment_id)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
