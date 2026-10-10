#!/usr/bin/env python3
"""RunPod private-template port hardening. Never log keys or response bodies."""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://rest.runpod.io/v1/templates/"
SECRETS = {"TS_AUTHKEY", "HF_TOKEN", "SGLANG_API_KEY", "WEBUI_ADMIN_PASSWORD"}


class PortSafetyError(Exception):
    pass


def request(method, template_id, payload=None):
    key = os.environ.get("RUNPOD_API_KEY", "")
    if not key:
        raise PortSafetyError("RUNPOD_API_KEY unavailable; load Keychain credentials")
    if not re.fullmatch(r"[A-Za-z0-9_-]{5,64}", template_id):
        raise PortSafetyError("invalid template ID")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + template_id, method=method, data=data,
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"})
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
    if SECRETS.intersection(env):
        raise PortSafetyError("embedded secret keys in template")
    if not env.get("BOOTSTRAP_B64") or not env.get("TAILSCALE_RUNTIME_B64"):
        raise PortSafetyError("missing bootstrap or Tailscale runtime")
    ports = template.get("ports")
    if not isinstance(ports, list):
        raise PortSafetyError("missing/unrecognized ports field")
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
