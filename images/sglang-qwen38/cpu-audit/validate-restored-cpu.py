#!/usr/bin/env python3
"""Post-VPS CPU-only acceptance of three *already-pulled* digest-pinned images.

Never builds, downloads, deploys, changes registry visibility or uses GPUs.
Containers have no network, are read-only and run without extra Linux caps.
Actual digest-pinned docker pulls must be completed separately before this.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

REFERENCE = "local/qwen38-cpu-test:baseline"
CANDIDATES = {
    "rust": "local/qwen38-cpu-test:rust",
    "rust-cuda": "local/qwen38-cpu-test:rust-cuda",
}
CONFIG_KEYS = (
    "Env", "Entrypoint", "Cmd", "WorkingDir", "User",
    "ExposedPorts", "Volumes", "StopSignal",
)

# Execute INSIDE images, never on the VPS. No third-party validation imports.
PROBE = r'''
import hashlib
import importlib
import json
import os
import sys
import time
from pathlib import Path

WHEEL = Path("/opt/sglang/lib/python3.12/site-packages/nvidia/cu13/lib")
SYSTEM = Path("/usr/local/cuda-13.0/targets/x86_64-linux/lib")
RUST = Path("/sgl-workspace/sglang/rust/target/release/deps")
PAIRS = (
    ("libcublasLt.so.13", "libcublasLt.so.13.1.1.3"),
    ("libcufft.so.12", "libcufft.so.12.0.0.61"),
    ("libcusparse.so.12", "libcusparse.so.12.6.3.3"),
    ("libcusolver.so.12", "libcusolver.so.12.0.4.66"),
    ("libcurand.so.10", "libcurand.so.10.4.0.35"),
    ("libnvrtc.alt.so.13", "libnvrtc.alt.so.13.0.88"),
    ("libnvrtc.so.13", "libnvrtc.so.13.0.88"),
    ("libcusolverMg.so.12", "libcusolverMg.so.12.0.4.66"),
    ("libcublas.so.13", "libcublas.so.13.1.1.3"),
    ("libnvperf_host.so", "libnvperf_host.so"),
    ("libnvperf_target.so", "libnvperf_target.so"),
)
mode=sys.argv[1]

def sha(path):
    h=hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(4*1024*1024), b""):
            h.update(b)
    return h.hexdigest()

report={"mode":mode, "imports":{}, "cuda":{}, "rust_intermediates": None}
for mod in ("torch","flashinfer","sglang","transformers"):
    started=time.monotonic()
    module=importlib.import_module(mod)
    result={"version":str(getattr(module,"__version__","unknown")),
            "duration_seconds":round(time.monotonic()-started,3)}
    report["imports"][mod]=result
    print("IMPORT",mod,result,flush=True)

if not RUST.is_dir():
    raise RuntimeError("Missing Rust output directory")
rust=list(RUST.rglob("*.rlib"))+list(RUST.rglob("*.rmeta"))
report["rust_intermediates"]=len(rust)
if mode == "baseline" and not rust:
    raise RuntimeError("Expected reference Rust intermediates absent")
if mode != "baseline" and rust:
    raise RuntimeError("Rust intermediates remain: "+str(len(rust)))

total=0
for wheel_name, system_name in PAIRS:
    wheel=WHEEL/wheel_name
    system=SYSTEM/system_name
    if not system.is_file() or system.is_symlink():
        raise RuntimeError("System CUDA target is not a regular file: "+str(system))
    if not wheel.is_file():
        raise RuntimeError("Missing wheel CUDA library: "+str(wheel))
    link=wheel.is_symlink()
    expected_link=(mode=="rust-cuda")
    if link != expected_link:
        raise RuntimeError("CUDA symlink expectation failed: "+str(wheel))
    if link and wheel.resolve(strict=True)!=system.resolve(strict=True):
        raise RuntimeError("CUDA symlink resolves to unexpected target: "+str(wheel))
    a,b=sha(wheel),sha(system)
    if a!=b:
        raise RuntimeError("Wheel/system CUDA SHA256 mismatch: "+wheel_name)
    sz=wheel.stat().st_size
    total+=sz
    report["cuda"][wheel_name]={"bytes":sz,"wheel_sha256":a,"system_sha256":b,
         "is_symlink":link,"target":str(wheel.resolve(strict=True))}

report["cuda_pair_bytes"]=total
if total!=1679571048:
    raise RuntimeError("Unexpected total CUDA duplicate byte size: "+str(total))
print("CPU_AUDIT_JSON:"+json.dumps(report,sort_keys=True),flush=True)
'''

def info(image):
    p=subprocess.run(["docker","image","inspect",image],check=True,
                     capture_output=True,text=True,timeout=30)
    return json.loads(p.stdout)[0]


def assert_metadata(reference, candidate, name):
    if candidate.get("Architecture") != "amd64" or candidate.get("Os") != "linux":
        raise ValueError("Wrong image architecture: "+name)
    a,b=reference["Config"],candidate["Config"]
    mismatched=[k for k in CONFIG_KEYS if a.get(k)!=b.get(k)]
    if mismatched:
        raise ValueError("Changed runtime config in "+name+": "+str(mismatched))
    labels_a=a.get("Labels") or {}
    labels_b=b.get("Labels") or {}
    diff=[k for k,v in labels_a.items() if labels_b.get(k)!=v]
    if diff:
        raise ValueError("Changed original labels "+name+": "+str(diff))
    if labels_b.get("ai.qwen38.experimental-repack")!=name:
        raise ValueError("Missing/incorrect experiment label: "+name)
    return True


def launch_probe(image, name, outdir, timeout=360):
    args=[
        "docker","run","--rm","--pull","never","--network","none",
        "--read-only","--cap-drop","ALL","--security-opt","no-new-privileges",
        "--pids-limit","256","--memory","8g","--cpus","6",
        "--tmpfs","/tmp:rw,nosuid,size=512m",
        "--tmpfs","/root/.cache:rw,nosuid,size=512m",
        "--env","PYTHONDONTWRITEBYTECODE=1",
        "--env","HF_HUB_OFFLINE=1","--env","TRANSFORMERS_OFFLINE=1",
        "--env","OMP_NUM_THREADS=1",
        "--entrypoint","/opt/sglang/bin/python3",image,"-c",PROBE,name,
    ]
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        (outdir/f"{name}.timeout.txt").write_text(str(exc)+"\n")
        raise RuntimeError(f"{name} container timed out after {timeout}s") from exc
    (outdir/f"{name}.stdout.log").write_text(p.stdout)
    (outdir/f"{name}.stderr.log").write_text(p.stderr)
    if p.returncode:
        raise RuntimeError(f"{name} import/CUDA probe failed exit={p.returncode}; "
                           f"see {name}.stderr.log / stdout.log")
    records=[x[len("CPU_AUDIT_JSON:"):] for x in p.stdout.splitlines()
             if x.startswith("CPU_AUDIT_JSON:")]
    if len(records)!=1:
        raise RuntimeError(f"{name} did not emit exactly one CPU_AUDIT_JSON")
    report=json.loads(records[0])
    (outdir/f"{name}.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    return report


def compare_results(results):
    baseline=results["baseline"]
    expected=set(baseline["cuda"])
    if len(expected)!=11:
        raise ValueError("Expected exactly 11 CUDA libraries")
    for name in CANDIDATES:
        item=results[name]
        if set(item["cuda"])!=expected:
            raise ValueError("CUDA pair set changed in "+name)
        if set(item["imports"])!=set(baseline["imports"]):
            raise ValueError("Python module set changed in "+name)
        for mod,ref in baseline["imports"].items():
            if ref["version"]!=item["imports"][mod]["version"]:
                raise ValueError("Version mismatch in "+name+": "+mod)
        for lib,ref in baseline["cuda"].items():
            if item["cuda"][lib]["wheel_sha256"]!=ref["wheel_sha256"]:
                raise ValueError("Changed actual CUDA library bytes in "+name+": "+lib)
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=Path("/opt/qwen38-verify/reports"))
    args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    images={"baseline":REFERENCE,**CANDIDATES}
    inspected={name:info(img) for name,img in images.items()}
    for name in CANDIDATES:
        assert_metadata(inspected["baseline"],inspected[name],name)
    (args.output_dir/"image-inspect-summary.json").write_text(json.dumps(
        {name:{"image_id":item["Id"],"size_uncompressed_bytes":item["Size"],
               "architecture":item["Architecture"],"os":item["Os"],
               "config":item["Config"]}
         for name,item in inspected.items()},indent=2,sort_keys=True)+"\n")
    results={}
    for name,img in images.items():
        print("START",name,flush=True)
        results[name]=launch_probe(img,name,args.output_dir)
        print("PASS",name,flush=True)
    compare_results(results)
    (args.output_dir/"cpu-validation-summary.json").write_text(json.dumps(
        {"status":"PASS","candidates":list(CANDIDATES),
         "modules":list(results["baseline"]["imports"]),
         "cuda_pairs":11,"cuda_duplicate_logical_bytes":1679571048,
         "scope":"CPU-only; GPU JIT/kernel/runtime validation NOT performed"},
        indent=2)+"\n")
    print("CPU-ONLY VALIDATION PASS",flush=True)


if __name__=="__main__":
    try:
        main()
    except Exception as e:
        print("CPU-ONLY VALIDATION FAIL:",repr(e),file=sys.stderr,flush=True)
        raise
