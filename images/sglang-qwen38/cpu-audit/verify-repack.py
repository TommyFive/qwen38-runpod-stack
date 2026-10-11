#!/usr/bin/env python3
"""CPU-only validation of OCI-repacked Qwen38 image config and critical file paths.

No GPU, network, builds, downloads or mutation. Fail closed on differences.
"""
import argparse
import json
import subprocess

REFERENCE = ("ghcr.io/tommyfive/qwen38-sglang@sha256:"
             "1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd")


def inspect(name):
    raw = subprocess.check_output(["docker", "image", "inspect", name], text=True)
    return json.loads(raw)[0]["Config"]


def safe_run(image, shell_command):
    args = [
        "docker", "run", "--rm", "--pull", "never", "--read-only", "--network", "none",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--entrypoint", "/bin/bash", image, "-c", shell_command,
    ]
    return subprocess.run(args, check=False, capture_output=True, text=True, timeout=180)


def verify(image, mode):
    before, after = inspect(REFERENCE), inspect(image)
    unchanged = (
        "Env", "Entrypoint", "Cmd", "WorkingDir",
        "User", "ExposedPorts", "Volumes", "StopSignal",
    )
    for key in unchanged:
        if before.get(key) != after.get(key):
            raise ValueError(f"Metadata mismatch: {key}")
    baseline_labels = before.get("Labels") or {}
    candidate_labels = after.get("Labels") or {}
    for key, value in baseline_labels.items():
        if candidate_labels.get(key) != value:
            raise ValueError(f"Original label changed: {key}")
    if candidate_labels.get("ai.qwen38.experimental-repack") != mode:
        raise ValueError("Missing candidate label")
    rust_files = safe_run(image,
                          'find /sgl-workspace/sglang/rust/target/release/deps '
                          '\\( -name "*.rlib" -o -name "*.rmeta" \\) -type f | wc -l')
    if rust_files.returncode or rust_files.stdout.strip() != "0":
        raise ValueError("Rust intermediates still exist: " + rust_files.stdout)
    if mode == "rust-cuda":
        wheel = "/opt/sglang/lib/python3.12/site-packages/nvidia/cu13/lib"
        paths = ["libcublasLt.so.13", "libcufft.so.12", "libcusolver.so.12",
                 "libcusparse.so.12", "libcurand.so.10", "libnvrtc.so.13"]
        script = "set -e; " + "; ".join(f'test -L "{wheel}/{name}" && test -r "{wheel}/{name}"'
                                         for name in paths)
        result = safe_run(image, script)
        if result.returncode:
            raise ValueError("CUDA symlink/link resolution failed: " + result.stderr)
    print(f"PASS {mode}: preserved {len(unchanged)} config fields and original labels; "
          "removed Rust .rlib/.rmeta; CUDA symlinks checked where applicable")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image", required=True)
    p.add_argument("--mode", choices=["rust", "rust-cuda"], required=True)
    a = p.parse_args()
    verify(a.image, a.mode)
