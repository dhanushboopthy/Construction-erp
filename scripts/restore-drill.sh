#!/usr/bin/env bash
# Monthly restore drill: prove the newest backup really brings the books back, without touching
# live data. Restores the newest dump (and files archive) into a scratch database and folder,
# runs the integrity check on it, then removes both.
#   ./scripts/restore-drill.sh            # newest backup
#   ./scripts/restore-drill.sh backups/erp-20261009-0230.dump
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose -f docker-compose.prod.yml)
dump="${1:-$(ls -1t backups/erp-2*.dump 2>/dev/null | head -1 || true)}"
[ -n "$dump" ] && [ -f "$dump" ] || { echo "FAIL: no backup found in backups/"; exit 1; }
files_archive="$(dirname "$dump")/$(basename "$dump" | sed 's/^erp-/erp-files-/; s/\.dump$/.tar.gz/')"
scratch="erp_drill_$(date +%s)"
started=$(date +%s)
result=FAIL

cleanup() {
  "${compose[@]}" exec -T db sh -c "dropdb --if-exists -U \"\$POSTGRES_USER\" $scratch" >/dev/null 2>&1 || true
  "${compose[@]}" exec -T backend rm -rf /tmp/drill-files >/dev/null 2>&1 || true
  mkdir -p backups
  echo "$(date -Is) $dump $result $(( $(date +%s) - started ))s" >> backups/restore-drills.log
}
trap cleanup EXIT

echo "Drill: restoring $dump into scratch database $scratch"
"${compose[@]}" exec -T db sh -c "createdb -U \"\$POSTGRES_USER\" $scratch"
"${compose[@]}" exec -T db sh -c "pg_restore --no-owner -U \"\$POSTGRES_USER\" -d $scratch" < "$dump"

"${compose[@]}" exec -T backend sh -c 'rm -rf /tmp/drill-files && mkdir -p /tmp/drill-files'
if [ -f "$files_archive" ]; then
  echo "Drill: restoring files from $files_archive"
  "${compose[@]}" exec -T backend tar -xzf - -C /tmp/drill-files < "$files_archive"
else
  echo "Drill: no files archive beside the dump; stored files will be reported as missing if any exist."
fi

echo "Drill: running the integrity check on the restored copy"
"${compose[@]}" exec -T backend sh -c \
  "DATABASE_URL=\$(echo \"\$DATABASE_URL\" | sed 's#/[^/]*\$#/$scratch#') STORAGE_DIR=/tmp/drill-files python -m app.scripts.verify --full"
result=PASS
echo "DRILL PASSED in $(( $(date +%s) - started ))s: $dump brings the books back."
