#!/usr/bin/env python3
"""Security preflight: inspect published image CONFIG + history, no layer download.

The user-approved public image release should not expose credentials embedded
at BUILD TIME. Docker/OCI config and history can be audited with just a few KB.
This is *not* a substitute for examining the contents of all 31 filesystem
layers or a malware/SBOM scanner. Runtime RunPod Secret references are separate.

In GitHub Actions use an ephemeral GITHUB_TOKEN with packages:read and
GITHUB_ACTOR. No secret values are ever printed.
"""
import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

REGISTRY = "https://ghcr.io"
REPO = "tommyfive/qwen38-sglang"
MANIFEST = "sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd"
MEDIA_TYPES = ", ".join((
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
))
SENSITIVE_KEYS = re.compile(
    r"(?i)(?:TOKEN|PASSWORD|PASSWD|SECRET|API_KEY|PRIVATE_KEY|AUTHKEY|"
    r"CREDENTIAL|AWS_ACCESS|AZURE_CLIENT_SECRET|GOOGLE_APPLICATION_CREDENTIALS)"
)
SENSITIVE_PATHS = re.compile(
    r"(?i)(?:\.ssh/(?:id_|config)|huggingface/token|\.aws/credentials|"
    r"docker/config\.json|(?<![\w])ghp_[A-Za-z0-9]{20}|"
    r"github_pat_[A-Za-z0-9_]{20}|tskey-[A-Za-z0-9-]{12}|"
    r"-----BEGIN .*PRIVATE KEY-----)"
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ValueError("GHCR unexpected redirect")


def fetch(path, headers=None):
    req = urllib.request.Request(REGISTRY + path, headers=headers or {})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as res:
        return res.read(4 * 1024 * 1024)


def authenticated_bearer():
    github_token = os.getenv("GITHUB_TOKEN", "")
    username = os.getenv("GITHUB_ACTOR", "")
    if not github_token or not username:
        raise RuntimeError("Missing ephemeral GitHub Actions package token")
    encoded = base64.b64encode(f"{username}:{github_token}".encode()).decode()
    args = urllib.parse.urlencode({
        "service": "ghcr.io", "scope": f"repository:{REPO}:pull"
    })
    response = json.loads(fetch("/token?" + args, {
        "Authorization": "Basic " + encoded, "Accept": "application/json"
    }))
    bearer = response.get("token") or response.get("access_token")
    if not isinstance(bearer, str) or not bearer:
        raise RuntimeError("GHCR issued no read-only registry bearer token")
    return bearer


def inspect_config(config):
    env = config.get("config", {}).get("Env") or []
    history = config.get("history") or []
    if not isinstance(env, list) or not isinstance(history, list):
        raise ValueError("Unexpected Docker config structure")
    keys = [entry.partition("=")[0] for entry in env if isinstance(entry, str)]
    exposed_keys = sorted(k for k in keys if SENSITIVE_KEYS.search(k))
    flagged_history = [
        index for index, item in enumerate(history, 1)
        if SENSITIVE_PATHS.search(str(item.get("created_by", "")))
    ]
    if exposed_keys or flagged_history:
        # NEVER print the secret value, command contents or image history.
        raise ValueError(
            f"Potential embedded secrets in ENV keys {exposed_keys} "
            f"or sensitive Dockerfile paths on {len(flagged_history)} history steps"
        )
    return len(keys), len(history)


def main():
    try:
        bearer = authenticated_bearer()
        headers = {"Authorization": "Bearer " + bearer,
                   "Accept": MEDIA_TYPES}
        raw = fetch(f"/v2/{REPO}/manifests/{MANIFEST}", headers)
        if "sha256:" + hashlib.sha256(raw).hexdigest() != MANIFEST:
            raise ValueError("Retrieved manifest does not match original tested digest")
        manifest = json.loads(raw)
        if len(manifest.get("layers") or []) != 31:
            raise ValueError("Unexpected layer count")
        config_digest = manifest.get("config", {}).get("digest", "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", config_digest):
            raise ValueError("Invalid OCI config digest")
        raw_config = fetch(f"/v2/{REPO}/blobs/{config_digest}", headers)
        if "sha256:" + hashlib.sha256(raw_config).hexdigest() != config_digest:
            raise ValueError("OCI config blob SHA256 mismatch")
        env_count, history_count = inspect_config(json.loads(raw_config))
        print(f"IMAGE_METADATA_AUDIT_PASS env_keys={env_count} "
              f"history_steps={history_count} layers=31 verified_digests=2")
        print("LIMIT: files inside image filesystem layers were NOT inspected.")
        return 0
    except (ValueError, RuntimeError, OSError, urllib.error.URLError, KeyError,
            json.JSONDecodeError) as exc:
        reason = "other"
        if isinstance(exc, ValueError):
            message = str(exc)
            if message.startswith("Potential embedded secrets"):
                # Key names and counts only; never print ENV values or commands.
                reason = message
            elif "manifest" in message.lower():
                reason = "manifest verification mismatch"
            elif "config" in message.lower():
                reason = "OCI config retrieval or validation mismatch"
            elif "redirect" in message.lower():
                reason = "unhandled registry redirect"
        print("IMAGE_METADATA_AUDIT_FAILED (" + type(exc).__name__ +
              ", reason=" + reason + "); do not treat image as fully audited",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
