#!/usr/bin/env bash
# Replace the Blackkite database with a dump made by deploy/backup.sh.
#   deploy/restore.sh FILE --yes     run from the repository root
# Stops api, worker and proxy, drops and recreates the database, restores FILE,
# then starts the stack again (the api applies any newer migrations on start).
# DESTRUCTIVE: everything written since the dump is lost. Take a fresh dump first
# if the current database might still be needed.
# Environment: COMPOSE as for deploy/backup.sh.
set -euo pipefail
COMPOSE=${COMPOSE:-docker compose}
file=${1:-}
if [ -z "$file" ] || [ ! -f "$file" ] || [ "${2:-}" != "--yes" ]; then
  echo "usage: deploy/restore.sh FILE --yes   (replaces the current database)" >&2
  exit 2
fi
$COMPOSE exec -T db pg_restore --list < "$file" > /dev/null   # readable dump?
$COMPOSE stop proxy worker api
# shellcheck disable=SC2016  # expanded inside the db container
$COMPOSE exec -T db sh -c 'dropdb -U "$POSTGRES_USER" --if-exists --force "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
# shellcheck disable=SC2016
$COMPOSE exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error' < "$file"
$COMPOSE up -d --wait api worker proxy
echo "restored $file"
