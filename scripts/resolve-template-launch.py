#!/usr/bin/env python3
"""RunPod template-first launch plan: only explicitly requested ENV overrides."""
import argparse
import base64
import gzip
import json
import math
import os
import pathlib
import re
import sys

CUSTOM="ghcr.io/tommyfive/qwen38-sglang@sha256:820c0ef5e0752c0243946dbdce342cc8d363c1d5e115aa19c04fe497e51400c7"
OFFICIAL="lmsysorg/sglang:dev-qwen38-27b-dflash2"
SECRET=re.compile(r"\{\{ RUNPOD_SECRET_([A-Za-z][A-Za-z0-9_]*) \}\}\Z")
HOST=re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
HELPERS=("BOOTSTRAP_B64","TAILSCALE_RUNTIME_B64","STORAGE_HELPER_B64","BENCHMARK_B64")

class Invalid(ValueError):
    pass

def size(v):
    try: n=int(v)
    except (ValueError,TypeError): raise Invalid("Invalid disk size") from None
    if not 20<=n<=500 or str(v)!=str(n): raise Invalid("Disk must be 20..500 GiB")
    return n

def resolve(t, args, source=None):
    e=os.environ if source is None else source
    def option(cli, envname):
        return e.get(cli) if cli in e else e.get(envname)
    def validate_secret(key, env):
        if not isinstance(env.get(key),str) or not SECRET.fullmatch(env[key]):
            raise Invalid(key+" must use RunPod Secret reference")
    if t.get("id")!=args.template_id: raise Invalid("Template ID mismatch")
    if t.get("imageName")!={"custom":CUSTOM,"official":OFFICIAL}[args.variant]:
        raise Invalid("Template image mismatch")
    if args.variant=="official" and t.get("containerRegistryAuthId"):
        raise Invalid("Unexpected private registry auth in official template")
    env=t.get("env")
    if not isinstance(env,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in env.items()):
        raise Invalid("Template env is missing or invalid")
    if env.get("NETWORK_MODE")!=args.mode: raise Invalid("Template network mode mismatch")
    if env.get("SERVE_WEBUI")!=("0" if args.lean else "1"): raise Invalid("Full/Lean mode mismatch")
    ports=t.get("ports") or []
    if args.mode=="tailnet":
        if ports or t.get("portsConfig"): raise Invalid("SECURITY ERROR: Tailnet template must be portless")
        validate_secret("TS_AUTHKEY",env)
    else:
        if "8000/http" not in ports: raise Invalid("Public API port 8000 missing")
        if ("8080/http" in ports) == args.lean: raise Invalid("Public WebUI port mismatch")
        if "TS_AUTHKEY" in env: raise Invalid("Public template contains TS_AUTHKEY")
    validate_secret("SGLANG_API_KEY",env)
    if "HF_TOKEN" in env: validate_secret("HF_TOKEN",env)
    if not args.lean:
        validate_secret("WEBUI_ADMIN_PASSWORD",env)
        if "@" not in env.get("WEBUI_ADMIN_EMAIL",""): raise Invalid("Missing WebUI admin email")
    elif "WEBUI_ADMIN_PASSWORD" in env or "WEBUI_ADMIN_EMAIL" in env:
        raise Invalid("Lean template contains WebUI credentials")
    for k in HELPERS+("MODEL_ID","SPEC","MAX_LEN","MEM_FRAC","MODEL_STORAGE","MODEL_RAM_DIR","MODEL_SSD_DIR"):
        if not env.get(k): raise Invalid("Template missing "+k)
    # Keep explicit local helper overrides compatible with still-existing legacy
    # templates, while new gzip templates receive gzip-compressed overrides.
    try:
        bootstrap_wire = base64.b64decode(env["BOOTSTRAP_B64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise Invalid("Invalid bootstrap Base64 payload") from exc
    gzip_template = bootstrap_wire.startswith(b"\x1f\x8b")
    overrides={}
    for key,cli,local in (
        ("MODEL_ID","CLI_MODEL","QWEN38_OVERRIDE_MODEL_ID"),
        ("SPEC","CLI_SPEC","QWEN38_OVERRIDE_SPEC"),
        ("MAX_LEN","CLI_MAX_LEN","QWEN38_OVERRIDE_MAX_LEN"),
        ("MODEL_STORAGE","CLI_STORAGE","QWEN38_MODEL_STORAGE"),
        ("MODEL_RAM_DIR","CLI_RAM_DIR","QWEN38_MODEL_RAM_DIR"),
        ("MODEL_SSD_DIR","CLI_SSD_DIR","QWEN38_MODEL_SSD_DIR"),
        ("TS_HOSTNAME","CLI_TS_HOSTNAME","TS_HOSTNAME"),
        ("BENCHMARK","CLI_BENCHMARK","BENCHMARK"),
    ):
        val=option(cli,local)
        if val is not None: overrides[key]=val
    for key,local in (
        ("MODEL_RAM_PEAK_FACTOR","QWEN38_RAM_PEAK_FACTOR"),
        ("MODEL_RAM_RELEASE_AFTER_LOAD","QWEN38_MODEL_RAM_RELEASE_AFTER_LOAD"),
        ("BENCHMARK_RUNS","BENCHMARK_RUNS"),
        ("BENCHMARK_MAX_TOKENS","BENCHMARK_MAX_TOKENS"),
        ("BENCHMARK_TIMEOUT_SECONDS","BENCHMARK_TIMEOUT_SECONDS"),
        ("BENCHMARK_REPORT_PATH","BENCHMARK_REPORT_PATH"),
        ("DEBUG","QWEN38_DEBUG"),
        ("COLDSTART_TRACE","QWEN38_COLDSTART_TRACE"),
        ("ENABLE_SSH","QWEN38_ENABLE_SSH"),
        ("TS_ENABLE_SSH","TS_ENABLE_SSH"),
        ("WEBUI_ADMIN_EMAIL","QWEN38_WEBUI_ADMIN_EMAIL"),
    ):
        if local in e: overrides[key]=e[local]
    effective=dict(env,**overrides)
    if effective["MODEL_STORAGE"] not in ("ram","ssd"): raise Invalid("MODEL_STORAGE must be ram or ssd")
    for k in ("BENCHMARK","DEBUG","COLDSTART_TRACE","ENABLE_SSH","TS_ENABLE_SSH","MODEL_RAM_RELEASE_AFTER_LOAD"):
        if effective.get(k,"0") not in ("0","1"): raise Invalid(k+" must be 0 or 1")
    try:
        if int(effective["MAX_LEN"])<1 or str(int(effective["MAX_LEN"]))!=effective["MAX_LEN"]:
            raise ValueError()
    except ValueError:
        raise Invalid("MAX_LEN must be a positive integer") from None
    if effective["MODEL_STORAGE"]=="ssd" and effective.get("MODEL_RAM_RELEASE_AFTER_LOAD","0")=="1":
        raise Invalid("SSD storage cannot use RAM release")
    if "MODEL_RAM_PEAK_FACTOR" in overrides:
        try:
            v=float(overrides["MODEL_RAM_PEAK_FACTOR"])
            if not math.isfinite(v) or not 1.5<=v<=5:raise ValueError()
        except ValueError:raise Invalid("MODEL_RAM_PEAK_FACTOR must be 1.5..5.0") from None
        if effective["MODEL_STORAGE"]=="ssd":overrides.pop("MODEL_RAM_PEAK_FACTOR")
    for k,limit in (("BENCHMARK_RUNS",20),("BENCHMARK_MAX_TOKENS",4096),("BENCHMARK_TIMEOUT_SECONDS",7200)):
        if k in overrides:
            try:
                n=int(overrides[k])
                if not 1<=n<=limit or str(n)!=overrides[k]:raise ValueError()
            except ValueError:raise Invalid(k+" must be 1.."+str(limit)) from None
    name=effective.get("TS_HOSTNAME","")
    if not isinstance(name,str) or (name and not HOST.fullmatch(name)):
        raise Invalid("Invalid TS_HOSTNAME")
    if args.mode=="tailnet" and not name: raise Invalid("Tailnet requires nonempty TS_HOSTNAME")
    if args.gpu=="5090":
        # Hardware-specific safety rule, conditional on explicit GPU selection.
        try: n=int(effective["MAX_LEN"])
        except ValueError:raise Invalid("Invalid MAX_LEN") from None
        if n>65536 and "MAX_LEN" in overrides:raise Invalid("RTX 5090 requires MAX_LEN<=65536")
        if n>65536: overrides["MAX_LEN"]="65536"
        overrides["MEM_FRAC"]="0.90"
        effective.update(overrides)
    template_disk=size(t.get("containerDiskInGb"))
    disk_env="QWEN38_LEAN_DISK_GB" if args.lean else "QWEN38_FULL_DISK_GB"
    disk=(size(e[disk_env]) if disk_env in e else
          150 if effective["MODEL_STORAGE"]=="ssd" and env["MODEL_STORAGE"]!="ssd" else template_disk)
    if effective["MODEL_STORAGE"]=="ssd" and disk<50:raise Invalid("SSD requires >=50 GiB Container Disk")
    mode=e.get("QWEN38_CREDENTIAL_MODE","runpod_secrets")
    if mode not in ("runpod_secrets","local"):raise Invalid("Invalid credential mode")
    if mode=="runpod_secrets":
        for key,local in (("SGLANG_API_KEY","QWEN38_API_SECRET_NAME"),
                          ("HF_TOKEN","QWEN38_HF_SECRET_NAME"),
                          ("WEBUI_ADMIN_PASSWORD","QWEN38_WEBUI_PASSWORD_SECRET_NAME")):
            if local in e:
                label=e[local]
                if not label or not re.fullmatch("[A-Za-z][A-Za-z0-9_]*",label):
                    raise Invalid("Invalid RunPod Secret name")
                if args.lean and key=="WEBUI_ADMIN_PASSWORD":raise Invalid("Lean does not use WebUI password")
                overrides[key]="{{ RUNPOD_SECRET_"+label+" }}"
        if e.get("QWEN38_WEBUI_ADMIN_PASSWORD"):raise Invalid("Plaintext WebUI password forbidden")
    if args.lean and "WEBUI_ADMIN_EMAIL" in overrides:raise Invalid("Lean cannot override WebUI email")
    if not args.lean and ("@" not in effective.get("WEBUI_ADMIN_EMAIL","") or
                        any(c.isspace() for c in effective["WEBUI_ADMIN_EMAIL"])):
        raise Invalid("Invalid admin email")
    for local,key in (
        ("QWEN38_BOOTSTRAP","BOOTSTRAP_B64"),
        ("QWEN38_TAILSCALE_RUNTIME","TAILSCALE_RUNTIME_B64"),
        ("QWEN38_STORAGE_HELPER","STORAGE_HELPER_B64"),
        ("QWEN38_BENCHMARK_SCRIPT","BENCHMARK_B64"),
    ):
        if local in e:
            p=pathlib.Path(e[local])
            if not p.is_file() or p.stat().st_size==0:raise Invalid(local+" file missing")
            data=p.read_bytes()
            if gzip_template:
                data=gzip.compress(data, compresslevel=9, mtime=0)
            overrides[key]=base64.b64encode(data).decode("ascii")
    return {
      "env_overrides":overrides,"override_keys":sorted(overrides),
      "disk_gb":disk,"template_disk_gb":template_disk,
      "hostname":name,"model":effective["MODEL_ID"],"spec":effective["SPEC"],
      "max_len":effective["MAX_LEN"],"storage":effective["MODEL_STORAGE"],
      "benchmark":effective.get("BENCHMARK","0"),"ram_release":effective.get("MODEL_RAM_RELEASE_AFTER_LOAD","0"),
      "coldstart":effective.get("COLDSTART_TRACE","1"),
      "credential_mode":mode,"api_secret_name":SECRET.fullmatch(env["SGLANG_API_KEY"]).group(1),
      "template_id":args.template_id,"env_count":len(env)
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--template-id",required=True)
    p.add_argument("--variant",choices=["custom","official"],required=True)
    p.add_argument("--mode",choices=["runpod","tailnet"],required=True)
    p.add_argument("--gpu",required=True)
    p.add_argument("--lean",action="store_true")
    a=p.parse_args()
    try:print(json.dumps(resolve(json.load(sys.stdin),a),separators=(",",":")))
    except (Invalid,ValueError,TypeError,KeyError) as ex:
        print("TEMPLATE-FIRST VALIDATION FAILED: "+str(ex),file=sys.stderr);sys.exit(64)

if __name__=="__main__":main()
