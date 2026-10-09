#!/usr/bin/env python3
"""Bounded, single-stream, in-pod SGLang benchmark (stdlib only).

No full prompts, completions, authorization headers or server-info dumps are
persisted. This program is deliberately independent of RunPod's public proxy.
"""
import importlib.metadata
import json
import os
from pathlib import Path
import re
import signal
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "http://127.0.0.1:8000/v1"
SCHEMA_VERSION = 1
PROMPT_SET_REVISION = "qwen38-sglang-v1"
WORKLOADS = (
    ("technical", "Explain how speculative decoding verifies draft tokens against a "
     "target model, including the acceptance rule, latency trade-offs and failure modes."),
    ("code", "Write a self-contained Python 3 function that merges sorted iterators "
     "without materializing their inputs. Include type hints, complexity analysis and "
     "three small test cases."),
    ("code_edit", "Fix this Python code to handle empty inputs and duplicate values, "
     "then explain the bug and give tests:\n"
     "def unique_sorted(items):\n"
     "    result = [items[0]]\n"
     "    for item in items:\n"
     "        if item != result[-1]: result.append(item)\n"
     "    return result\n"),
)


class BenchmarkError(Exception):
    pass


class DeadlineExceeded(BenchmarkError):
    pass


class Unauthorized(BenchmarkError):
    pass


def positive_int(name, default, maximum):
    value = os.environ.get(name, str(default))
    if not re.fullmatch(r"[0-9]+", value):
        raise BenchmarkError(f"{name} must be a positive integer (max {maximum})")
    n = int(value)
    if not 1 <= n <= maximum:
        raise BenchmarkError(f"{name} must be between 1 and {maximum}")
    return n


def settings():
    return {
        "runs": positive_int("BENCHMARK_RUNS", 3, 20),
        "max_tokens": positive_int("BENCHMARK_MAX_TOKENS", 512, 4096),
        "timeout_seconds": positive_int("BENCHMARK_TIMEOUT_SECONDS", 900, 7200),
        "report_path": os.environ.get("BENCHMARK_REPORT_PATH") or "/tmp/qwen38-benchmark.json",
    }


def time_left(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DeadlineExceeded("benchmark deadline reached")
    return remaining


def headers():
    out = {"Content-Type": "application/json", "Accept": "application/json"}
    key = os.environ.get("SGLANG_API_KEY", "")
    if key:
        out["Authorization"] = "Bearer " + key
    return out


def request(url, payload=None, timeout=5.0):
    data = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers())
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        # Never include body, URL, request payload or headers in an exception.
        if e.code in (401, 403):
            raise Unauthorized("SGLang authentication failed (HTTP 401/403)") from None
        raise BenchmarkError(f"SGLang returned HTTP {e.code}") from None


def ready_model(deadline, retry_delay=2.0):
    """Poll authenticated loopback until models exist; unauthorized fails fast."""
    while True:
        remaining = time_left(deadline)
        try:
            with request(API + "/models", timeout=min(5.0, remaining)) as r:
                if r.status == 200:
                    data = json.load(r)
                    models = data.get("data") or []
                    if models and isinstance(models[0].get("id"), str):
                        return models[0]["id"]
        except (Unauthorized, DeadlineExceeded):
            raise
        except (BenchmarkError, OSError, ValueError, KeyError):
            pass
        time.sleep(min(retry_delay, time_left(deadline)))


def _has_output(delta):
    """SSE events are NOT tokens. Detect first meaningful text/reasoning/tool output."""
    if not isinstance(delta, dict):
        return False
    if any(isinstance(delta.get(k), str) and delta[k]
           for k in ("content", "reasoning_content")):
        return True
    for tool in delta.get("tool_calls") or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") or {}
        if isinstance(fn, dict) and (fn.get("arguments") or fn.get("name")):
            return True
    return False


def _sse_events(response):
    """Assemble SSE data fields; tolerate comments, empty lines and split chunks."""
    parts = []
    for raw in response:
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if parts:
                yield "\n".join(parts)
                parts = []
        elif line.startswith("data:"):
            parts.append(line[5:].lstrip(" "))
    if parts:
        yield "\n".join(parts)


def one_run(model, prompt, max_tokens, deadline):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    start = time.monotonic()
    first = None
    usage = None
    completed = False
    with request(API + "/chat/completions", payload,
                 timeout=min(30.0, time_left(deadline))) as resp:
        for event in _sse_events(resp):
            time_left(deadline)
            if not event:
                continue
            if event == "[DONE]":
                completed = True
                break
            try:
                part = json.loads(event)
            except ValueError:
                raise BenchmarkError("invalid SSE JSON") from None
            if part.get("error"):
                raise BenchmarkError("SGLang returned a stream error")
            if isinstance(part.get("usage"), dict):
                usage = part["usage"]
            if first is None and any(_has_output(choice.get("delta"))
                                     for choice in part.get("choices") or []):
                first = time.monotonic()
    end = time.monotonic()
    time_left(deadline)
    if not completed:
        raise BenchmarkError("incomplete SSE stream (missing [DONE])")
    prompt_tokens = usage.get("prompt_tokens") if usage else None
    completion_tokens = usage.get("completion_tokens") if usage else None
    if not isinstance(prompt_tokens, int) or prompt_tokens < 0:
        prompt_tokens = None
    if not isinstance(completion_tokens, int) or completion_tokens < 0:
        completion_tokens = None
    ttft = first - start if first is not None else None
    wall = end - start
    decode = end - first if first is not None else None
    # TTFT includes the first output token, so decode contains only N-1 gaps.
    tpot = (decode / (completion_tokens - 1)
            if decode is not None and completion_tokens is not None
            and completion_tokens > 1 and decode > 0 else None)
    return {
        "wall_seconds": wall,
        "ttft_seconds": ttft,
        "decode_seconds": decode,
        "tpot_seconds": tpot,
        "decode_tokens_per_second": 1 / tpot if tpot else None,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "token_count_source": "server_usage" if completion_tokens is not None else "unavailable",
        "first_output_observed": first is not None,
    }


def _version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _gpu_metadata():
    output = {"devices": [], "topology": None}
    try:
        raw = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,compute_cap",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, timeout=5,
        ).stdout
        for line in raw.splitlines()[:16]:
            fields = [s.strip() for s in line.split(",")]
            if len(fields) == 5:
                output["devices"].append(dict(zip(
                    ("index", "name", "vram_mib", "vram_used_mib", "compute_capability"),
                    fields)))
        topo = subprocess.run(["nvidia-smi", "topo", "-m"], capture_output=True,
                              text=True, check=True, timeout=5).stdout
        output["topology"] = topo[:4096]
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return output


def _model_metadata():
    source = Path(os.environ.get("MODEL_PATH", "/nonexistent"))
    revision = source.name if re.fullmatch(r"[0-9a-f]{7,64}", source.name) else None
    quantization = None
    try:
        config = json.loads((source / "config.json").read_text())
        q = config.get("quantization_config") or {}
        if isinstance(q, dict):
            quantization = {k: q[k] for k in
                            ("quant_method", "format", "bits", "group_size")
                            if isinstance(q.get(k), (str, int, float))}
    except (OSError, ValueError):
        pass
    return {
        "model_id": os.environ.get("MODEL_ID"),
        "checkpoint_revision": revision,
        "quantization": quantization,
        "served_name": os.environ.get("SERVED_NAME"),
        "spec": os.environ.get("SPEC"),
        "draft_model": {"dflash2": "incoai/Qwen3.8-27B-DFlash2",
                        "dspark": "RadixArk/Qwen3.8-27B-DSpark"}.get(
                            os.environ.get("SPEC")),
        "context_length": os.environ.get("MAX_LEN"),
        "mem_fraction_static": os.environ.get("MEM_FRAC"),
        "mamba_full_memory_ratio": os.environ.get("MAMBA_RATIO"),
    }


def _median(results, key):
    nums = [r[key] for r in results if r[key] is not None]
    return statistics.median(nums) if nums else None


def _safe_report(report, path):
    """Never leave an incomplete JSON file; private permissions even on failure."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".qwen38-bench-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(report, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _summary(report):
    print("### Qwen38 in-pod SGLang benchmark (single-stream, loopback)", flush=True)
    print(f"status={report['status']} prompt_set={PROMPT_SET_REVISION}", flush=True)
    for work in report["workloads"]:
        measured = work["measurements"]
        ttft = _median(measured, "ttft_seconds")
        tps = _median(measured, "decode_tokens_per_second")
        print(f"{work['id']}: {len(measured)} measured, "
              f"TTFT={ttft * 1000:.1f}ms" if ttft is not None else
              f"{work['id']}: {len(measured)} measured, TTFT=n/a",
              end=" | ", flush=True)
        print(f"decode={tps:.1f} tok/s" if tps is not None
              else "decode=n/a (usage unavailable)", flush=True)


def _deadline_alarm(_signal, _frame):
    raise DeadlineExceeded("benchmark deadline reached")


def _terminated(_signal, _frame):
    raise BenchmarkError("benchmark stopped by pod shutdown")


def main():
    os.umask(0o077)
    started = datetime.now(timezone.utc).isoformat()
    try:
        cfg = settings()
    except BenchmarkError as e:
        print(f"benchmark configuration error: {e}", file=sys.stderr)
        return 64

    report = {
        "schema_version": SCHEMA_VERSION,
        "prompt_set_revision": PROMPT_SET_REVISION,
        "started_utc": started,
        "completed_utc": None,
        "status": "in_progress",
        "error": None,
        "config": {"runs": cfg["runs"], "max_tokens": cfg["max_tokens"],
                   "timeout_seconds": cfg["timeout_seconds"], "concurrency": 1,
                   "stream": True, "temperature": 0, "thinking_requested": False,
                   "endpoint": "loopback", "usage_source": "SGLang SSE usage"},
        "software": {"sglang": _version("sglang"), "torch": _version("torch")},
        "gpu": _gpu_metadata(),
        "model": _model_metadata(),
        "workloads": [],
        "speculative_acceptance": None,
        "speculative_acceptance_note": "unavailable: metrics not enabled/verified",
    }
    signal.signal(signal.SIGALRM, _deadline_alarm)
    signal.signal(signal.SIGTERM, _terminated)
    signal.signal(signal.SIGINT, _terminated)
    signal.setitimer(signal.ITIMER_REAL, cfg["timeout_seconds"])
    deadline = time.monotonic() + cfg["timeout_seconds"]
    exit_code = 0
    try:
        model = ready_model(deadline)
        for workload_id, prompt in WORKLOADS:
            item = {"id": workload_id, "warmup_excluded": True, "measurements": []}
            report["workloads"].append(item)
            one_run(model, prompt, cfg["max_tokens"], deadline)  # discarded
            for _ in range(cfg["runs"]):
                item["measurements"].append(
                    one_run(model, prompt, cfg["max_tokens"], deadline))
        report["status"] = "completed"
    except (BenchmarkError, OSError, ValueError) as e:
        report["status"] = "failed"
        # No exception strings from urllib/requests: they can contain URLs.
        report["error"] = str(e) if isinstance(e, BenchmarkError) else type(e).__name__
        exit_code = 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        report["completed_utc"] = datetime.now(timezone.utc).isoformat()
        try:
            _safe_report(report, cfg["report_path"])
        except OSError:
            print("benchmark report write failed", file=sys.stderr)
            exit_code = 1
        _summary(report)
        print(f"benchmark result={report['status']} (report path configured by "
              "BENCHMARK_REPORT_PATH)", flush=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
