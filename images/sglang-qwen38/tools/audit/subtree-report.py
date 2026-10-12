#!/usr/bin/env python3
"""CPU-only subtree totals over immutable file inventory JSONL."""
import argparse
import collections
import json
from pathlib import Path


def summarize(folder, prefix, depth):
    prefix = prefix.rstrip("/") + "/"
    totals = collections.Counter()
    by_suffix = collections.Counter()
    total = 0
    files = 0
    with (folder / "files.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row.get("k") != "file":
                continue
            path = row["p"]
            if not path.startswith(prefix):
                continue
            size = int(row["size"])
            total += size
            files += 1
            rel = path[len(prefix):].split("/")
            name = "/".join(rel[:depth])
            totals[name] += size
            by_suffix[Path(path).suffix or "(none)"] += size
    print(f"prefix={prefix} total={total/1e9:.3f} GB files={files}")
    for name, size in totals.most_common(60):
        print(f"  {size/1e9:8.3f} GB {name}")
    print("=== FILE EXTENSIONS ===")
    for name, size in by_suffix.most_common(14):
        print(f"  {size/1e9:8.3f} GB {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--depth", type=int, default=2)
    args = parser.parse_args()
    if args.depth < 1 or args.depth > 6:
        parser.error("depth must be 1..6")
    summarize(args.folder, args.prefix, args.depth)


if __name__ == "__main__":
    main()
