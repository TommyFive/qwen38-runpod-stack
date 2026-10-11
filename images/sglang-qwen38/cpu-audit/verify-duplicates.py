#!/usr/bin/env python3
"""Cryptographically verify *potential* duplicate native files from CPU audit.

Runs INSIDE the image with --read-only/--network none and no GPU. Reads only
paths produced by the inventory, limited to trusted system/library prefixes.
Exact hashes do not establish runtime loader substitutability.
"""
import argparse
import hashlib
import json
import os

ALLOWED = (
    "/opt/sglang/lib/python3.12/site-packages/",
    "/usr/local/",
    "/usr/lib/",
    "/opt/nvidia/",
)
SUMMARY = "/tmp/qwen38-summary.json"


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(4 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-file-mb", type=float, default=2000)
    parser.add_argument("--max-total-gb", type=float, default=12)
    args = parser.parse_args()
    if args.max_file_mb < 1 or args.max_total_gb < 0.1:
        parser.error("Invalid size budget")
    summary = json.load(open(SUMMARY, encoding="utf-8"))
    consumed = 0
    for count, size, name, paths in summary["possible_same_name_size"]:
        if size > args.max_file_mb * 1e6:
            continue
        if consumed + size * len(paths) > args.max_total_gb * 1e9:
            break
        if not all(
            path.startswith(ALLOWED) and not os.path.islink(path)
            and os.path.isfile(path) and os.path.getsize(path) == size
            for path in paths
        ):
            continue
        try:
            hashes = [digest(path) for path in paths]
        except OSError:
            continue
        consumed += size * len(paths)
        print(json.dumps({
            "name": name, "each_bytes": size, "paths": paths,
            "sha256": hashes, "all_identical": len(set(hashes)) == 1,
        }, separators=(",", ":")))


if __name__ == "__main__":
    main()
