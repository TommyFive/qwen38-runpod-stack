#!/usr/bin/env python3
"""Forensic READ-ONLY image inventory (stdlib-only, no imports from SGLang).

Executed INSIDE the published OCI image with no GPU, no network, readonly rootfs
and all capabilities dropped. Emits JSON Lines to stdout; caller owns storage.
This program never deletes, installs, executes image apps, or follows symlinks.
"""
import argparse
import importlib.metadata
import json
import os
import stat
from pathlib import Path

BLOCKED = {"proc", "sys", "dev", "run", "tmp", "audit", "mnt"}
SITE = "/opt/sglang/lib/python3.12/site-packages"


def emit(value):
    print(json.dumps(value, separators=(",", ":"), ensure_ascii=True))


def record(path):
    try:
        st = os.lstat(path)
    except (PermissionError, FileNotFoundError, OSError):
        return None
    kind = "link" if stat.S_ISLNK(st.st_mode) else (
        "file" if stat.S_ISREG(st.st_mode) else (
            "dir" if stat.S_ISDIR(st.st_mode) else "other"
        )
    )
    d = {
        "k": kind, "p": os.fspath(path), "size": st.st_size if kind == "file" else 0,
        "alloc": st.st_blocks * 512 if kind == "file" else 0,
        "mode": stat.S_IMODE(st.st_mode), "nlink": st.st_nlink,
        "dev": st.st_dev, "inode": st.st_ino,
    }
    if kind == "link":
        try:
            d["target"] = os.readlink(path)
        except OSError:
            d["target"] = None
    return d


def walk():
    for base, dirs, files in os.walk("/", topdown=True, followlinks=False):
        if base == "/":
            dirs[:] = sorted(x for x in dirs if x not in BLOCKED)
        else:
            dirs.sort()
        for name in sorted(dirs + files):
            path = os.path.join(base, name)
            r = record(path)
            if r is not None:
                emit(r)


def python_distributions():
    for dist in sorted(
        importlib.metadata.distributions(path=[SITE]),
        key=lambda d: (d.metadata.get("Name") or "").lower()
    ):
        name = dist.metadata.get("Name", "(unnamed)")
        files = dist.files
        emit({
            "name": name,
            "version": dist.version,
            "requires": list(dist.requires or []),
            "reported_files": len(files) if files is not None else None,
        })


def dpkg_status():
    p = Path("/var/lib/dpkg/status")
    if not p.is_file():
        return
    raw = p.read_text(encoding="utf-8", errors="replace")
    for paragraph in raw.split("\n\n"):
        values = {}
        last = None
        for line in paragraph.splitlines():
            if line.startswith(" ") and last:
                values[last] += " " + line.strip()
            elif ": " in line:
                last, value = line.split(": ", 1)
                values[last] = value
        if values.get("Status") == "install ok installed":
            emit({
                "name": values.get("Package"), "version": values.get("Version"),
                "installed_kib": int(values.get("Installed-Size", "0")),
                "depends": values.get("Depends", ""),
                "section": values.get("Section", ""),
            })


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", required=True, choices=("files", "python", "dpkg"))
    args = p.parse_args()
    {"files": walk, "python": python_distributions, "dpkg": dpkg_status}[args.mode]()


if __name__ == "__main__":
    main()
