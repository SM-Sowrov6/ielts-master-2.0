#!/usr/bin/env bash
# One-time Cloudflare Tunnel setup for compose.tunnel.yml (runs cloudflared in Docker; nothing to
# install). Usage, from the repository root:  bash infrastructure/deploy/tunnel-setup.sh ieltsmaster.site
# 1. prints a Cloudflare login URL — open it and authorise the domain;
# 2. creates tunnel "ielts-master" and points DOMAIN, www.DOMAIN and media.DOMAIN (MinIO) at it (CNAME, proxied);
# 3. writes infrastructure/deploy/cloudflared/config.yml. Credentials stay in that folder (git-ignored).
set -euo pipefail
export MSYS_NO_PATHCONV=1
DOMAIN="${1:?usage: tunnel-setup.sh DOMAIN}"
NAME=ielts-master
DIR="$(cd "$(dirname "$0")" && pwd)/cloudflared"
IMAGE=cloudflare/cloudflared:2026.10.1
mkdir -p "$DIR"
cf() { docker run --rm -i -v "$DIR:/home/nonroot/.cloudflared" "$IMAGE" "$@"; }

[ -f "$DIR/cert.pem" ] || cf tunnel login
if ! ls "$DIR"/*.json >/dev/null 2>&1; then cf tunnel create "$NAME"; fi
ID="$(basename "$(ls "$DIR"/*.json | head -1)" .json)"
cf tunnel route dns --overwrite-dns "$ID" "$DOMAIN"
cf tunnel route dns --overwrite-dns "$ID" "www.$DOMAIN"
cf tunnel route dns --overwrite-dns "$ID" "media.$DOMAIN"

cat > "$DIR/config.yml" <<EOF
tunnel: $ID
credentials-file: /etc/cloudflared/$ID.json
ingress:
  - hostname: $DOMAIN
    service: http://caddy:80
  - hostname: www.$DOMAIN
    service: http://caddy:80
  - hostname: media.$DOMAIN
    service: http://minio:9000
  - service: http_status:404
EOF
echo "Tunnel $ID ready for $DOMAIN (config: $DIR/config.yml)"
