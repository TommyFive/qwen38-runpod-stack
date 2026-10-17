#!/usr/bin/env python3
"""Offline contract tests for template-first overrides; no RunPod API calls."""
import importlib.util
import base64
import gzip
import tempfile
import pathlib
import types
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("qwen38_template_first", ROOT/"scripts/resolve-template-launch.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

REF=lambda name:"{{ RUNPOD_SECRET_"+name+" }}"
def fixture(lean=False,mode="runpod",variant="custom",disk=30):
    e={"NETWORK_MODE":mode,"SERVE_WEBUI":"0" if lean else "1",
       "SGLANG_API_KEY":REF("LLAMA_API_KEY"),"HF_TOKEN":REF("HF_TOKEN"),
       "TS_HOSTNAME":"llm","TS_ENABLE_SSH":"1","MODEL_ID":"test/example",
       "SPEC":"dflash2","MAX_LEN":"262144","MEM_FRAC":"0.85",
       "MODEL_STORAGE":"ram","MODEL_RAM_DIR":"/dev/shm/qwen38-hf",
       "MODEL_SSD_DIR":"/workspace/hf","MODEL_RAM_RELEASE_AFTER_LOAD":"0",
       "BENCHMARK":"0","DEBUG":"0","COLDSTART_TRACE":"1","ENABLE_SSH":"0"}
    for key in mod.HELPERS:e[key]="YXNkZg=="
    if mode=="tailnet":e["TS_AUTHKEY"]=REF("TS_AUTHKEY")
    if not lean:
        e["WEBUI_ADMIN_EMAIL"]="admin@example.invalid"
        e["WEBUI_ADMIN_PASSWORD"]=REF("QWEN38_WEBUI_ADMIN_PASSWORD")
    return {"id":"test-id","imageName":mod.CUSTOM if variant=="custom" else mod.OFFICIAL,
            "env":e,"containerDiskInGb":disk,
            "ports":[] if mode=="tailnet" else (["8000/http"] if lean else ["8000/http","8080/http"])}

def args(lean=False,mode="runpod",variant="custom",gpu="pro6000"):
    return types.SimpleNamespace(template_id="test-id",lean=lean,mode=mode,variant=variant,gpu=gpu)

class TemplateFirst(unittest.TestCase):
    def test_all_eight_profiles_no_overrides(self):
        for lean in (False,True):
            for mode in ("runpod","tailnet"):
                for variant in ("custom","official"):
                    with self.subTest(lean=lean,mode=mode,variant=variant):
                        d=mod.resolve(fixture(lean,mode,variant,disk=20 if variant=="official" else 30),
                                      args(lean,mode,variant),{})
                        self.assertEqual(d["env_overrides"],{})
                        self.assertEqual(d["disk_gb"],20 if variant=="official" else 30)
                        self.assertEqual(d["hostname"],"llm")

    def test_single_explicit_override(self):
        d=mod.resolve(fixture(),args(),{"CLI_TS_HOSTNAME":"testing"})
        self.assertEqual(d["env_overrides"],{"TS_HOSTNAME":"testing"})
        self.assertEqual(d["hostname"],"testing")

    def test_cli_wins_over_shell(self):
        d=mod.resolve(fixture(),args(),{"TS_HOSTNAME":"shell","CLI_TS_HOSTNAME":"cli"})
        self.assertEqual(d["env_overrides"],{"TS_HOSTNAME":"cli"})

    def test_no_implicit_benchmark_or_spec(self):
        d=mod.resolve(fixture(),args(),{"CLI_BENCHMARK":"1"})
        self.assertEqual(d["env_overrides"],{"BENCHMARK":"1"})
        self.assertEqual(d["spec"],"dflash2")

    def test_storage_disk_upshift_only_when_needed(self):
        d=mod.resolve(fixture(),args(),{"CLI_STORAGE":"ssd"})
        self.assertEqual(d["env_overrides"],{"MODEL_STORAGE":"ssd"})
        self.assertEqual(d["disk_gb"],150)
        with self.assertRaises(mod.Invalid):
            mod.resolve(fixture(),args(),{"CLI_STORAGE":"ssd","QWEN38_FULL_DISK_GB":"30"})
        d=mod.resolve(fixture(disk=150),args(),{"CLI_STORAGE":"ssd"})
        self.assertEqual(d["disk_gb"],150)
        d=mod.resolve(fixture(disk=45),args(),{"CLI_STORAGE":"ram"})
        self.assertEqual(d["disk_gb"],45)

    def test_template_stored_ssd_disk(self):
        t=fixture(disk=150)
        t["env"]["MODEL_STORAGE"]="ssd"
        d=mod.resolve(t,args(),{})
        self.assertEqual(d["disk_gb"],150)
        self.assertEqual(d["env_overrides"],{})

    def test_secret_reference_inherited_and_replaced_explicitly(self):
        self.assertEqual(mod.resolve(fixture(),args(),{})["api_secret_name"],"LLAMA_API_KEY")
        d=mod.resolve(fixture(),args(),{"QWEN38_API_SECRET_NAME":"CUSTOM_SECRET"})
        self.assertEqual(d["env_overrides"],{"SGLANG_API_KEY":REF("CUSTOM_SECRET")})
        with self.assertRaises(mod.Invalid):
            mod.resolve(fixture(),args(),{"QWEN38_API_SECRET_NAME":"bad/name"})

    def test_security_fail_closed(self):
        t=fixture(mode="tailnet"); t["ports"]=["8000/http"]
        with self.assertRaises(mod.Invalid):mod.resolve(t,args(mode="tailnet"),{})
        t=fixture(mode="tailnet"); t["env"].pop("TS_AUTHKEY")
        with self.assertRaises(mod.Invalid):mod.resolve(t,args(mode="tailnet"),{})
        t=fixture();t["env"].pop("BOOTSTRAP_B64")
        with self.assertRaises(mod.Invalid):mod.resolve(t,args(),{})
        t=fixture();t["env"]["SGLANG_API_KEY"]="plaintext"
        with self.assertRaises(mod.Invalid):mod.resolve(t,args(),{})
        t=fixture(lean=True);t["env"]["WEBUI_ADMIN_PASSWORD"]=REF("P")
        with self.assertRaises(mod.Invalid):mod.resolve(t,args(lean=True),{})
        t=fixture(mode="tailnet");t["env"]["TS_HOSTNAME"]=""
        with self.assertRaises(mod.Invalid):mod.resolve(t,args(mode="tailnet"),{})

    def test_webui_noauth_only_tailnet_full(self):
        t=fixture(mode="tailnet")
        d=mod.resolve(t,args(mode="tailnet"),{"QWEN38_WEBUI_AUTH":"0"})
        self.assertEqual(d["env_overrides"],{"QWEN38_WEBUI_AUTH":"0"})
        self.assertEqual(d["webui_auth"],"0")
        t["env"]["QWEN38_WEBUI_AUTH"]="0"
        t["env"].pop("WEBUI_ADMIN_EMAIL")
        t["env"].pop("WEBUI_ADMIN_PASSWORD")
        self.assertEqual(mod.resolve(t,args(mode="tailnet"),{})["env_overrides"],{})
        with self.assertRaises(mod.Invalid):
            mod.resolve(t,args(mode="tailnet"),{"QWEN38_WEBUI_AUTH":"1"})
        for bad in ("invalid","false","","2"):
            with self.subTest(value=bad),self.assertRaises(mod.Invalid):
                mod.resolve(fixture(mode="tailnet"),args(mode="tailnet"),{"QWEN38_WEBUI_AUTH":bad})
        with self.assertRaises(mod.Invalid):
            mod.resolve(fixture(),args(),{"QWEN38_WEBUI_AUTH":"0"})
        with self.assertRaises(mod.Invalid):
            mod.resolve(fixture(lean=True,mode="tailnet"),args(lean=True,mode="tailnet"),{"QWEN38_WEBUI_AUTH":"0"})
        t=fixture()
        t["env"]["QWEN38_WEBUI_AUTH"]="0"
        with self.assertRaises(mod.Invalid):mod.resolve(t,args(),{})
        t=fixture(mode="tailnet");t["ports"]=["8080/http"]
        with self.assertRaises(mod.Invalid):
            mod.resolve(t,args(mode="tailnet"),{"QWEN38_WEBUI_AUTH":"0"})

    def test_local_override_uses_template_codec(self):
        data=b"#!/bin/bash\\necho test\\n"
        for compressed in (False, True):
            with self.subTest(compressed=compressed), tempfile.TemporaryDirectory() as td:
                path=pathlib.Path(td)/"helper.sh"
                path.write_bytes(data)
                template=fixture()
                original=gzip.compress(b"base", mtime=0) if compressed else b"base"
                template["env"]["BOOTSTRAP_B64"]=base64.b64encode(original).decode()
                result=mod.resolve(template,args(),{"QWEN38_BOOTSTRAP":str(path)})
                encoded=base64.b64decode(result["env_overrides"]["BOOTSTRAP_B64"])
                self.assertEqual(gzip.decompress(encoded) if compressed else encoded, data)

    def test_invalid_bootstrap_base64_fails_closed(self):
        template=fixture()
        template["env"]["BOOTSTRAP_B64"]="not!base64"
        with self.assertRaisesRegex(mod.Invalid,"Invalid bootstrap Base64"):
            mod.resolve(template,args(),{})

    def test_invalid_values(self):
        for key,value in (
            ("CLI_TS_HOSTNAME","Bad.Host"),("CLI_STORAGE","bad"),
            ("QWEN38_DEBUG","bad"),("QWEN38_RAM_PEAK_FACTOR","infinity"),
            ("QWEN38_MODEL_RAM_RELEASE_AFTER_LOAD","bad"),
            ("BENCHMARK_RUNS","0"),("CLI_MAX_LEN","NaN")):
            with self.subTest(key=key),self.assertRaises((mod.Invalid,ValueError)):
                mod.resolve(fixture(),args(),{key:value})

    def test_gpu_5090_safety(self):
        d=mod.resolve(fixture(),args(gpu="5090"),{})
        self.assertEqual(d["env_overrides"],{"MAX_LEN":"65536","MEM_FRAC":"0.90"})
        with self.assertRaises(mod.Invalid):
            mod.resolve(fixture(),args(gpu="5090"),{"CLI_MAX_LEN":"131072"})

if __name__=="__main__":unittest.main()
