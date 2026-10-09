#!/usr/bin/env bash
# Restore a backup into the production database. DESTRUCTIVE: replaces current data.
#   ./scripts/restore.sh backups/erp-20261009-0230.dump
set -euo pipefail
file="${1:?usage: restore.sh <backup.dump>}"
compose=(docker compose -f docker-compose.prod.yml)

read -r -p "This replaces ALL current data with $file. Type RESTORE to continue: " answer
[ "$answer" = "RESTORE" ] || { echo "Cancelled."; exit 1; }

"${compose[@]}" stop backend
"${compose[@]}" exec -T db sh -c 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$file"
"${compose[@]}" start backend
echo "Restored $file. Check the app, then tell staff to sign in again."
