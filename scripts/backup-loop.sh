#!/bin/sh
# Nightly pg_dump into ./backups, keeping BACKUP_KEEP_DAYS days. Runs inside the backup container.
# Copy ./backups off the machine as well (see docs/DEPLOYMENT.md): a backup on the same disk
# does not survive a dead disk.
set -eu
KEEP="${BACKUP_KEEP_DAYS:-30}"
while true; do
  now=$(date +%H%M)
  if [ "$now" = "0230" ] || [ ! -f /backups/.first-run-done ]; then
    file="/backups/erp-$(date +%Y%m%d-%H%M).dump"
    echo "backup: writing $file"
    pg_dump --format=custom --file="$file.partial" && mv "$file.partial" "$file"
    find /backups -name 'erp-*.dump' -mtime +"$KEEP" -delete
    touch /backups/.first-run-done
    sleep 60
  fi
  sleep 30
done
