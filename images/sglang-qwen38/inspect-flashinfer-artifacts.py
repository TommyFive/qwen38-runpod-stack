#!/usr/bin/env python3
"""Conservative, READ-ONLY FlashInfer kernel footprint/architecture inventory.

Run inside a v1 candidate container. Never infers that a file is safe to remove:
path names and logical file bytes are NOT proof of runtime reachability or
compressed OCI savings. Symlinks are ignored; no imports, JIT or network calls.
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

# Only explicit architecture tokens are classified. Filenames without tokens,
# mixed architecture fatbins, and ambiguous packaging MUST remain untouched.
ARCH = re.compile(r"(?i)(?<![a-z0-9])(?:sm|compute)[_-]?([0-9]{2,3}[afp]?)(?![a-z0-9])")
PACKAGES = ("flashinfer_cubin", "flashinfer_jit_cache")


def classify(relative_path):
    # Documentation and Python source references to SM120 are not kernel assets.
    if not relative_path.lower().endswith((".cubin", ".fatbin", ".so", ".bin", ".ptx")):
        return "unknown", []
    arches = sorted(set(m.group(1).lower() for m in ARCH.finditer(relative_path)))
    if not arches:
        return "unknown", arches
    if len(arches) > 1:
        return "multi_arch", arches
    if arches[0].startswith("120"):
        return "sm120_named", arches
    return "other_arch_named", arches


def inspect(site_packages, sample_limit=3):
    if not site_packages.is_dir():
        raise ValueError("Missing site-packages: " + str(site_packages))
    report = {"schema": 1, "site_packages": str(site_packages), "packages": {}}
    for package in PACKAGES:
        root = site_packages / package
        if not root.is_dir() or root.is_symlink():
            raise ValueError("Missing/non-directory required package: " + package)
        groups = defaultdict(lambda: {"files": 0, "logical_bytes": 0, "examples": []})
        architectures = defaultdict(lambda: {"files": 0, "logical_bytes": 0})
        skipped_links = 0
        for path in root.rglob("*"):
            if path.is_symlink():
                skipped_links += 1
                continue
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            category, arches = classify(relative)
            size = path.stat().st_size
            row = groups[category]
            row["files"] += 1
            row["logical_bytes"] += size
            if len(row["examples"]) < sample_limit:
                row["examples"].append(relative)
            for arch in arches:
                architectures[arch]["files"] += 1
                architectures[arch]["logical_bytes"] += size
        report["packages"][package] = {
            "logical_bytes": sum(v["logical_bytes"] for v in groups.values()),
            "files": sum(v["files"] for v in groups.values()),
            "skipped_symlinks": skipped_links,
            "by_path_category": dict(sorted(groups.items())),
            "by_arch_token": dict(sorted(architectures.items())),
        }
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--site-packages", type=Path, default=Path("/opt/sglang/lib/python3.12/site-packages"))
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    try:
        report = inspect(args.site_packages)
    except (OSError, ValueError) as exc:
        p.error(str(exc))
    if args.json:
        print(json.dumps(report, indent=2))
        return
    for name, data in report["packages"].items():
        print(f"== {name}: {data['logical_bytes']/1e9:.3f} GB logical ({data['files']} files) ==")
        for category, row in data["by_path_category"].items():
            print(f"  {category:19s} {row['logical_bytes']/1e9:8.3f} GB  {row['files']:7d} files")
        print("  Explicit architecture tokens:", ", ".join(data["by_arch_token"]) or "(none)")
        print(f"  Ignored symlinks: {data['skipped_symlinks']}")
    print("READ ONLY. Do not delete by path-name, calculate OCI savings from logical bytes,")
    print("or infer SM120-only runtime correctness; verify JIT, NVFP4 and DFlash2 on a GPU.")


if __name__ == "__main__":
    main()
