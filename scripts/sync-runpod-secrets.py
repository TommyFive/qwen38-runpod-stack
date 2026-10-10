#!/usr/bin/env python3
"""Synchronize existing QWEN38 templates with RunPod Secret references safely.

No pods launched, no secret values read or printed. Requires RUNPOD_API_KEY.
"""
import importlib.util
import base64
import os
from pathlib import Path
import re
import sys

path = Path(__file__).with_name("private-template-ports.py")
spec = importlib.util.spec_from_file_location("qwen38_private_ports", path)
ports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ports)

SECRET_KEYS = ("TS_AUTHKEY", "SGLANG_API_KEY", "HF_TOKEN", "WEBUI_ADMIN_PASSWORD")
BUNDLED_HELPERS = {
    "BOOTSTRAP_B64": "scripts/bootstrap-sglang-openwebui.sh",
    "TAILSCALE_RUNTIME_B64": "scripts/tailscale-runtime.sh",
    "STORAGE_HELPER_B64": "scripts/model-storage.py",
    "BENCHMARK_B64": "scripts/benchmark_sglang.py",
}


def read_bundled_helpers():
    """Only trusted checkout files; never read keys, API configuration or tokens."""
    repo = Path(__file__).resolve().parents[1]
    result = {}
    for key, relative in BUNDLED_HELPERS.items():
        source = repo / relative
        if not source.is_file() or source.is_symlink():
            raise ports.PortSafetyError("missing or symlinked bundled helper: " + relative)
        result[key] = base64.b64encode(source.read_bytes()).decode("ascii")
    return result

API_REFERENCE = "{{ RUNPOD_SECRET_LLAMA_API_KEY }}"
TS_REFERENCE = "{{ RUNPOD_SECRET_TS_AUTHKEY }}"


def make_env(existing, mode, hf_secret, helpers=None):
    if not isinstance(existing, dict):
        raise ports.PortSafetyError("template env is missing or malformed")
    if mode not in ("runpod", "tailnet") or existing.get("NETWORK_MODE") != mode:
        raise ports.PortSafetyError("template NETWORK_MODE mismatch")
    if not existing.get("BOOTSTRAP_B64") or not existing.get("TAILSCALE_RUNTIME_B64"):
        raise ports.PortSafetyError("missing bootstrap or Tailscale runtime")
    if hf_secret and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", hf_secret):
        raise ports.PortSafetyError("invalid Hugging Face secret name")
    if "WEBUI_ADMIN_PASSWORD" in existing:
        raise ports.PortSafetyError("pre-existing WEBUI_ADMIN_PASSWORD; refuses to copy it")
    new = dict(existing)
    new.setdefault("MODEL_RAM_RELEASE_AFTER_LOAD", "0")
    if helpers is not None:
        if set(helpers) != set(BUNDLED_HELPERS) or not all(helpers.values()):
            raise ports.PortSafetyError("incomplete helper bundle")
        if any(not existing.get(key) for key in BUNDLED_HELPERS):
            raise ports.PortSafetyError("template is missing an embedded helper")
        new.update(helpers)
    new["SGLANG_API_KEY"] = API_REFERENCE
    if mode == "tailnet":
        new["TS_AUTHKEY"] = TS_REFERENCE
    else:
        new.pop("TS_AUTHKEY", None)
    if hf_secret:
        new["HF_TOKEN"] = "{{ RUNPOD_SECRET_" + hf_secret + " }}"
    else:
        new.pop("HF_TOKEN", None)
    return new


def sync(template_id, mode, hf_secret, helpers=None):
    before = ports.request("GET", template_id)
    if before.get("id") != template_id:
        raise ports.PortSafetyError("template ID mismatch")
    old_env = before.get("env")
    new_env = make_env(old_env, mode, hf_secret, helpers)
    old_ports = before.get("ports", [])
    if not isinstance(old_ports, list):
        raise ports.PortSafetyError("unexpected ports format")
    ports.request("PATCH", template_id, {"env": new_env})
    after = ports.request("GET", template_id)
    if after.get("id") != template_id or after.get("env") != new_env:
        raise ports.PortSafetyError("template env did not persist as expected")
    if mode == "tailnet":
        ports.repair(template_id)
    elif after.get("ports", []) != old_ports:
        raise ports.PortSafetyError("public template port configuration changed unexpectedly")
    print("PASS: " + mode + " template " + template_id +
          " now references RunPod Secrets" +
          (" and has zero published ports" if mode == "tailnet" else ""))


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-full", required=True)
    parser.add_argument("--public-lean", required=True)
    parser.add_argument("--private-full", required=True)
    parser.add_argument("--private-lean", required=True)
    parser.add_argument("--refresh-helpers", action="store_true",
                        help="refresh four embedded helper scripts from this git checkout")
    args = parser.parse_args()
    hf_secret = os.environ.get("QWEN38_HF_SECRET_NAME", "HF_TOKEN")
    if hf_secret and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", hf_secret):
        print("FAIL: invalid QWEN38_HF_SECRET_NAME", file=sys.stderr)
        return 64
    helpers = read_bundled_helpers() if args.refresh_helpers else None
    for template_id, mode in (
        (args.public_full, "runpod"),
        (args.public_lean, "runpod"),
        (args.private_full, "tailnet"),
        (args.private_lean, "tailnet"),
    ):
        try:
            sync(template_id, mode, hf_secret, helpers)
        except ports.PortSafetyError as exc:
            print("FAIL: " + mode + " template " + template_id + ": " + str(exc),
                  file=sys.stderr)
            print("Stopped. No GPU pod was started.", file=sys.stderr)
            return 1
    print("SUCCESS: Four existing templates updated. No GPU pod started.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
