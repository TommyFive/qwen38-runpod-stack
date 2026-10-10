#!/usr/bin/env bash
# Fresh Cloudzy 64GB Ubuntu VM only. Argument: immutable Git commit SHA.
set -Eeuo pipefail
umask 077
die() { echo "ERROR: $*" >&2; exit 1; }
[[ $# == 1 && "$1" =~ ^[a-f0-9]{40}$ ]] || die "Expected pinned 40-character Git SHA"
SHA="$1"
[[ $EUID == 0 && "$(uname -m)" == x86_64 ]] || die "Root on Linux AMD64 required"
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || die "Ubuntu Server 24.04 required"
[[ ! -e /opt/qwen38-cloudzy/.started ]] || die "Existing builder detected"
[[ ! -e /var/log/qwen38-cloudzy/buildkit.log ]] || die "Refusing existing build log"
mem_kib=$(awk '/^MemTotal:/{print $2}' /proc/meminfo)
((mem_kib >= 52*1024*1024)) || die "64GB class RAM required"
(( $(nproc) >= 8 )) || die "At least 8 vCPU required"
free_bytes=$(df -B1 --output=avail / | tail -1 | tr -d ' ')
((free_bytes >= 220*1024*1024*1024)) || die "At least 220GiB free SSD required"
printf 'Preflight OK: %d vCPU, %d GiB RAM, %d GiB free SSD\n' "$(nproc)" "$((mem_kib/1024/1024))" "$((free_bytes/1024/1024/1024))"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends ca-certificates curl gnupg git python3 jq
install -m 0755 -d /etc/apt/keyrings
curl -fsSL --retry 3 https://download.docker.com/linux/ubuntu/gpg | gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
arch=$(dpkg --print-architecture)
code=$(. /etc/os-release && echo "$VERSION_CODENAME")
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu %s stable\n' "$arch" "$code" >/etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y --no-install-recommends docker-ce docker-ce-cli containerd.io docker-buildx-plugin
systemctl enable --now docker
docker info >/dev/null
docker buildx version
install -m 0700 -d /opt/qwen38-cloudzy /var/log/qwen38-cloudzy
git clone --quiet --filter=blob:none https://github.com/TommyFive/qwen38-runpod-stack.git /opt/qwen38-cloudzy/repo
git -C /opt/qwen38-cloudzy/repo fetch --quiet --filter=blob:none origin "$SHA"
git -C /opt/qwen38-cloudzy/repo checkout --quiet --detach "$SHA"
[[ "$(git -C /opt/qwen38-cloudzy/repo rev-parse HEAD)" == "$SHA" ]] || die "Pinned checkout failed"
git -C /opt/qwen38-cloudzy/repo diff --quiet || die "Repo dirty"
root=/opt/qwen38-cloudzy/repo/images/sglang-qwen38
bash -n "$root/build-image.sh"
bash -n "$root/cloudzy/run-build.sh"
python3 -m py_compile "$root/cloudzy/observer.py"
python3 -m unittest discover -q -s "$root/tests" -p 'test_*.py'
cat >/opt/qwen38-cloudzy/buildkitd.toml <<'TOML'
[worker.oci]
  max-parallelism = 2
TOML
docker buildx create --name qwen38-cloudzy --driver docker-container --driver-opt memory=48g,memory-swap=56g --buildkitd-config /opt/qwen38-cloudzy/buildkitd.toml --use >/dev/null
docker buildx inspect qwen38-cloudzy --bootstrap >/dev/null
printf '%s\n' "$SHA" >/opt/qwen38-cloudzy/source.sha
chmod 0600 /opt/qwen38-cloudzy/source.sha
cat >/etc/systemd/system/qwen38-cloudzy-image.service <<'UNIT'
[Unit]
Description=Isolated Qwen38 SGLang candidate build (never auto-push)
After=docker.service network-online.target
Requires=docker.service
Wants=network-online.target
[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=/opt/qwen38-cloudzy/repo
ExecStart=/usr/bin/bash /opt/qwen38-cloudzy/repo/images/sglang-qwen38/cloudzy/run-build.sh
RemainAfterExit=yes
TimeoutStartSec=14400
KillMode=control-group
UMask=0077
Environment=BUILDKIT_PROGRESS=plain
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
touch /opt/qwen38-cloudzy/.started
chmod 0600 /opt/qwen38-cloudzy/.started
systemctl start --no-block qwen38-cloudzy-image.service
echo "LAUNCHED: qwen38-cloudzy-image; pinned SHA=$SHA"
echo "LOGS: /var/log/qwen38-cloudzy; journalctl -u qwen38-cloudzy-image"
echo "GUARD: no GHCR push, no RunPod pod, no VM deletion"
