#!/usr/bin/env python3
"""Read-only proof of duplicate CUDA runtime shared libraries.

Matches filenames by canonical .so stem (not identical basename) across apt
CUDA, PyTorch NVIDIA wheels, cuDNN and NCCL. A matching hash proves only
identical content, NOT that an installed library can be safely removed.
"""
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

ROOTS = (
    "/usr/local/cuda-13.0/targets/x86_64-linux/lib",
    "/usr/lib/x86_64-linux-gnu",
    "/opt/sglang/lib/python3.12/site-packages/nvidia/cu13/lib",
    "/opt/sglang/lib/python3.12/site-packages/nvidia/cudnn/lib",
    "/opt/sglang/lib/python3.12/site-packages/nvidia/nccl/lib",
)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(4 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def inspect():
    by_stem = defaultdict(list)
    for root in ROOTS:
        if not os.path.isdir(root):
            continue
        for entry in os.scandir(root):
            if not entry.is_file(follow_symlinks=False):
                continue
            if ".so" not in entry.name:
                continue
            st = entry.stat(follow_symlinks=False)
            if st.st_size < 5_000_000:
                continue
            stem = entry.name.split(".so", 1)[0]
            if stem and stem.startswith("lib"):
                by_stem[stem].append((entry.path, st.st_size))
    result = []
    for stem, paths in sorted(by_stem.items()):
        if len(paths) < 2:
            continue
        sizes = sorted(set(size for _, size in paths))
        hashes = {}
        if len(sizes) == 1:
            hashes = {path: sha(path) for path, _ in paths}
        result.append({
            "name": stem, "paths": [{"path": p, "bytes": n,
                                     **({"sha256": hashes[p]} if hashes else {})}
                                    for p, n in paths],
            "all_same_size": len(sizes) == 1,
            "all_same_hash": len(set(hashes.values())) == 1 if hashes else None,
        })
    return result


if __name__ == "__main__":
    for row in inspect():
        print(json.dumps(row, separators=(",", ":")))
