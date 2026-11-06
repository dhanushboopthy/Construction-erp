#!/bin/sh
# Nightly backup, inside the backup container (the backend image: it has pg_dump and the app).
#   erp-YYYYMMDD-HHMM.dump          the database (pg_dump, custom format)
#   erp-files-YYYYMMDD-HHMM.tar.gz  the uploaded slips and closing PDFs, when kept on a volume
# A dump is only kept after pg_restore can read it back. `.last-success` holds the time of the
# last good backup. The backup is copied off the machine by scripts/offsite-sync.sh: a backup on
# the same disk does not survive a dead disk.
# The time of day and how many daily, weekly and monthly copies to keep are set by a Super Admin
# on the Backups page (Milestone 25) and read through `python -m app.scripts.backup_schedule`.
# Every run is recorded there too, so the page lists nightly and manual backups together. If the
# application cannot be reached, the loop still backs up (at 02:30) and removes files older than
# BACKUP_KEEP_DAYS.
set -u
KEEP="${BACKUP_KEEP_DAYS:-30}"
DIR=/backups
CLI="python -m app.scripts.backup_schedule"
at="0230"
checked=0

refresh_time() {
  now_s=$(date +%s)
  if [ $((now_s - checked)) -ge 300 ]; then
    if t=$($CLI time 2>/dev/null) && [ -n "$t" ]; then at="$t"; fi
    checked=$now_s
  fi
}

backup_once() {
  stamp=$(date +%Y%m%d-%H%M)
  dump="$DIR/erp-$stamp.dump"
  files="$DIR/erp-files-$stamp.tar.gz"
  run_id=""
  if line=$($CLI start 2>/dev/null); then
    run_id=$(echo "$line" | cut -d' ' -f1)
    dump="$DIR/$(echo "$line" | cut -d' ' -f2)"
    files="$DIR/$(echo "$line" | cut -d' ' -f3)"
  fi
  echo "backup: writing $dump"
  if do_backup "$dump" "$files"; then
    [ -n "$run_id" ] && $CLI finish "$run_id" ok
    if [ -n "$run_id" ] && n=$($CLI prune 2>/dev/null); then
      echo "backup: pruned $n old copies"
    else
      find "$DIR" \( -name 'erp-*.dump' -o -name 'erp-files-*.tar.gz' \) -mtime +"$KEEP" -delete
    fi
    date -u +%s > "$DIR/.last-success"
    echo "backup: done $stamp"
    return 0
  fi
  [ -n "$run_id" ] && $CLI finish "$run_id" failed "the nightly dump or its check failed"
  return 1
}

do_backup() {
  dump="$1"
  files="$2"
  pg_dump --format=custom --file="$dump.partial" || return 1
  pg_restore --list "$dump.partial" >/dev/null || return 1
  if [ -d /files ]; then
    tar -czf "$files.partial" -C /files . || return 1
    tar -tzf "$files.partial" >/dev/null || return 1
    mv "$files.partial" "$files"
  fi
  mv "$dump.partial" "$dump"
}

while true; do
  refresh_time
  now=$(date +%H%M)
  if [ "$now" = "$at" ] || [ ! -f "$DIR/.first-run-done" ]; then
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
