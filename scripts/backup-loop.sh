#!/bin/sh
# Nightly backup, inside the backup container.
#   erp-YYYYMMDD-HHMM.dump          the database (pg_dump, custom format)
#   erp-files-YYYYMMDD-HHMM.tar.gz  the uploaded slips and closing PDFs, when kept on a volume
# A dump is only kept after pg_restore can read it back. Files older than BACKUP_KEEP_DAYS are
# removed. `.last-success` holds the time of the last good backup. The backup is copied off the
# machine by scripts/offsite-sync.sh: a backup on the same disk does not survive a dead disk.
set -u
KEEP="${BACKUP_KEEP_DAYS:-30}"
DIR=/backups

backup_once() {
  stamp=$(date +%Y%m%d-%H%M)
  dump="$DIR/erp-$stamp.dump"
  echo "backup: writing $dump"
  pg_dump --format=custom --file="$dump.partial" || return 1
  pg_restore --list "$dump.partial" >/dev/null || return 1
  mv "$dump.partial" "$dump"
  if [ -d /files ]; then
    tar -czf "$DIR/erp-files-$stamp.tar.gz.partial" -C /files . || return 1
    tar -tzf "$DIR/erp-files-$stamp.tar.gz.partial" >/dev/null || return 1
    mv "$DIR/erp-files-$stamp.tar.gz.partial" "$DIR/erp-files-$stamp.tar.gz"
  fi
  find "$DIR" \( -name 'erp-*.dump' -o -name 'erp-files-*.tar.gz' \) -mtime +"$KEEP" -delete
  date -u +%s > "$DIR/.last-success"
  echo "backup: done $stamp"
}

while true; do
  now=$(date +%H%M)
  if [ "$now" = "0230" ] || [ ! -f "$DIR/.first-run-done" ]; then
    if backup_once; then
      touch "$DIR/.first-run-done"
      sleep 60
    else
      echo "backup: FAILED, will try again in 10 minutes" >&2
      rm -f "$DIR"/*.partial
      sleep 600
    fi
  fi
  sleep 30
done
