#!/usr/bin/env bash
set -Eeuo pipefail

if [ "$#" -ne 3 ] || [ "$3" != "--confirm" ]; then
  echo "Usage: $0 <backup-file> <empty-target-database> --confirm" >&2
  exit 1
fi

BACKUP_FILE="$1"
TARGET_DB="$2"

if [ ! -f "$BACKUP_FILE" ] || [ ! -s "$BACKUP_FILE" ]; then
  echo "ERROR: Backup file missing or empty." >&2
  exit 1
fi

if [[ ! "$TARGET_DB" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  echo "ERROR: Invalid database name." >&2
  exit 1
fi

PRIMARY_DB="$(docker compose exec -T db sh -c 'printf "%s" "$POSTGRES_DB"')"

if [ "$TARGET_DB" = "$PRIMARY_DB" ]; then
  echo "ERROR: Restore into the primary database is prohibited." >&2
  exit 1
fi

echo "Validating backup archive..."
docker compose exec -T db pg_restore --list < "$BACKUP_FILE" >/dev/null

echo "Checking target database..."
TABLE_COUNT="$(
  docker compose exec -T db sh -c \
    'psql -U "$POSTGRES_USER" -d "$1" -tAqc "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('"'"'pg_catalog'"'"','"'"'information_schema'"'"')"' sh "$TARGET_DB"
)"

if [ "$TABLE_COUNT" != "0" ]; then
  echo "ERROR: Target database is not empty (user tables: $TABLE_COUNT)." >&2
  exit 1
fi

echo "Restoring into: $TARGET_DB"
docker compose exec -T db sh -c \
  'pg_restore --no-owner --no-privileges -U "$POSTGRES_USER" -d "$1"' \
  sh "$TARGET_DB" < "$BACKUP_FILE"

echo "Restore completed. Verify the restored database before using it."
