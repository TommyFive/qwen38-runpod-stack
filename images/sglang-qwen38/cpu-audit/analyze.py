#!/usr/bin/env python3
"""Summarize v1 OCI merged filesystem evidence from offline JSONL snapshots.

Computes logical bytes (NOT compressed layer savings). Never executes packages,
downloads assets or modifies image contents. Outputs auditable Markdown.
"""
import argparse
import collections
import json
from pathlib import Path

PREFIXES = (
    "/opt/sglang/lib/python3.12/site-packages/",
    "/sgl-workspace/",
    "/usr/local/",
    "/usr/lib/",
    "/opt/nvidia/",
    "/root/",
)


def walk_rows(filename):
    with filename.open(encoding="utf-8") as fh:
        for line in fh:
            yield json.loads(line)


def fmt(value):
    return f"{value / 1e9:,.3f}"


def analyze(folder):
    bytes_by_directory = collections.Counter()
    bytes_by_package = collections.Counter()
    bytes_by_ext = collections.Counter()
    candidates_by_name = collections.defaultdict(list)
    largest = []
    size_total = 0
    file_count = 0
    link_count = 0
    suffix_candidates = (".so", ".a", ".cubin", ".fatbin", ".ptx", ".bc", ".o")
    for row in walk_rows(folder / "files.jsonl"):
        if row["k"] == "link":
            link_count += 1
            continue
        if row["k"] != "file":
            continue
        file_count += 1
        name = row["p"]
        size = int(row["size"])
        size_total += size
        for base in PREFIXES:
            if name.startswith(base):
                relative = name[len(base):].split("/")
                if relative:
                    bytes_by_directory[base.rstrip("/") + "/" + relative[0]] += size
                if base == PREFIXES[0] and relative:
                    bytes_by_package[relative[0]] += size
                break
        suffix = Path(name).suffix.lower() or "(none)"
        bytes_by_ext[suffix] += size
        if size >= 10_000_000:
            largest.append((size, name))
        basename = name.rsplit("/", 1)[-1]
        if size >= 1_000_000 and (
            basename.endswith(suffix_candidates)
            or ".so." in basename
        ):
            candidates_by_name[(basename, size)].append(name)
    largest.sort(reverse=True)
    duplicates = sorted(
        [(len(paths), size, base, paths) for (base, size), paths
         in candidates_by_name.items() if len(paths) >= 2],
        key=lambda row: row[0] * row[1], reverse=True
    )
    dpkg = sorted(walk_rows(folder / "dpkg.jsonl"),
                  key=lambda x: int(x["installed_kib"]), reverse=True)
    python = list(walk_rows(folder / "python.jsonl"))
    return {
        "file_count": file_count, "link_count": link_count,
        "logical_bytes_total": size_total,
        "directories": bytes_by_directory.most_common(150),
        "site_packages": bytes_by_package.most_common(120),
        "extensions": bytes_by_ext.most_common(40),
        "largest_files": largest[:150],
        "possible_same_name_size": duplicates[:100],
        "dpkg": dpkg, "python": python,
    }


def report(data):
    out = [
        "# Qwen38 minimal-v1 CPU forensic inventory",
        "",
        "> READ-ONLY filesystem snapshot; **logical/uncompressed file bytes are",
        "> not equivalent to compressed OCI layer bytes**. Duplicate candidates",
        "> below match basename and size only, NOT cryptographic contents.",
        "",
        f"- Files: **{data['file_count']:,}**; symbolic links: **{data['link_count']:,}**",
        f"- Filesystem total: **{fmt(data['logical_bytes_total'])} decimal GB logical**",
        f"- Installed dpkg packages: **{len(data['dpkg'])}**",
        f"- Installed Python distributions: **{len(data['python'])}**",
        "",
    ]
    for label, rows, limit in [
        ("Largest tracked directories", data["directories"], 90),
        ("Largest Python top-level directories", data["site_packages"], 85),
        ("Largest individual files", data["largest_files"], 100),
    ]:
        out.extend([f"## {label}", "", "| Logical GB | Path |", "|---:|---|"])
        for first, second in rows[:limit]:
            path, size = (first, second) if isinstance(first, str) else (second, first)
            out.append(f"| {fmt(size)} | `{path}` |")
        out.append("")
    out.extend(["## Largest installed Ubuntu packages (reported installed-size)", "",
                "| MiB (dpkg) | Package |", "|---:|---|"])
    for row in data["dpkg"][:100]:
        out.append(f"| {row['installed_kib']/1024:,.1f} | `{row['name']}` |")
    out.extend(["", "## Possible duplicated .so/.a/cubin files (same filename and byte size)", "",
                "| Names | Each MB | Files |", "|---:|---:|---|"])
    for count, size, base, paths in data["possible_same_name_size"][:70]:
        out.append(f"| {count} | {size/1e6:,.1f} | `{base}`: " +
                   ", ".join(f"`{p}`" for p in paths[:3]) + " |")
    out.extend(["", "## Classification constraints", "",
                "Filesystem inventory does not establish that CUDA kernels, ",
                "FlashInfer cubins, JIT assets, ELF development headers or Python",
                "distributions can be safely deleted. CPU-only removal and rebuild",
                "experiments must be isolated and followed by RTX PRO 6000 SM120",
                "NVFP4+DFlash2 GPU correctness and cold/warm timing tests.", ""])
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--folder", type=Path, required=True)
    args = p.parse_args()
    result = analyze(args.folder)
    (args.folder / "summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    (args.folder / "summary.md").write_text(report(result), encoding="utf-8")
    print("PASS: created", args.folder / "summary.md")
    print("Logical file bytes:", fmt(result["logical_bytes_total"]), "GB")
    print("Files:", result["file_count"],
          "Python distributions:", len(result["python"]),
          "dpkg packages:", len(result["dpkg"]))
    print("Top directories:")
    for path, count in result["directories"][:18]:
        print(f" {fmt(count):>8} GB {path}")


if __name__ == "__main__":
    main()
