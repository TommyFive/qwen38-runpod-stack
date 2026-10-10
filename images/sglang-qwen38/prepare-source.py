#!/usr/bin/env python3
"""Fail-closed, minimal, reproducible Qwen38 overlay for a pinned SGLang checkout.

Never edit the caller's own repository or fetch arbitrary upstream branches.
This script only changes python/pyproject.toml in a dedicated build checkout.
"""
import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

MARKER = "[project.optional-dependencies]\n"
EXTRA = "qwen38-minimal"
REQUIRED_PINS = (
    "torch==2.13.0",
    "flashinfer_python[cu13]==0.6.17",
    "sglang-kernel==0.4.6.post1",
)


def inject_empty_extra(source: str) -> str:
    """Add a deliberate zero-additional-dependency extra; preserve base packages."""
    if source.count(MARKER) != 1:
        raise ValueError("Expected exactly one [project.optional-dependencies] section")
    original = tomllib.loads(source)
    extras = original["project"]["optional-dependencies"]
    if EXTRA in extras:
        raise ValueError("Refusing an already modified SGLang project")
    deps = original["project"]["dependencies"]
    for dependency in REQUIRED_PINS:
        if dependency not in deps:
            raise ValueError(f"Pinned SGLang dependency missing: {dependency}")
    updated = source.replace(MARKER, MARKER + EXTRA + " = []\n", 1)
    revised = tomllib.loads(updated)
    if revised["project"]["dependencies"] != deps:
        raise ValueError("Base dependencies changed unexpectedly")
    if revised["project"]["optional-dependencies"][EXTRA] != []:
        raise ValueError("The minimal extra is not empty")
    for name, packages in extras.items():
        if revised["project"]["optional-dependencies"][name] != packages:
            raise ValueError(f"Upstream extra changed unexpectedly: {name}")
    return updated


def git(source: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(source), *args], text=True, stderr=subprocess.PIPE
    ).strip()


def prepare(source: Path, lock_path: Path) -> None:
    source = source.resolve(strict=True)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock["target"] != "runtime" or lock["build_type"] != EXTRA:
        raise ValueError("Unexpected image target or build type")
    if git(source, "rev-parse", "HEAD") != lock["upstream_commit"]:
        raise ValueError("Wrong upstream commit; refusing to patch")
    if git(source, "status", "--porcelain"):
        raise ValueError("Upstream worktree is not clean")
    for path, expected in (
        ("python/pyproject.toml", lock["upstream_pyproject_blob"]),
        ("docker/Dockerfile", lock["upstream_dockerfile_blob"]),
    ):
        if git(source, "rev-parse", "HEAD:" + path) != expected:
            raise ValueError(f"Unexpected upstream blob for {path}")
    pyproject = source / "python/pyproject.toml"
    original = pyproject.read_text(encoding="utf-8")
    patched = inject_empty_extra(original)
    pyproject.write_text(patched, encoding="utf-8")
    if git(source, "status", "--porcelain") != " M python/pyproject.toml":
        raise ValueError("Unexpected files modified by overlay")
    print(
        f"PASS: pinned SGLang {lock['upstream_commit'][:12]} "
        f"with empty {EXTRA} extra; CUDA/FlashInfer untouched."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path(__file__).with_name("upstream.lock.json"),
    )
    args = parser.parse_args()
    try:
        prepare(args.source, args.lock)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
