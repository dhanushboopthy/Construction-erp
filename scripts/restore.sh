#!/usr/bin/env bash
# Restore a backup into the production database and files. DESTRUCTIVE: replaces current data.
#   ./scripts/restore.sh backups/erp-20261009-0230.dump
# If backups/erp-files-20261009-0230.tar.gz exists beside it, the uploaded files are restored too.
set -euo pipefail
file="${1:?usage: restore.sh <backup.dump>}"
[ -f "$file" ] || { echo "No such file: $file"; exit 1; }
files_archive="$(dirname "$file")/$(basename "$file" | sed 's/^erp-/erp-files-/; s/\.dump$/.tar.gz/')"
compose=(docker compose -f docker-compose.prod.yml)

read -r -p "This replaces ALL current data with $file. Type RESTORE to continue: " answer
[ "$answer" = "RESTORE" ] || { echo "Cancelled."; exit 1; }

"${compose[@]}" stop backend
"${compose[@]}" exec -T db sh -c 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$file"
if [ -f "$files_archive" ]; then
  "${compose[@]}" run --rm --no-deps -T backend sh -c 'rm -rf /data/files/* && tar -xzf - -C /data/files' < "$files_archive"
  echo "Restored uploaded files from $files_archive."
else
  echo "No files archive beside the dump ($files_archive): uploaded files were left as they are."
fi
"${compose[@]}" start backend
"${compose[@]}" exec -T backend python -m app.scripts.verify || echo "WARNING: the integrity check reported a problem. Read it above."
echo "Restored $file. Check the app, then tell staff to sign in again."
