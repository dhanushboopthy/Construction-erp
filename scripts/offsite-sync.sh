#!/usr/bin/env bash
# Copy backups off the machine and prove the copy arrived. Run daily from the host's cron, after
# the 02:30 backup (for example 03:30), with rclone set up for a remote (Google Drive, S3, ...):
#   30 3 * * *  cd /path/to/construction-erp && BACKUP_REMOTE=gdrive:erp-backups ./scripts/offsite-sync.sh
set -euo pipefail
cd "$(dirname "$0")/.."
remote="${BACKUP_REMOTE:?set BACKUP_REMOTE, for example gdrive:erp-backups}"
command -v rclone >/dev/null || { echo "rclone is not installed"; exit 1; }

# `copy`, not `sync`: a deleted local file must never delete the off-site copy.
rclone copy backups "$remote" --include 'erp-*.dump' --include 'erp-files-*.tar.gz' --include 'restore-drills.log'
rclone check backups "$remote" --include 'erp-*.dump' --include 'erp-files-*.tar.gz' --one-way

newest="$(ls -1t backups/erp-2*.dump | head -1)"
rclone lsf "$remote" | grep -qx "$(basename "$newest")" || { echo "FAIL: $newest is not at $remote"; exit 1; }
echo "OK: $(basename "$newest") is safe at $remote"
