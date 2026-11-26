#!/usr/bin/env bash
# Dump the Blackkite database to a timestamped file (pg_dump custom format).
#   deploy/backup.sh [DIR]          run from the repository root; DIR defaults to ./backups
# Environment:
#   COMPOSE              compose command (default "docker compose"; the local stack
#                        uses "docker compose -f docker-compose.yml -f docker-compose.local.yml")
#   BK_BACKUP_KEEP_DAYS  delete dumps older than this many days (default 14; 0 keeps all)
# The dump holds every user's profiles, notes and email address: keep DIR private
# (mode 700) and copy it off the VPS (docs/deploy.md, "Backups").
set -euo pipefail
COMPOSE=${COMPOSE:-docker compose}
dir=${1:-backups}
keep=${BK_BACKUP_KEEP_DAYS:-14}
umask 077
mkdir -p "$dir"
chmod 700 "$dir"
out="$dir/blackkite-$(date -u +%Y%m%dT%H%M%SZ).dump"
# shellcheck disable=SC2016  # expanded inside the db container
$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner' > "$out.partial"
# A dump that pg_restore cannot list is not a backup.
$COMPOSE exec -T db pg_restore --list < "$out.partial" > /dev/null
mv "$out.partial" "$out"
if [ "$keep" -gt 0 ]; then
  find "$dir" -maxdepth 1 -name 'blackkite-*.dump' -mtime +"$keep" -delete
fi
echo "$out ($(du -h "$out" | cut -f1))"
