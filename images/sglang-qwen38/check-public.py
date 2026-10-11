#!/usr/bin/env python3
"""Verify that the exact GPU-tested custom image is anonymously pullable.

Only communicates with ghcr.io using its standard anonymous registry bearer
flow. No Docker installation, GitHub account, token, or image layer download
is needed. This does not change package visibility.

Usage:
  python3 images/sglang-qwen38/check-public.py
"""
import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

REGISTRY = "https://ghcr.io"
REPOSITORY = "tommyfive/qwen38-sglang"
PINNED = "sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd"
MANIFEST_TYPE = "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"


class BlockRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("Unexpected registry redirect: refusing to forward bearer token")


def get_json(uri, headers=None):
    req = urllib.request.Request(uri, headers=headers or {})
    with urllib.request.build_opener(BlockRedirect()).open(req, timeout=15) as response:
        return response.read(1024 * 1024), response.headers


def verify_anonymous():
    params = urllib.parse.urlencode({
        "service": "ghcr.io", "scope": "repository:" + REPOSITORY + ":pull"
    })
    token_body, _ = get_json(REGISTRY + "/token?" + params)
    token = json.loads(token_body).get("token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Anonymous GHCR pull token unavailable")
    data, headers = get_json(
        REGISTRY + "/v2/" + REPOSITORY + "/manifests/" + PINNED,
        {"Authorization": "Bearer " + token, "Accept": MANIFEST_TYPE}
    )
    actual = "sha256:" + hashlib.sha256(data).hexdigest()
    if actual != PINN:
        raise RuntimeError("Public registry returned different manifest than the tested digest")
    declared = headers.get("Docker-Content-Digest")
    if declared and declared != PINN:
        raise RuntimeError("Public registry declared unexpected manifest digest")
    manifest = json.loads(data)
    layers = manifest.get("layers") or []
    if not isinstance(layers, list) or len(layers) != 31:
        raise RuntimeError("Public registry did not return expected 31-layer image")
    return len(layers)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        count = verify_anonymous()
    except (RuntimeError, KeyError, OSError, ValueError, json.JSONDecodeError,
            urllib.error.URLError, urllib.error.HTTPError) as exc:
        print("Custom GHCR image is not yet publicly verified (" +
              type(exc).__name__ + ")", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"PUBLIC_IMAGE_VERIFIED: {REPOSITORY}@{PINN} ({count} layers); no login required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
