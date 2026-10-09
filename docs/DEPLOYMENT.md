# Deployment (simple production)

One machine running Docker Compose: either a small server inside one shop (both shops reach it
over the network) or a small cloud VPS. No Kubernetes. Pick based on the shop's internet (G26):
a local server keeps billing working when the internet drops, but needs a VPN or LAN link for
the second shop and an off-site backup copy.

## First install

```bash
git clone https://github.com/dhanushboopthy/construction-erp.git && cd construction-erp
cp .env.example .env
# edit .env: APP_ENV=production, JWT_SECRET (48 random chars), POSTGRES_PASSWORD,
# COOKIE_SECURE=true, CORS_ORIGINS=[], SEED_* passwords
make prod-up
make prod-seed        # prints generated passwords once if SEED_* were not set
```

The app is on port 80 (`HTTP_PORT`). Migrations run when the backend starts.

## HTTPS

Passwords cross the network, so serve over HTTPS:

- **VPS with a domain:** put Caddy in front (`reverse_proxy localhost:80`); it gets certificates
  automatically.
- **Shop LAN:** use Tailscale on the server and counter PCs and `tailscale serve` for HTTPS, or
  Caddy with `tls internal` and install its root certificate on each PC.
- Plain HTTP on a LAN only as a stop-gap: set `ALLOW_INSECURE_COOKIES=true`, `COOKIE_SECURE=false`.

## Backups (G24)

- The `backup` service writes, nightly at 02:30, `backups/erp-YYYYMMDD-HHMM.dump` (the database)
  and `backups/erp-files-YYYYMMDD-HHMM.tar.gz` (uploaded slips and closing PDFs), keeps 30 days,
  and only keeps a dump after `pg_restore --list` can read it. `backups/.last-success` holds the
  time of the last good backup; Settings, System turns red when it is over 30 hours old.
- **Copy `backups/` off the machine daily.** `scripts/offsite-sync.sh` copies with rclone (Google
  Drive, S3, a USB-mounted folder...), never deletes remote files, and proves the newest dump
  arrived:
  `30 3 * * *  cd /path/to/construction-erp && BACKUP_REMOTE=gdrive:erp-backups ./scripts/offsite-sync.sh`
  A backup on the same disk does not survive a dead disk.
- **Restore drill every month:** `make prod-drill` restores the newest backup into a scratch
  database and folder, runs `python -m app.scripts.verify --full` on it and removes the scratch
  copy. It must print `DRILL PASSED`; results are appended to `backups/restore-drills.log`.
- Take a manual backup before every upgrade: `make prod-backup`.
- Real restore: `./scripts/restore.sh backups/<file>.dump` (database, files if the archive sits
  beside it, then the integrity check).

## Upgrades

```bash
make prod-backup
git pull
make prod-up          # rebuilds images; migrations run on start
```

## Monitoring

- `GET /api/v1/health/ready` from an uptime checker (UptimeRobot or similar) every 5 minutes.
- Settings, System (owner) shows the database version, last backup age, file storage, the
  e-way provider and shops that did not close yesterday; `make prod-verify` checks the books.
- `docker compose -f docker-compose.prod.yml logs -f backend` — JSON lines with request ids;
  users quote the request id shown in error messages.
- Watch disk space for `pgdata` and `backups/`.

## Uploaded files

Weighbridge slips and delivery proof are kept in `STORAGE_DIR` (the `files` volume in
`docker-compose.prod.yml`, `/data/files`). Include this volume in the off-machine backup together
with the database dump: the database only holds a record of each file. The restore drill checks both.

## Cloud storage for closing PDFs and slips

Set `STORAGE_PROVIDER=s3` with `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` and, for
anything other than AWS, `S3_ENDPOINT_URL` (Cloudflare R2, Backblaze B2, Wasabi and MinIO all
work). Slips and closing PDFs then go to the bucket instead of the `files` volume; keep bucket
versioning on. The owner has not chosen a provider yet (GAP_ANALYSIS open question).

## Production checklist

- `APP_ENV=production`, `JWT_SECRET` (48 random characters), `COOKIE_SECURE=true` behind HTTPS,
  `POSTGRES_PASSWORD`, `SEED_*` passwords, `ENABLE_API_DOCS=false` (the compose file sets it).
- `GSP_PROVIDER=sandbox` or `live` with the provider's keys before the first e-way bill; the pretend
  provider is refused in production.
- `STORAGE_PROVIDER=s3` and its `S3_*` variables if closing PDFs should go to a bucket.
- `BACKUP_DIR` is set by the compose file so the System page can see the backups.
- Run `make prod-verify FULL=1` and `make prod-drill` before Day 0 ([GO_LIVE](GO_LIVE.md)).
