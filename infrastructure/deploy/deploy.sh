#!/usr/bin/env bash
# Build and (re)start the stack from the current checkout. Safe to re-run for every update:
#   git pull && bash infrastructure/deploy/deploy.sh
# Migrations run automatically (the `migrate` service) before the backend starts.
set -euo pipefail
cd "$(dirname "$0")/../.."

COMPOSE=(docker compose -f infrastructure/deploy/compose.prod.yml --env-file infrastructure/deploy/.env)

test -s infrastructure/deploy/.env || { echo "infrastructure/deploy/.env is missing"; exit 1; }
grep -q '^DOMAIN=example.com' infrastructure/deploy/.env && { echo "Set DOMAIN in .env first"; exit 1; }

"${COMPOSE[@]}" build
"${COMPOSE[@]}" up -d --remove-orphans
"${COMPOSE[@]}" ps
echo
echo "Logs: ${COMPOSE[*]} logs -f --tail=100 backend worker voice caddy"
