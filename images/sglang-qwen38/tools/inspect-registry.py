#!/usr/bin/env python3
"""Read-only GHCR tag, manifest, config and blob-reference verification.

No Docker, downloaded image layers, persistent token file or package writes.
Anonymous reads by default; --private uses hidden-input read-only credentials.
HTTPS requests go only to ghcr.io and the exact pinned image repository.

Usage:
  python3 images/sglang-qwen38/tools/inspect-registry.py
"""
import argparse
import datetime
import re
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


class BlobRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        host = urllib.parse.urlsplit(newurl)
        if host.scheme != "https" or not (host.hostname == "pkg-containers.githubusercontent.com"
                or (host.hostname or "").endswith(".blob.core.windows.net")):
            raise RuntimeError("Untrusted blob redirect")
        # Preserve HEAD: never accidentally download a multi-GB layer or forward auth.
        return urllib.request.Request(newurl, method=request.get_method())


def verify(reference="v0.2.2", repository=REPO, private=False):
    if not re.fullmatch(r"[a-z0-9][a-z0-9._/-]*", repository):
        raise ValueError("Invalid repository")
    if not re.fullmatch(r"(?:sha256:[0-9a-f]{64}|[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})", reference):
        raise ValueError("Invalid reference")
    query = urllib.parse.urlencode({"service": "ghcr.io", "scope": f"repository:{repository}:pull"})
    headers = {}
    if private:
        pat = getpass.getpass("GHCR read-only token: ")
        headers["Authorization"] = "Basic " + base64.b64encode(f"{OWNER}:{pat}".encode()).decode()
    request = urllib.request.Request("https://ghcr.io/token?" + query, headers=headers)
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        bearer = json.load(response)["token"]
    headers = {"Authorization": "Bearer " + bearer, "Accept": ", ".join([
        "application/vnd.oci.image.manifest.v1+json", "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json", "application/vnd.docker.distribution.manifest.list.v2+json"])}
    base = "https://ghcr.io/v2/" + repository

    def manifest(ref):
        req = urllib.request.Request(base + "/manifests/" + ref, headers=headers)
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as response:
            raw = response.read(8*1024*1024)
            digest = "sha256:" + hashlib.sha256(raw).hexdigest()
            if response.headers.get("Docker-Content-Digest", digest) != digest:
                raise ValueError("Registry digest mismatch")
        if ref.startswith("sha256:") and ref != digest:
            raise ValueError("Pinned manifest mismatch")
        return json.loads(raw), digest

    doc, tag_digest = manifest(reference)
    result = measure(doc)
    digest = tag_digest
    if isinstance(result, str):
        descriptor = next(x for x in doc["manifests"] if x["digest"] == result)
        doc, digest = manifest(result)
        result = measure(doc)
    if isinstance(result, str):
        raise ValueError("Nested index unsupported")
    total, layers = result
    for part in [doc["config"], *layers]:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", part["digest"]):
            raise ValueError("Malformed blob digest")
        req = urllib.request.Request(base + "/blobs/" + part["digest"], headers=headers, method="HEAD")
        with urllib.request.build_opener(BlobRedirect()).open(req, timeout=30) as response:
            if response.status != 200 or int(response.headers["Content-Length"]) != part["size"]:
                raise ValueError("Blob missing or wrong size")
    req = urllib.request.Request(base + "/blobs/" + doc["config"]["digest"], headers=headers)
    with urllib.request.build_opener(BlobRedirect()).open(req, timeout=30) as response:
        raw = response.read(4*1024*1024)
    if len(raw) != doc["config"]["size"] or "sha256:" + hashlib.sha256(raw).hexdigest() != doc["config"]["digest"]:
        raise ValueError("Config checksum/size mismatch")
    config = json.loads(raw)
    if config.get("os") != "linux" or config.get("architecture") != "amd64":
        raise ValueError("Not linux/amd64")
    if len(config.get("rootfs", {}).get("diff_ids", [])) != len(layers):
        raise ValueError("Config/layer count mismatch")
    return {"checked_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
            "repository": repository, "reference": reference, "tag_digest": tag_digest,
            "manifest_digest": digest, "config": doc["config"], "layers": layers,
            "compressed_layer_bytes": total, "platform": "linux/amd64",
            "blob_head_checks": len(layers)+1, "config_sha256_verified": True,
            "note": "Layer HEAD checks verify availability/size, not downloaded content hashes; no image build or layer download."}, config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default="v0.2.2")
    parser.add_argument("--repository", default=REPO)
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--config-output", help="Private local config evidence; may include historical labels")
    args = parser.parse_args()
    result, config = verify(args.reference, args.repository, args.private)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(rendered)
    if args.config_output:
        from pathlib import Path
        Path(args.config_output).write_text(json.dumps(config, indent=2) + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
