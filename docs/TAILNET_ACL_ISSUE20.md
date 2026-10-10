# Tailnet HTTPS Serve — Issue #20: verified ACL root cause (2026-10-10)

## Live reproduction and conclusion

Issue [#20](https://github.com/TommyFive/qwen38-runpod-stack/issues/20)
was reproduced on **two** disposable Private Full RTX PRO 6000 pods.
On the second **Secure** cloud test (actual $2.49/hour, pod explicitly deleted
after testing), native Tailscale SSH and local applications worked, while
HTTPS Serve ports 443 and 8443 timed out.

Read-only `tailscale debug netmap` from the Pod showed the **inbound**
packet-filter rules allowed the authorized Mac mini client to reach **TCP/22**
but **not TCP/443 or TCP/8443**. An unrelated wide Tailnet selector allowed
TCP/8080. The Pod had a broad `tag:tagged-devices` identity shared with
other infrastructure. These are actual enforced rules distributed by the
Tailnet control plane — `tailscale serve status` displaying handlers does
**not** override them. This is a **confirmed ACL/grant denial**, not evidence
of a bug in SGLang, TLS generation, RunPod public networking, or the relay.

Testing over HTTPS with an explicit hostname/SNI-to-tailnet-IP mapping via
`curl --resolve` bypassed a separate Mac mini MagicDNS lookup problem,
but both TCP connections still timed out. Local unauthenticated SGLang
`/v1/models` returned **401** and OpenWebUI `/api/config` returned
**200**. Tailscale SSH over 22 worked. No public RunPod ports were enabled.

A prior Private Lean run reported reachable Serve on 443; we do **not**
assume the previous and current Tailscale policy snapshots were identical.
The current live Pod ACL rules explain the reproducible Private Full failure.

## Owner-approved policy update (2026-10-10)

The owner requires these HTTPS ports to be reachable by **all Tailnet members**, not just OpenClaw clients. The RunPod authentication key already has `tag:runpod-llm` and `tag:ssh-target`. Keep both tags and add TCP 443/8443 to the existing wildcard-source grant (which already allows TCP 8080) targeting `tag:runpod-llm`. This is tailnet-only access, not public RunPod port exposure. The test for `tag:openclaw` was updated accordingly. Live application/TLS validation remains outstanding; renewing the expiring auth key must preserve its existing tags. **This owner decision supersedes the dedicated-tag/narrow-source proposal in the historical section below.**

## Correct least-privilege design (tailnet-admin action required)

**Do not** add `tag:tagged-devices:443/8443` broadly. That tag also covers
other production VPN/VPS/router devices.

1. In the Tailscale admin policy, define a **dedicated**
   `tag:qwen38-pod` (owners restricted to the Tailnet admins or approved
   automation identity).
2. Add a scoped grant from explicitly authorized clients (e.g. Mac mini and
   MacBook Tailnet IPv4/32 or a managed client group) **only** to
   `tag:qwen38-pod` on `tcp:443` and `tcp:8443`. Leave existing SSH
   grants/policy intact.
3. Create a **tag-scoped, ephemeral** Tailscale auth key for
   `tag:qwen38-pod`; update the existing RunPod Secret **`TS_AUTHKEY`**
   through its secret-management UI. Never put a plaintext key in GitHub,
   PRs, terminal history, the Mac mini launcher environment, or template
   JSON. Four existing RunPod templates already use the Secret reference.
4. Recreate **only an explicitly approved disposable Pod** to receive
   the new tag and policy. Existing Pod identity is not retroactively
   retagged by editing the Secret. Verify the effective
   `PacketFilterRules` includes the intended clients on 443 and 8443,
   without granting those ports to unrelated tagged machines.
5. Verify default TLS/HTTPS, both API and UI, with no RunPod public ports;
   verify admin login and anonymous denial. Confirm `/v1/models` returns
   401 without and 200 with the authorized SGLang bearer.
6. On failure, revert the policy/Secret changes and terminate the exact
   disposable Pod ID. **Never** broaden `*` access to solve timeouts.

The following is a **fragment to integrate into the existing HuJSON
policy**, not a complete replacement. Replace the client placeholders
with validated identities and preserve existing rules:

```jsonc
{
  "tagOwners": {
    "tag:qwen38-pod": []
  },
  "grants": [
    {
      "src": ["<APPROVED_MAC_MINI_TAILNET_IP>/32", "<APPROVED_MACBOOK_TAILNET_IP>/32"],
      "dst": ["tag:qwen38-pod"],
      "ip": ["tcp:443", "tcp:8443"]
    }
  ]
}
```

Source identities may instead be an existing tightly controlled client
group. Audit the **union** of all grants and legacy ACLs: more-specific
grants cannot remove permissions supplied by an existing broader rule.

Admin access to the Tailnet policy is **not** available via the installed
GitHub/SSH tools or current Selected Tabs browser ACL. Consequently no
Tailnet policy edits or Tailscale auth-key rotations were performed in this
test. A policy change must be done via authorized Tailscale administration
before an additional paid validation Pod is warranted.

Official documentation:
- [Grants syntax](https://tailscale.com/docs/reference/syntax/grants)
- [Policy file / tag owners](https://tailscale.com/docs/reference/syntax/policy-file)
- [Auth-key tag behavior](https://tailscale.com/docs/features/access-control/auth-keys)
- [Serve and ACLs](https://tailscale.com/docs/features/tailscale-serve)

## Release acceptance (still open)

- [ ] Dedicated Pod tag and restrictive Tailnet grant deployed and read back.
- [ ] Client DNS/HTTPS name resolves; additionally test via `curl --resolve`
      to isolate DNS vs TCP/TLS.
- [ ] TCP 443 and 8443 establish, with proper TLS hostname verification.
- [ ] Tailnet HTTPS 443: API 401 without Bearer, 200 with Bearer.
- [ ] Tailnet HTTPS 8443: UI auth on, signup off, anonymous requests denied,
      positive login using safe credential handling.
- [ ] Native Tailscale SSH still works, `NETWORK_MODE=tailnet` uses
      zero published RunPod ports, and public RunPod proxies return 404.
- [ ] Exact-ID cleanup, no running charged Pods, final offline CI green.

Issue #20 remains a **PR #17 P0 merge blocker** until these checks pass.
