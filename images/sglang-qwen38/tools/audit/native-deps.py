#!/usr/bin/env python3
"""Read-only ELF dependency inventory inside an isolated CPU-only container.

Captures ELF DT_NEEDED, SONAME and R[UN]PATH, but no dlopen/dlsym, JIT or
GPU usage. Absence from DT_NEEDED is NOT evidence that a library is unused.
"""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

ROOTS = (
    "/opt/sglang/lib/python3.12/site-packages",
    "/usr/local/cuda-13.0",
    "/usr/lib/x86_64-linux-gnu",
    "/usr/local/lib",
    "/opt/nvidia",
)
RE_NEEDED = re.compile(r"\(NEEDED\).*?\[(.*?)\]")
RE_SONAME = re.compile(r"\(SONAME\).*?\[(.*?)\]")
RE_RPATH = re.compile(r"\((?:RUNPATH|RPATH)\).*?\[(.*?)\]")


def collect(minimum_bytes):
    for root in ROOTS:
        if not os.path.exists(root):
            continue
        for base, dirs, files in os.walk(root, followlinks=False):
            dirs.sort()
            for filename in sorted(files):
                path = os.path.join(base, filename)
                try:
                    if os.path.islink(path):
                        continue
                    size = os.stat(path).st_size
                    if size < minimum_bytes:
                        continue
                    with open(path, "rb") as source:
                        if source.read(4) != b"\x7fELF":
                            continue
                except (OSError, PermissionError):
                    continue
                try:
                    output = subprocess.run(
                        ["readelf", "-d", path], stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, text=True, timeout=10,
                        check=False,
                    )
                    text = output.stdout
                    yield {
                        "path": path, "bytes": size,
                        "needed": RE_NEEDED.findall(text),
                        "soname": RE_SONAME.findall(text),
                        "runpath": RE_RPATH.findall(text),
                        "readelf_code": output.returncode,
                    }
                except (OSError, subprocess.TimeoutExpired) as err:
                    yield {"path": path, "bytes": size, "error": str(err)[:180]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-mb", type=float, default=5.0)
    args = parser.parse_args()
    if args.min_mb < 0.1 or args.min_mb > 1000:
        parser.error("--min-mb must be between 0.1 and 1000")
    for row in collect(int(args.min_mb * 1e6)):
        print(json.dumps(row, separators=(",", ":")))


if __name__ == "__main__":
    main()
