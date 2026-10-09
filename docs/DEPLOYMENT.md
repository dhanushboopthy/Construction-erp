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

- The `backup` service writes `backups/erp-YYYYMMDD-0230.dump` nightly and keeps 30 days.
- **Copy `backups/` off the machine daily** (rclone to Google Drive or S3, or a USB disk rotated
  weekly). A backup on the same disk does not survive a dead disk.
- Restore drill monthly on a spare machine: `./scripts/restore.sh backups/<file>.dump`.
- Take a manual backup before every upgrade: `make prod-backup`.

## Upgrades

```bash
make prod-backup
git pull
make prod-up          # rebuilds images; migrations run on start
```

## Monitoring

- `GET /api/v1/health/ready` from an uptime checker (UptimeRobot or similar) every 5 minutes.
- `docker compose -f docker-compose.prod.yml logs -f backend` — JSON lines with request ids;
  users quote the request id shown in error messages.
- Watch disk space for `pgdata` and `backups/`.

## Uploaded files

Weighbridge slips and delivery proof are kept in `STORAGE_DIR` (the `files` volume in
`docker-compose.prod.yml`, `/data/files`). Include this volume in the off-machine backup together
with the database dump: the database only holds a record of each file. Milestone 14 adds the
restore drill for both.
