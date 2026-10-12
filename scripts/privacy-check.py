#!/usr/bin/env python3
"""Fail closed on personal infrastructure in tracked text/paths and new Git metadata.

Reports only category, path and line, never the matched private value. Public
service names, loopback/bind addresses, RFC 5737 documentation IPs and explicit
example identities are permitted; real endpoints belong in environment variables.
"""
import argparse
import ipaddress
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "personal-home": re.compile(r"(?:/Users/|/home/)(?!runner(?:/|\b)|linuxbrew(?:/|\b)|example(?:/|\b))[A-Za-z][\w.-]+(?:/|\b)"),
    "private-tailnet": re.compile(r"\b(?:[\w-]+\.)*(?:tail[a-f0-9]{4,}|tailnet-[a-z0-9]+)\.ts\.net\b", re.I),
    "personal-device": re.compile(r"\b(?:mac[b]ook|mac[-]mini|mac[ ]mini|workstation-von-|[\w-]+-von-[\w-]+)\b", re.I),
    "infrastructure-id": re.compile(r"\b(?:i-[a-z0-9]{12,}|ecs\.[a-z0-9]+\.[a-z0-9]+)\b"),
    "literal-ssh-target": re.compile(r"\b(?:ssh|scp)\s+(?:\S+\s+)*?(?:root|admin)@(?!(?:example\.(?:com|net)|\$|<))[a-z0-9][a-z0-9.-]+", re.I),
    "credential-uri": re.compile(r"https?://[^\s/:@]+:[^\s/@]+@", re.I),
}
IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
DOC_NETWORKS = tuple(ipaddress.ip_network(s) for s in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"))
# Exact version exception, not a blanket path exclusion: the published dependency
# inventory must remain byte-identical. This is a wheel version, not a host.
VERSION_VALUES = {"4.10.0.84"}
EMAIL = re.compile(r"[\w.+-]+@(?:[\w-]+\.)+[A-Za-z]{2,}")


def findings(text):
    result = []
    for number, line in enumerate(text.splitlines(), 1):
        for category, rx in PATTERNS.items():
            if rx.search(line):
                result.append((number, category))
        for candidate in IPV4.findall(line):
            if candidate in VERSION_VALUES:
                continue
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if address.is_loopback or address.is_unspecified or any(address in n for n in DOC_NETWORKS):
                continue
            result.append((number, "literal-infrastructure-ip"))
        # Real pod identifiers in prose/metadata. Placeholders have separators.
        for match in re.finditer(r'(?i)\b(?:pod(?:_id| id)?|template(?:_id| id))["` :|]+([a-z0-9]{10,16})(?![a-z0-9-])', line):
            identifier = match.group(1)
            if any(c.isdigit() for c in identifier) and any(c.isalpha() for c in identifier):
                result.append((number, "literal-resource-id"))
    return sorted(set(result))


def metadata_findings(text):
    result = findings(text)
    for number, line in enumerate(text.splitlines(), 1):
        for email in EMAIL.findall(line):
            if not (email.endswith("@users.noreply.github.com") or email.endswith("@example.invalid")
                    or email.endswith("@github.com")):
                result.append((number, "nonpublic-git-email"))
        if re.search(r"(?i)\b(?:root|admin)@[^\s<>]+", line):
            result.append((number, "host-git-identity"))
    return sorted(set(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commits", help="Git revision range of NEW commits, not unsanitized historical ancestors")
    args = parser.parse_args()
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    violations = []
    for name in filter(None, paths):
        path = ROOT / name
        if not path.is_file():
            continue
        violations += [(name, n, c) for n, c in findings(name)]
        raw = path.read_bytes()
        if b"\0" in raw:
            continue
        violations += [(name, n, c) for n, c in findings(raw.decode("utf-8", errors="replace"))]
    if args.commits:
        if args.commits.startswith("-"):
            parser.error("Invalid revision range")
        shas = subprocess.check_output(["git", "rev-list", args.commits, "--"], cwd=ROOT, text=True).splitlines()
        for sha in shas:
            text = subprocess.check_output(["git", "show", "-s", "--format=%an <%ae>%n%cn <%ce>%n%B", sha], cwd=ROOT, text=True)
            violations += [("commit:" + sha[:12], n, c) for n, c in metadata_findings(text)]
    for path, number, category in violations:
        print(f"{path}:{number}: {category}")
    print(f"Privacy scan: {len(violations)} findings; {len(list(filter(None, paths)))} tracked paths")
    return int(bool(violations))


if __name__ == "__main__":
    raise SystemExit(main())
