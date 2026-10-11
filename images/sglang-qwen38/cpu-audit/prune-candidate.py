#!/usr/bin/env python3
"""Fail-closed CPU-only v1 OCI repack pruning; never run on production.

Used as BuildKit read-only bind-mount in a disposable builder stage. Deletes
only explicitly permitted artifacts after SHA256 verification in cuda mode.
This script does NOT build or compile SGLang/CUDA/Rust, download, or publish.
"""
import argparse
import hashlib
import os
from pathlib import Path

RUST = Path("/sgl-workspace/sglang/rust/target/release/deps")
WHEEL = Path("/opt/sglang/lib/python3.12/site-packages/nvidia/cu13/lib")
SYSTEM = Path("/usr/local/cuda-13.0/targets/x86_64-linux/lib")
PAIRS = (
    ("libcublasLt.so.13", "libcublasLt.so.13.1.1.3"),
    ("libcufft.so.12", "libcufft.so.12.0.0.61"),
    ("libcusparse.so.12", "libcusparse.so.12.6.3.3"),
    ("libcusolver.so.12", "libcusolver.so.12.0.4.66"),
    ("libcurand.so.10", "libcurand.so.10.4.0.35"),
    ("libnvrtc.alt.so.13", "libnvrtc.alt.so.13.0.88"),
    ("libnvrtc.so.13", "libnvrtc.so.13.0.88"),
    ("libcusolverMg.so.12", "libcusolverMg.so.12.0.4.66"),
    ("libcublas.so.13", "libcublas.so.13.1.1.3"),
    ("libnvperf_host.so", "libnvperf_host.so"),
    ("libnvperf_target.so", "libnvperf_target.so"),
)
EXPECTED_CUDA_BYTES = 1679571048


def sha256(path):
    hash_ = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            hash_.update(chunk)
    return hash_.hexdigest()


def rust():
    if not RUST.is_dir() or RUST.is_symlink():
        raise ValueError("Expected Rust output directory missing or symlink")
    files = sorted(
        path for suffix in (".rlib", ".rmeta")
        for path in RUST.rglob("*" + suffix)
    )
    if any(not p.is_file() or p.is_symlink() for p in files):
        raise ValueError("Unexpected Rust output symlink/non-file")
    total = sum(p.stat().st_size for p in files)
    if not (1_500_000_000 <= total <= 1_900_000_000):
        raise ValueError(f"Rust expected byte envelope violated: {total}")
    for path in files:
        path.unlink()
    print(f"RUST REMOVED: {len(files)} files, {total} logical bytes")


def cuda():
    if not WHEEL.is_dir() or not SYSTEM.is_dir():
        raise ValueError("CUDA expected library directories absent")
    total = 0
    all_pairs = []
    for wheel_name, system_name in PAIRS:
        wheel = WHEEL / wheel_name
        system = SYSTEM / system_name
        if not wheel.is_file() or wheel.is_symlink():
            raise ValueError(f"Expected regular wheel file: {wheel_name}")
        if not system.is_file() or system.is_symlink():
            raise ValueError(f"Expected regular system file: {system_name}")
        a, b = wheel.stat().st_size, system.stat().st_size
        if a != b or sha256(wheel) != sha256(system):
            raise ValueError(f"CUDA files not identical: {wheel_name}")
        total += a
        all_pairs.append((wheel, system))
    if total != EXPECTED_CUDA_BYTES:
        raise ValueError(f"CUDA byte contract violated: {total}")
    # No mutations occur until EVERY candidate has been validated.
    for wheel, system in all_pairs:
        wheel.unlink()
        wheel.symlink_to(os.path.relpath(system, wheel.parent))
    for wheel, system in all_pairs:
        if not wheel.is_symlink() or wheel.resolve(strict=True) != system:
            raise ValueError(f"Broken CUDA link: {wheel}")
    print(f"CUDA DEDUP: {len(all_pairs)} verified symlinks, {total} logical bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("rust", "cuda"))
    args = parser.parse_args()
    {"rust": rust, "cuda": cuda}[args.mode]()
