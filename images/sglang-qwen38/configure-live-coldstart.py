#!/usr/bin/env python3
"""Configure ONLY a freshly created isolated RunPod test template from a proven baseline.
No paid GPU Pod creation. Output excludes template env/bootstrap content and secrets.
"""
import argparse,json,subprocess,sys

TEMPLATE_ID="fjz0hj6xwc"
SOURCE_ID="g6ey6ire16"
NAME="qwen38-coldstart-isolated-20261011"
def run(*args):
    return subprocess.run(["/opt/homebrew/bin/runpodctl",*args],capture_output=True,text=True,timeout=75)
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--minimal",action="store_true")
    args=a.parse_args()
    response=run("template","list","--type","user","-o","json")
    if response.returncode: raise RuntimeError("Unable to list templates")
    templates=json.loads(response.stdout)
    def find(i):
        matching=[x for x in templates if x.get("id")==i]
        if len(matching)!=1: raise ValueError("Missing template: "+i)
        return matching[0]
    orig, candidate=find(SOURCE_ID),find(TEMPLATE_ID)
    if candidate.get("name")!=NAME or not candidate.get("imageName","").startswith("ghcr.io/tommyfive/qwen38-sglang:"):
        raise ValueError("Wrong isolated candidate target")
    if candidate.get("containerRegistryAuthId")!="cmutxmy57004u13i0uprfwtld":
        raise ValueError("Private GHCR registry auth missing")
    env=dict(orig.get("env") or {})
    if args.minimal:
        required=set("""
        BOOTSTRAP_B64 COLDSTART_TRACE HF_TOKEN SGLANG_API_KEY MODEL_ID SERVED_NAME
        MAX_LEN SPEC MEM_FRAC MAMBA_RATIO SERVE_WEBUI ENABLE_SSH BENCHMARK DEBUG
        MODEL_STORAGE MODEL_RAM_DIR MODEL_RAM_RELEASE_AFTER_LOAD MODEL_SSD_DIR NETWORK_MODE
        RUNTIME_LOG_DIR STORAGE_HELPER_B64
        """.split())
        missing=required-set(env)
        if missing: raise ValueError("Missing source env keys: "+",".join(sorted(missing)))
        env={k:env[k] for k in required}
    if env.get("COLDSTART_TRACE")!="1" or env.get("MODEL_STORAGE")!="ram" or env.get("SPEC")!="dflash2":
        raise ValueError("Lost measurement setup")
    if not env.get("SGLANG_API_KEY","").startswith("{{ RUNPOD_SECRET_"):
        raise ValueError("Authenticated API prerequisite failed")
    print("Template env update: isolated=",TEMPLATE_ID,"keys=",len(env),"mode=","minimal" if args.minimal else "full")
    resp=run("template","update",TEMPLATE_ID,"--env",json.dumps(env,separators=(",",":")),"-o","json")
    if resp.returncode:
        # Avoid printing server response / CLI command / secret-bearing env.
        print("TEMPLATE_UPDATE_FAILED exit=",resp.returncode, file=sys.stderr)
        sys.exit(2)
    info=json.loads(resp.stdout)
    if info.get("id")!=TEMPLATE_ID: raise RuntimeError("Unexpected response template ID")
    print("TEMPLATE_READY id=",TEMPLATE_ID,"env_keys=",len(info.get("env",{})),"coldtrace=",info.get("env",{}).get("COLDSTART_TRACE"))
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("TEMPLATE_SETUP_ERROR",type(e).__name__,file=sys.stderr)
        sys.exit(1)
