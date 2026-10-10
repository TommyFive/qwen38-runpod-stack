#!/usr/bin/env python3
"""RunPod private-template port hardening. Never log keys or response bodies."""
import argparse
import json
from pathlib import Path
import stat
try:
    import tomllib
except ImportError:  # macOS system Python 3.9; avoid external dependencies
    tomllib = None
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://rest.runpod.io/v1/templates/"
SECRETS = {"TS_AUTHKEY", "HF_TOKEN", "SGLANG_API_KEY", "WEBUI_ADMIN_PASSWORD"}


class PortSafetyError(Exception):
    pass


def runpod_api_key(config_path=None):
    """Prefer explicit env; fall back to native runpodctl config without leaking key."""
    key = os.environ.get("RUNPOD_API_KEY", "")
    if key:
        return key
    path = Path(config_path) if config_path is not None else Path.home() / ".runpod/config.toml"
    try:
        if path.is_symlink():
            raise PortSafetyError("RunPod config must not be a symlink")
        meta = path.stat()
        if (meta.st_uid != os.getuid() or
                stat.S_IMODE(meta.st_mode) & 0o077 or not stat.S_ISREG(meta.st_mode)):
            raise PortSafetyError("RunPod config ownership/permissions unsafe")
        if tomllib is not None:
            with path.open("rb") as handle:
                value = tomllib.load(handle).get("apiKey", "")
        else:
            # Minimal, strict parser of the native runpodctl root-level TOML
            # string key; no third-party parser or shell eval on Python 3.9.
            value = ""
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("["):  # root-level keys only
                    break
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, literal = line.partition("=")
                if name.strip() == "apiKey":
                    literal = literal.strip()
                    if literal.startswith('"'):
                        value = json.loads(literal)
                    elif literal.startswith("'") and literal.endswith("'"):
                        value = literal[1:-1]
                    break
        if isinstance(value, str) and value:
            return value
    except (OSError, ValueError, UnicodeDecodeError):
        pass
    raise PortSafetyError("RunPod API credential unavailable in environment/native config")


def request(method, template_id, payload=None):
    key = runpod_api_key()
    if not re.fullmatch(r"[A-Za-z0-9_-]{5,64}", template_id):
        raise PortSafetyError("invalid template ID")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + template_id, method=method, data=data,
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json",
                                          "Accept": "application/json",
                                          # RunPod edge returns HTTP 403 to Python-urllib UA.
                                          # A browser-compatible UA reaches API auth (HTTP 401 unauthenticated).
                                          "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                                        "AppleWebKit/537.36 qwen38-private-template-ports/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            if method == "DELETE":
                return {}
            result = json.loads(response.read(4 * 1024 * 1024))
            if not isinstance(result, dict):
                raise PortSafetyError("unexpected template response type")
            return result
    except urllib.error.HTTPError as exc:
        raise PortSafetyError(f"RunPod {method} returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise PortSafetyError(f"RunPod {method} connection failed") from None
    except (ValueError, UnicodeDecodeError):
        raise PortSafetyError(f"RunPod {method} response invalid") from None


def validate(template, template_id, require_empty=True):
    if template.get("id") != template_id:
        raise PortSafetyError("template ID mismatch")
    env = template.get("env")
    if not isinstance(env, dict) or env.get("NETWORK_MODE") != "tailnet":
        raise PortSafetyError("template is not in tailnet mode")
    # Secret *references* are safe to persist in templates, plaintext is not.
    for secret_name in SECRETS.intersection(env):
        value = env[secret_name]
        if not isinstance(value, str) or not re.fullmatch(
                r"\{\{ RUNPOD_SECRET_[A-Za-z][A-Za-z0-9_]* \}\}", value):
            raise PortSafetyError("embedded plaintext secret in template")
    if not env.get("BOOTSTRAP_B64") or not env.get("TAILSCALE_RUNTIME_B64"):
        raise PortSafetyError("missing bootstrap or Tailscale runtime")
    # RunPod omits ports on REST GET when there are no mappings.
    # Explicit null/unknown shapes still fail closed. During repair, PATCH [] is
    # always issued, even if the preflight GET omits the key.
    ports = template.get("ports", [])
    if not isinstance(ports, list):
        raise PortSafetyError("unrecognized ports field")
    if require_empty and (ports or template.get("portsConfig")):
        raise PortSafetyError("private template has public RunPod ports")


def verify(template_id):
    validate(request("GET", template_id), template_id)
    print("PASS: portless private template " + template_id)


def repair(template_id):
    validate(request("GET", template_id), template_id, require_empty=False)
    # runpodctl template update --ports='' omits the field. Send [] explicitly.
    request("PATCH", template_id, {"ports": []})
    verify(template_id)  # reread persisted state; PATCH 200 alone is not proof


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("verify", "repair"))
    p.add_argument("template_id")
    p.add_argument("--delete-on-failure", action="store_true")
    a = p.parse_args()
    if a.delete_on_failure and a.action != "repair":
        p.error("--delete-on-failure only for repair")
    try:
        (repair if a.action == "repair" else verify)(a.template_id)
        return 0
    except PortSafetyError as exc:
        print(f"FAIL: {exc} (template {a.template_id})", file=sys.stderr)
        if a.delete_on_failure:
            try:
                request("DELETE", a.template_id)
                print(f"Deleted unsafe new template {a.template_id}", file=sys.stderr)
            except PortSafetyError:
                print(f"DELETE FAILED: remove unsafe template {a.template_id} manually",
                      file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
