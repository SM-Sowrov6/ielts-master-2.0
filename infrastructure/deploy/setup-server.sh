#!/usr/bin/env bash
# One-time server preparation for Oracle Cloud Always Free (Ubuntu 22.04/24.04, arm64 or amd64).
# Installs Docker, opens ports 80/443 in the host firewall, adds swap, and clones the repository.
#
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/infrastructure/deploy/setup-server.sh -o setup.sh
#   (private repo: copy the file over with scp instead)
#   bash setup.sh https://github.com/<owner>/<repo>.git
set -euo pipefail

REPO_URL="${1:?usage: setup-server.sh <git-repo-url>}"
APP_DIR="${APP_DIR:-$HOME/ielts-master}"

echo "==> Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi

echo "==> Host firewall: allow HTTP/HTTPS (Oracle images ship iptables rules that block them)"
for port in 80 443; do
  sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
    || sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport "$port" -j ACCEPT
done
sudo iptables -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null \
  || sudo iptables -I INPUT 6 -p udp --dport 443 -j ACCEPT
if command -v netfilter-persistent >/dev/null; then
  sudo netfilter-persistent save
else
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent
  sudo netfilter-persistent save
fi

echo "==> Swap (4 GB) for image builds"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 4G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> Repository"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cp -n "$APP_DIR/infrastructure/deploy/env.production.example" "$APP_DIR/infrastructure/deploy/.env"
chmod 600 "$APP_DIR/infrastructure/deploy/.env"
mkdir -p "$APP_DIR/infrastructure/deploy/backups"

cat <<EOF

Done. Next:
  1. Log out and back in (docker group), then: cd $APP_DIR
  2. Fill in infrastructure/deploy/.env   (nano infrastructure/deploy/.env)
  3. bash infrastructure/deploy/deploy.sh
EOF
