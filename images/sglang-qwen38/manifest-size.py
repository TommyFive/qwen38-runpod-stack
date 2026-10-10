#!/usr/bin/env python3
"""Offline OCI/Docker image manifest layer-size analysis (no registry credentials).

Input: JSON from 'docker buildx imagetools inspect --raw IMAGE', or a file.
For an index/manifest-list input, obtain the platform manifest by digest
first; never add manifest sizes as though they were image layers.

Example (after Docker has authenticated pull access):
  docker buildx imagetools inspect --raw ghcr.io/tommyfive/qwen38-sglang:candidate-cloudzy-4ad22cd0b56b |
    python3 images/sglang-qwen38/manifest-size.py
"""
import argparse
import json
import sys
from pathlib import Path

GIB = 1024 ** 3
GB = 10 ** 9


def summarize(doc):
    if not isinstance(doc, dict):
        raise ValueError("Expected OCI/Docker manifest JSON object")
    if "manifests" in doc:
        platforms = [
            (x.get("platform", {}).get("os"), x.get("platform", {}).get("architecture"),
             x.get("digest")) for x in doc["manifests"]
            if isinstance(x, dict)
        ]
        amd64 = [digest for os_name, arch, digest in platforms
                 if os_name == "linux" and arch == "amd64"]
        msg = "Manifest index, not a single-platform image manifest"
        if amd64:
            msg += f"; fetch linux/amd64 digest {amd64[0]} and rerun"
        raise ValueError(msg)
    layers = doc.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("Image manifest must contain nonempty layers array")
    valid = []
    for idx, item in enumerate(layers):
        if not isinstance(item, dict) or not isinstance(item.get("size"), int):
            raise ValueError(f"Missing integer byte count on layer #{idx+1}")
        if item["size"] < 0:
            raise ValueError(f"Negative size on layer #{idx+1}")
        if not isinstance(item.get("digest"), str) or not item["digest"].startswith("sha256:"):
            raise ValueError(f"Missing SHA256 digest on layer #{idx+1}")
        valid.append({"digest": item["digest"], "bytes": item["size"]})
    total = sum(x["bytes"] for x in valid)
    return {
        "layers": len(valid),
        "compressed_bytes": total,
        "compressed_decimal_gb": round(total / GB, 3),
        "compressed_gib": round(total / GIB, 3),
        "top_layers": sorted(valid, key=lambda x: -x["bytes"])[:8],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", default="-", help="manifest.json or '-' for stdin")
    parser.add_argument("--baseline-gb", type=float, default=14.676,
                        help="previous linux/amd64 source image compressed decimal GB")
    a = parser.parse_args()
    try:
        data = sys.stdin.read() if a.manifest == "-" else Path(a.manifest).read_text(encoding="utf-8")
        result = summarize(json.loads(data))
        if a.baseline_gb <= 0:
            raise ValueError("baseline must be positive")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    total = result["compressed_decimal_gb"]
    delta = result["compressed_bytes"] / (a.baseline_gb * GB) - 1
    print(f"Compressed registry layers: {result['compressed_bytes']:,} bytes "
          f"({total:.3f} GB decimal, {result['compressed_gib']:.3f} GiB)")
    print(f"Number of compressed layers: {result['layers']}")
    print(f"Baseline: {a.baseline_gb:.3f} GB decimal; difference: {delta:+.1%}")
    print("Largest compressed layers:")
    for entry in result["top_layers"]:
        print(f"  {entry['bytes']/GB:.3f} GB   {entry['digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
