#!/usr/bin/env python3
"""Stream a single oversized OCI filesystem layer into small, ordered OCI layers.

Designed for GitHub Container Registry's 10-GB-per-layer and 10-minute limits.
This is a CPU-only *repack*, not a source build. Original tar remains untouched.
Preserves all original tar entries (path order, type, mode, owner, PAX attributes,
symlink/hardlink targets and byte content). Rewrites OCI config diff_ids/history
as required by the new layer boundaries; other config/labels preserved.

Requires Python 3.12 and pigz (parallel gzip). No network, no Docker daemon.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

CHUNK_BYTES = 3_750_000_000
MAX_LAYER_BYTES = 4_700_000_000


def canonical_json(item):
    return json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def save_blob(dst, data):
    digest = sha_bytes(data)
    filename = dst / "blobs" / "sha256" / digest
    if not filename.exists():
        filename.write_bytes(data)
    return {"mediaType": "application/vnd.oci.image.config.v1+json",
            "digest": "sha256:" + digest, "size": len(data)}


def load_json_archive(archive, name):
    item = archive.extractfile(name)
    if item is None:
        raise RuntimeError("OCI missing " + name)
    return json.loads(item.read())


class CountingHashWriter:
    def __init__(self, child):
        self.child = child
        self.hash = hashlib.sha256()
        self.length = 0

    def write(self, data):
        self.hash.update(data)
        self.length += len(data)
        return self.child.write(data)

    def flush(self):
        self.child.flush()


def build_chunk(destination, n):
    path = destination / ("chunk-%03d.tmp" % n)
    outfile = path.open("wb")
    process = subprocess.Popen(
        ["pigz", "-6", "-p", "3", "-n", "-c"],
        stdin=subprocess.PIPE, stdout=outfile, stderr=subprocess.PIPE,
    )
    uncompressed = CountingHashWriter(process.stdin)
    tar = tarfile.open(fileobj=uncompressed, mode="w|", format=tarfile.PAX_FORMAT)
    return path, outfile, process, uncompressed, tar


def finish_chunk(destination, chunk, n):
    path, outfile, proc, raw, writer = chunk
    writer.close()
    raw.child.close()
    msg = proc.stderr.read()
    code = proc.wait()
    outfile.close()
    if code != 0:
        raise RuntimeError("pigz failed: " + msg.decode(errors="replace"))
    size = path.stat().st_size
    if not 0 < size < MAX_LAYER_BYTES:
        raise ValueError(f"Layer {n} violates maximum compressed size: {size}")
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for blob in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            digest.update(blob)
    target = destination / "blobs" / "sha256" / digest.hexdigest()
    path.rename(target)
    print(f"FINISHED layer {n}: raw={raw.length} compressed={size} digest=sha256:{digest.hexdigest()}", flush=True)
    return {
        "descriptor": {
            "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
            "digest": "sha256:" + digest.hexdigest(),
            "size": size,
        },
        "diff_id": "sha256:" + raw.hash.hexdigest(),
    }


def rewrite_history(config, old_diff_ids, new_diff_ids):
    original = config.get("history") or []
    if not original:
        config["history"] = [{"created_by": "Qwen38 deadline lossless layer split"}
                             for _ in new_diff_ids]
        return
    rewritten = []
    found = 0
    for event in original:
        if event.get("empty_layer"):
            rewritten.append(event)
            continue
        if found == 0:
            for n in range(len(new_diff_ids) - len(old_diff_ids) + 1):
                item = dict(event)
                item["created_by"] = ("Qwen38 repack: split original rootfs layer "
                                      + str(n + 1))
                rewritten.append(item)
        else:
            rewritten.append(event)
        found += 1
    if found != len(old_diff_ids):
        raise ValueError("OCI config history/rootfs mismatch")
    config["history"] = rewritten


def split(source, dest, ref):
    if dest.exists():
        raise FileExistsError(f"Refusing to replace destination {dest}")
    (dest / "blobs" / "sha256").mkdir(parents=True)
    with tarfile.open(source, "r:") as outer:
        index = load_json_archive(outer, "index.json")
        descs = index["manifests"]
        if len(descs) != 1:
            raise ValueError("Expected a single OCI manifest")
        desc = descs[0]
        manifest = load_json_archive(outer, "blobs/sha256/" + desc["digest"][7:])
        layers = manifest["layers"]
        if len(layers) != 2 or layers[0]["size"] < 10_000_000_000:
            raise ValueError("Unexpected two-layer oversized candidate")
        config = load_json_archive(outer, "blobs/sha256/" + manifest["config"]["digest"][7:])
        old_diff_ids = config["rootfs"]["diff_ids"]
        if len(old_diff_ids) != len(layers):
            raise ValueError("diff_ids count mismatch")
        result = []
        count, current_bytes, n = 0, 0, 0
        firstlayer = "blobs/sha256/" + layers[0]["digest"][7:]
        compressed = outer.extractfile(firstlayer)
        if compressed is None:
            raise RuntimeError("Missing source filesystem layer")
        with gzip.GzipFile(fileobj=compressed) as uncompressed:
            with tarfile.open(fileobj=uncompressed, mode="r|") as reader:
                chunk = None
                for member in reader:
                    if member.name.startswith("/") or ".." in Path(member.name).parts:
                        raise ValueError("Invalid absolute/parent tar entry")
                    raw_size = member.size if member.isfile() else 0
                    if chunk and current_bytes >= CHUNK_BYTES:
                        result.append(finish_chunk(dest, chunk, n))
                        chunk = None
                        current_bytes = 0
                    if chunk is None:
                        n += 1
                        chunk = build_chunk(dest, n)
                    payload = reader.extractfile(member) if member.isfile() else None
                    chunk[-1].addfile(member, payload)
                    current_bytes += raw_size
                    count += 1
                    if count % 25000 == 0:
                        print("PROGRESS entries", count, "last", member.name[:150], flush=True)
                if chunk:
                    result.append(finish_chunk(dest, chunk, n))
        # Copy the original (small) second compressed filesystem layer unchanged.
        last = layers[1]
        name = "blobs/sha256/" + last["digest"][7:]
        data = outer.extractfile(name).read()
        if sha_bytes(data) != last["digest"][7:]:
            raise ValueError("Final original OCI blob hash mismatch")
        (dest / name).write_bytes(data)
        new_diff_ids = [x["diff_id"] for x in result] + old_diff_ids[1:]
        rewrite_history(config, old_diff_ids, new_diff_ids)
        config["rootfs"]["diff_ids"] = new_diff_ids
        config_desc = save_blob(dest, canonical_json(config))
        new_manifest = dict(manifest)
        new_manifest["config"] = config_desc
        new_manifest["layers"] = [x["descriptor"] for x in result] + [last]
        manifest_bytes = canonical_json(new_manifest)
        manifest_digest = sha_bytes(manifest_bytes)
        (dest / "blobs" / "sha256" / manifest_digest).write_bytes(manifest_bytes)
        new_desc = dict(desc)
        new_desc.update({"digest": "sha256:" + manifest_digest, "size": len(manifest_bytes)})
        new_desc["annotations"] = dict(desc.get("annotations", {}))
        new_desc["annotations"]["org.opencontainers.image.ref.name"] = ref
        (dest / "index.json").write_bytes(canonical_json({"schemaVersion": 2, "manifests": [new_desc]}))
        (dest / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}\n')
        report = {
            "source": str(source),
            "original_manifest": desc["digest"],
            "original_config": manifest["config"]["digest"],
            "original_compressed_bytes": sum(l["size"] for l in layers),
            "repacked_manifest": "sha256:" + manifest_digest,
            "repacked_config": config_desc["digest"],
            "repacked_compressed_bytes": sum(l["size"] for l in new_manifest["layers"]),
            "layers": new_manifest["layers"],
            "number_of_tar_entries": count,
            "source_diff_ids": old_diff_ids,
            "repacked_diff_ids": new_diff_ids,
            "note": "Full OCI config except required rootfs.diff_ids and history preserved; full tar entry order preserved.",
        }
        (dest / "split-report.json").write_text(json.dumps(report, indent=2))
        print("DONE", json.dumps({"manifest": report["repacked_manifest"],
                                 "entries": count, "layers": len(result) + 1,
                                 "compressed_bytes": report["repacked_compressed_bytes"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--ref", default="checkpoint")
    args = parser.parse_args()
    split(args.source, args.destination, args.ref)
