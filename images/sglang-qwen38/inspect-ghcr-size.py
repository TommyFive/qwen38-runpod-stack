#!/usr/bin/env python3
"""Read-only compressed-size verification of the PRIVATE GHCR candidate.

No Docker, downloaded image layers, persistent token file or package writes.
Credentials are requested with getpass on an interactive terminal only.
HTTPS requests go only to ghcr.io and the exact pinned image repository.

Usage:
  python3 images/sglang-qwen38/inspect-ghcr-size.py
"""
import base64
import getpass
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

OWNER = "TommyFive"
REPO = "tommyfive/qwen38-sglang"
REFERENCE = "sha256:1dc683600229c0c34d8df7eb322c6cbf36f677c22d216625df1e3892ae32a7fd"
BASELINE_COMPRESSED_GB = 14.676
USER_AGENT = "qwen38-manifest-verifier/1.0"

# Avoid allowing a redirect to another hostname to receive bearer credentials.
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *unused):
        raise RuntimeError("GHCR unexpected redirect; refusing to forward credentials")


def get_registry_bearer(pat):
    qs = urllib.parse.urlencode({
        "service": "ghcr.io",
        "scope": f"repository:{REPO}:pull",
    })
    url = "https://ghcr.io/token?" + qs
    basic = base64.b64encode(f"{OWNER}:{pat}".encode()).decode()
    req = urllib.request.Request(url, headers={
        "Authorization": "Basic " + basic,
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as response:
        data = json.load(response)
    token = data.get("token") or data.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("GHCR bearer token missing: verify PAT has read:packages and package access")
    return token


def retrieve_manifest(digest, bearer):
    if not isinstance(digest, str) or not digest.startswith("sha256:") or len(digest) != 71:
        raise RuntimeError("Unexpected digest")
    if any(c not in "0123456789abcdef" for c in digest[7:]):
        raise RuntimeError("Malformed SHA256 digest")
    url = f"https://ghcr.io/v2/{REPO}/manifests/{digest}"
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + bearer,
        "Accept": ", ".join([
            "application/vnd.oci.image.manifest.v1+json",
            "application/vnd.docker.distribution.manifest.v2+json",
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
        ]),
        "User-Agent": USER_AGENT,
    })
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as response:
        raw = response.read(8 * 1024 * 1024)
        registered = response.headers.get("Docker-Content-Digest", "")
    computed = "sha256:" + hashlib.sha256(raw).hexdigest()
    if computed != digest:
        raise RuntimeError("GHCR manifest bytes do not match requested immutable digest")
    if registered and registered != digest:
        raise RuntimeError("GHCR reported unexpected content digest")
    return json.loads(raw)


def measure(doc):
    if "manifests" in doc:
        entries = [m for m in doc["manifests"] if m.get("platform", {}).get("os") == "linux"
                   and m.get("platform", {}).get("architecture") == "amd64"]
        if len(entries) != 1:
            raise RuntimeError("Unable to identify exactly one linux/amd64 manifest")
        return entries[0]["digest"]
    layers = doc.get("layers")
    if not isinstance(layers, list) or not layers:
        raise RuntimeError("Manifest has no compressed layer descriptors")
    for item in layers:
        if not isinstance(item.get("size"), int) or item["size"] < 0:
            raise RuntimeError("Invalid compressed layer descriptor")
    return sum(layer["size"] for layer in layers), layers


def main():
    print("Read-only GHCR manifest lookup; NO image layers will be downloaded.")
    print("Account: TommyFive; package: ghcr.io/tommyfive/qwen38-sglang")
    try:
        pat = getpass.getpass("GitHub PAT (read:packages; hidden input): ")
        if not pat:
            raise RuntimeError("No token entered")
        bearer = get_registry_bearer(pat)
        del pat
        document = retrieve_manifest(REFERENCE, bearer)
        result = measure(document)
        if isinstance(result, str):
            manifest_sha = result
            print("GHCR returned multi-platform image index; selecting linux/amd64")
            document = retrieve_manifest(manifest_sha, bearer)
            result = measure(document)
        del bearer
        if isinstance(result, str):
            raise RuntimeError("Unexpected nested image index")
        total, layers = result
        print(f"GHCR manifest verified: {REFERENCE}")
        print(f"Compressed layers: {len(layers)}")
        print(f"Compressed total: {total:,} bytes = {total / 1e9:.3f} GB decimal")
        print(f"Previous baseline: {BASELINE_COMPRESSED_GB:.3f} GB decimal")
        print(f"Delta versus baseline: {(total / 1e9 / BASELINE_COMPRESSED_GB - 1):+.1%}")
        print("Top 5 compressed layer sizes (GB):",
              [round(int(x['size']) / 1e9, 3) for x in
               sorted(layers, key=lambda x: -x["size"])[:5]])
        return 0
    except (EOFError, KeyboardInterrupt):
        print("Cancelled; no secret saved.", file=sys.stderr)
    except urllib.error.HTTPError as exc:
        print(f"GHCR HTTP {exc.code}; verify package access and read:packages scope.", file=sys.stderr)
    except (RuntimeError, KeyError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
