#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/uptime-monitor_${TIMESTAMP}.dump"

umask 077
mkdir -p "$BACKUP_DIR"

echo "Creating PostgreSQL backup..."

if ! docker compose exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$BACKUP_FILE"; then
  rm -f "$BACKUP_FILE"
  echo "ERROR: Backup failed." >&2
  exit 1
fi

if [ ! -s "$BACKUP_FILE" ]; then
  rm -f "$BACKUP_FILE"
  echo "ERROR: Backup file is empty." >&2
  exit 1
fi

if ! docker compose exec -T db pg_restore --list < "$BACKUP_FILE" >/dev/null; then
  rm -f "$BACKUP_FILE"
  echo "ERROR: Backup validation failed." >&2
  exit 1
fi

chmod 600 "$BACKUP_FILE"
echo "Backup created and validated: $BACKUP_FILE"
