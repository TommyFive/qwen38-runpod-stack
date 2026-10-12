"""Small real OCI fixtures: order, metadata, layer hashes and diff IDs matter."""
import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'tools/audit'
spec = importlib.util.spec_from_file_location('verify_split', ROOT / 'verify-split-oci.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def sha(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def tar_layer(names):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w') as archive:
        for name, value in names:
            info = tarfile.TarInfo(name)
            info.mode = 0o640
            info.size = len(value)
            archive.addfile(info, io.BytesIO(value))
    raw = out.getvalue()
    return gzip.compress(raw, mtime=0), sha(raw)


def layout(root, groups):
    (root / 'blobs/sha256').mkdir(parents=True)
    def blob(data, media):
        digest = sha(data)
        (root / 'blobs/sha256' / digest[7:]).write_bytes(data)
        return {'digest':digest, 'size':len(data), 'mediaType':media}
    layers, diffs = [], []
    for group in groups:
        data, diff = tar_layer(group)
        layers.append(blob(data, 'application/vnd.oci.image.layer.v1.tar+gzip'))
        diffs.append(diff)
    config = {'architecture':'amd64', 'os':'linux', 'config':{'Cmd':['/bin/bash']},
              'rootfs':{'type':'layers', 'diff_ids':diffs}, 'history':[]}
    cfg = blob(json.dumps(config).encode(), 'application/vnd.oci.image.config.v1+json')
    manifest = {'schemaVersion':2, 'config':cfg, 'layers':layers}
    desc = blob(json.dumps(manifest).encode(), 'application/vnd.oci.image.manifest.v1+json')
    (root/'index.json').write_text(json.dumps({'schemaVersion':2,'manifests':[desc]}))
    (root/'split-report.json').write_text(json.dumps({'repacked_compressed_bytes':sum(x['size'] for x in layers)}))
    return manifest


class SplitVerificationTests(unittest.TestCase):
    def fixture(self, tmp, changed=False):
        root = Path(tmp)
        a, b = ('a', b'one'), ('b', b'two')
        layout(root/'old', [[a,b], []])
        manifest = layout(root/'new', [[a], [('b', b'bad') if changed else b], []])
        with tarfile.open(root/'original.tar', 'w') as tar:
            for file in (root/'old').rglob('*'):
                if file.is_file():
                    tar.add(file, arcname=str(file.relative_to(root/'old')))
        return root/'original.tar', root/'new', manifest

    def test_exact_ordered_filetree_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new, _ = self.fixture(tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                m.validate(old, new)

    def test_self_consistent_changed_payload_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new, _ = self.fixture(tmp, changed=True)
            with self.assertRaisesRegex(ValueError, 'TAR content'):
                m.validate(old, new)

    def test_corrupt_blob_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new, manifest = self.fixture(tmp)
            file = new/'blobs/sha256'/manifest['layers'][0]['digest'][7:]
            data = file.read_bytes()
            file.write_bytes(bytes([data[0] ^ 1]) + data[1:])
            with self.assertRaisesRegex(ValueError, 'OCI SHA'):
                m.validate(old, new)
