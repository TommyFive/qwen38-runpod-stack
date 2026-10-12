#!/usr/bin/env python3
"""Verify lossless OCI repack metadata and compressed blob integrity.

This is CPU-only verification. It cannot replace GPU runtime tests.
"""
import argparse
import gzip
import itertools
import hashlib
import json
import tarfile
from pathlib import Path


def read_tar_json(tar, path):
    f=tar.extractfile(path)
    if f is None:
        raise ValueError("Missing archive member " + path)
    return json.loads(f.read())


def read_dir_json(root, relative):
    return json.loads((root / relative).read_bytes())


def layer_entries(opener, layers):
    """Streaming ordered content/metadata comparison, without extracting any paths."""
    for descriptor in layers:
        with opener(descriptor["digest"]) as raw:
            with tarfile.open(fileobj=raw, mode="r|gz") as archive:
                for member in archive:
                    checksum = None
                    if member.isfile():
                        content = archive.extractfile(member)
                        sha = hashlib.sha256()
                        for chunk in iter(lambda: content.read(4*1024*1024), b""):
                            sha.update(chunk)
                        checksum = sha.hexdigest()
                    yield (member.name, member.type, member.size, member.mode,
                           member.uid, member.gid, member.uname, member.gname,
                           member.mtime, member.linkname, member.devmajor,
                           member.devminor, member.pax_headers, checksum)


def verify_layer_stream(raw, descriptor, diff_id):
    sha = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: raw.read(4*1024*1024), b""):
        sha.update(chunk)
        size += len(chunk)
    if size != descriptor["size"] or "sha256:"+sha.hexdigest() != descriptor["digest"]:
        raise ValueError("Compressed layer checksum/size mismatch")
    raw.seek(0)
    sha = hashlib.sha256()
    with gzip.GzipFile(fileobj=raw) as decoded:
        for chunk in iter(lambda: decoded.read(4*1024*1024), b""):
            sha.update(chunk)
    if "sha256:"+sha.hexdigest() != diff_id:
        raise ValueError("Uncompressed layer diff_id mismatch")


def validate(original, repacked):
    with tarfile.open(original, "r:") as t:
        index=read_tar_json(t,"index.json")
        desc=index["manifests"][0]
        manifest=read_tar_json(t,"blobs/sha256/"+desc["digest"][7:])
        original_config=read_tar_json(t,"blobs/sha256/"+manifest["config"]["digest"][7:])
    ix=read_dir_json(repacked, "index.json")
    newdesc=ix["manifests"][0]
    newmanifest=read_dir_json(repacked, "blobs/sha256/"+newdesc["digest"][7:])
    new_config=read_dir_json(repacked, "blobs/sha256/"+newmanifest["config"]["digest"][7:])
    a=dict(original_config)
    b=dict(new_config)
    for k in ("rootfs","history"):
        a.pop(k,None); b.pop(k,None)
    if a!=b:
        raise ValueError("OCI config attributes changed beyond rootfs/history")
    if len(new_config["rootfs"]["diff_ids"]) != len(newmanifest["layers"]):
        raise ValueError("Incorrect OCI rootfs count")
    if len(newmanifest["layers"]) <= len(manifest["layers"]):
        raise ValueError("OCI layers were not split")
    if newmanifest["layers"][-1] != manifest["layers"][-1]:
        raise ValueError("Original final layer was modified")
    total=0
    for descriptor in [newmanifest["config"],*newmanifest["layers"]]:
        h=descriptor["digest"][7:]
        file=repacked/"blobs"/"sha256"/h
        if file.stat().st_size!=descriptor["size"]:
            raise ValueError("Incorrect OCI blob length "+h)
        sha=hashlib.sha256()
        with file.open("rb") as stream:
            for chunk in iter(lambda:stream.read(4*1024*1024), b""):
                sha.update(chunk)
        if sha.hexdigest()!=h:
            raise ValueError("Incorrect OCI SHA "+h)
        if descriptor in newmanifest["layers"]:
            total+=descriptor["size"]
    # Verify index->manifest integrity in both representations, then layer
    # compressed hashes, uncompressed diff IDs and ordered TAR content/metadata.
    with tarfile.open(original, "r:") as source:
        old_open = lambda digest: source.extractfile("blobs/sha256/"+digest[7:])
        new_open = lambda digest: (repacked/"blobs"/"sha256"/digest[7:]).open("rb")
        for opener, descriptor in ((old_open, desc), (new_open, newdesc),
                                   (old_open, manifest["config"] )):
            with opener(descriptor["digest"]) as stream:
                raw = stream.read()
            if len(raw) != descriptor["size"] or "sha256:"+hashlib.sha256(raw).hexdigest() != descriptor["digest"]:
                raise ValueError("Manifest/config checksum mismatch")
        for opener, layers, config in ((old_open, manifest["layers"], original_config),
                                      (new_open, newmanifest["layers"], new_config)):
            if len(layers) != len(config["rootfs"]["diff_ids"]):
                raise ValueError("Layer/diff_id count mismatch")
            for layer, diff_id in zip(layers, config["rootfs"]["diff_ids"]):
                with opener(layer["digest"]) as stream:
                    verify_layer_stream(stream, layer, diff_id)
        for before, after in itertools.zip_longest(layer_entries(old_open, manifest["layers"]),
                                                  layer_entries(new_open, newmanifest["layers"])):
            if before != after:
                raise ValueError("Ordered TAR content/metadata mismatch")
    report=json.loads((repacked/"split-report.json").read_text())
    if total != report["repacked_compressed_bytes"]:
        raise ValueError("Incorrect split report compressed bytes")
    print(json.dumps({"status":"verified","original_config":manifest["config"]["digest"],
                     "new_config":newmanifest["config"]["digest"],
                     "original_manifest":desc["digest"],"new_manifest":newdesc["digest"],
                     "layers":len(newmanifest["layers"]),
                     "compressed_bytes":total,
                     "exact_non_rootfs_config_preserved":True},indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("original",type=Path)
    p.add_argument("repacked",type=Path)
    x=p.parse_args()
    validate(x.original,x.repacked)
