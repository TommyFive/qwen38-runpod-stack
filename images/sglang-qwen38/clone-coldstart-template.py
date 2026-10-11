#!/usr/bin/env python3
"""Clone the user's EXISTING Lean-SGLang RunPod template with only image changed.

Dry run by default. Exact source ID and intended image are pinned. This reads
existing template metadata locally through runpodctl, preserves the same
bootstrap/env/secret references, and never creates or changes a GPU Pod.
The explicit --execute switch creates only ONE additional RunPod template.
"""
import argparse
import json
import shutil
import subprocess
import sys

SOURCE_ID = "g6ey6ire16"
NAME = "qwen38-sglang-coldstart-candidate-20261011"
IMAGE = ("ghcr.io/tommyfive/qwen38-sglang@"
         "sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd")
REGISTRY_NAME = "ghcr.io"


def cli():
    return shutil.which("runpodctl") or "/opt/homebrew/bin/runpodctl"


def json_cmd(*args):
    res = subprocess.run([cli(), *args], capture_output=True, text=True,
                         check=True, timeout=35)
    return json.loads(res.stdout)


def prepare():
    templates = json_cmd("template", "list", "--type", "user", "-o", "json")
    matches = [x for x in templates if x.get("id") == SOURCE_ID]
    if len(matches) != 1:
        raise ValueError("Exactly one known source template must be available")
    source = matches[0]
    for key, val in {
        "COLDSTART_TRACE": "1", "MODEL_STORAGE": "ram", "NETWORK_MODE": "runpod",
        "SPEC": "dflash2", "SERVE_WEBUI": "0",
        "MODEL_ID": "sakamakismile/Huihui-Qwen3.8-27B-abliterated-NVFP4",
    }.items():
        if source.get("env", {}).get(key) != val:
            raise ValueError(f"Source env {key} differs from expected value")
    if not source.get("env", {}).get("BOOTSTRAP_B64"):
        raise ValueError("Missing production-tested source bootstrap")
    if source.get("env", {}).get("SGLANG_API_KEY") != "{{ RUNPOD_SECRET_LLAMA_API_KEY }}":
        raise ValueError("API key must be an existing RunPod secret reference")
    if source.get("env", {}).get("HF_TOKEN") != "{{ RUNPOD_SECRET_HF_TOKEN }}":
        raise ValueError("HF credential must be an existing RunPod secret reference")
    for field in ("STORAGE_HELPER_B64", "TAILSCALE_RUNTIME_B64", "BENCHMARK_B64"):
        if not source["env"].get(field):
            raise ValueError(f"Missing telemetry helper field {field}")
    if source.get("containerDiskInGb") != 150:
        raise ValueError("Unexpected disk size in tested template")
    if source.get("ports") != ["8000/http", "22/tcp"]:
        raise ValueError("Unexpected exposed ports in tested template")
    registry = json_cmd("registry", "list")
    auth = [x.get("id") for x in registry if x.get("name") == REGISTRY_NAME]
    if len(auth) != 1 or not isinstance(auth[0], str):
        raise ValueError("Exactly one GHCR registry credential required")
    existing = [x for x in templates if x.get("name") == NAME]
    if existing:
        raise ValueError(f"Candidate template named {NAME} already exists; do not duplicate")
    start = source.get("dockerStartCmd")
    if not isinstance(start, list) or start[:2] != ["bash", "-c"] or len(start) != 3:
        raise ValueError("Unexpected source entrypoint")
    return source, auth[0]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true",
                   help="Opt-in only: create a new TEMPLATE, never start a GPU Pod")
    args = p.parse_args()
    source, registry_auth_id = prepare()
    print("Source id:", SOURCE_ID, "name:", source.get("name"))
    print("Candidate:", NAME, "image digest:", IMAGE.split("@")[-1])
    print("Same bootstrap, RAM-first, DFlash2, secrets, trace and ports:", True)
    print("No secret values printed, no existing templates modified.")
    if not args.execute:
        print("DRY RUN: use --execute to create only an isolated template (no GPU).")
        return
    command = [
        cli(), "template", "create", "--name", NAME, "--image", IMAGE,
        "--registry-auth-id", registry_auth_id,
        "--container-disk-in-gb", "150",
        "--volume-mount-path", source.get("volumeMountPath") or "/workspace",
        "--ports", ",".join(source["ports"]),
        "--port-labels", "8000=SGLang API,22=SSH",
        "--docker-start-cmd", ",".join(source["dockerStartCmd"]),
        "--env", json.dumps(source["env"], separators=(",", ":")),
        "-o", "json",
    ]
    response = subprocess.run(command, capture_output=True, text=True, timeout=45)
    if response.returncode != 0:
        # stderr can contain env values. Emit only an error line when it has
        # no payload/secret markers, and redact any long high-entropy spans.
        import re
        raw = (response.stderr or response.stdout).strip()
        first = raw.splitlines()[0][:300] if raw else "No diagnostic provided"
        if any(k in first.lower() for k in ("bootstrap_b64", "hf_token", "authkey", "api_key", "--env", "secret_", "storage_helper")):
            first = "Redacted because CLI diagnostics referenced template environment"
        first = re.sub(r"[a-zA-Z0-9/+_=-]{32,}", "[REDACTED]", first)
        print("RUNPOD_CLI_ERROR:", first, file=sys.stderr)
        raise RuntimeError(f"RunPod template create failed with code {response.returncode}")
    result = json.loads(response.stdout)
    template_id = result.get("id")
    if not isinstance(template_id, str) or not template_id:
        raise RuntimeError("RunPod template response has no template ID")
    print("CREATED_CANDIDATE_TEMPLATE_ID=" + template_id)
    print("No paid GPU Pod started.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired,
            subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        # Exceptions can contain CLI arguments/env secrets; print only class.
        print(f"Candidate template preparation failed ({type(exc).__name__})",
              file=sys.stderr)
        raise SystemExit(1)
