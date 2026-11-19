#!/usr/bin/env bash
# Nightly PostgreSQL dump (keep 14 days). Cron:  0 3 * * * bash ~/ielts-master/infrastructure/deploy/backup.sh
# Copy the dumps off the server too (e.g. to R2 with rclone) — a backup on the same disk is not a backup.
set -euo pipefail
cd "$(dirname "$0")"
COMPOSE=(docker compose -f compose.prod.yml --env-file .env)
stamp=$(date +%Y%m%d-%H%M)
"${COMPOSE[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "backups/ielts-$stamp.dump"
find backups -name 'ielts-*.dump' -mtime +14 -delete
echo "backups/ielts-$stamp.dump"
