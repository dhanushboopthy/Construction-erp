# Runbook

What to do, and who does it, when the system is running at the shops. Written for the owner and
whoever looks after the server. Commands run in the project folder on the server.

## Every day

| When | Who | What |
| --- | --- | --- |
| Closing time | Counter staff | Reports, Daily closing: count the drawer, write a note if it is short or over, **Close the day**. The PDF is saved; bills for that day are now locked. |
| Morning | Owner | Open Settings, System. Every row should say *Good*. *Needs action* on the backup row means last night's backup did not run (see below). A shop listed as "not closed yesterday" needs its day closed. |

## Every week

- Reports, Dues: send reminders for the oldest customer bills.
- Stock counts at the godown (Stock, Counts); post the count so differences become adjustments.
- Check the disk: `df -h` on the server. Keep 20% free for `pgdata/`, `backups/` and the files volume.

## Every month

1. **Restore drill:** `make prod-drill`. It restores the newest backup into a scratch database,
   runs the integrity check and deletes the scratch copy. It must end with `DRILL PASSED`. The
   result is added to `backups/restore-drills.log`.
2. **Integrity check on live data:** `make prod-verify FULL=1` (or Settings, System, *Check the
   books and every stored file*). Every line must be `OK`.
3. **GST month end** (accountant): Reports, GST returns, pick the month. Upload the GSTR-2B from
   the portal and clear every *amounts differ* and *in 2B, not in our books* line with the
   supplier. Download GSTR-1 (Excel for review, JSON for the portal). Check that *Documents
   issued* shows no missing numbers.
4. Confirm the **off-site copy** is current: `BACKUP_REMOTE=... ./scripts/offsite-sync.sh`.

## Something went wrong

### The backup row says "Needs action"

1. `docker compose -f docker-compose.prod.yml logs --tail=50 backup`. A line `backup: FAILED` says
   which step broke (usually the disk is full).
2. Free disk space, then `make prod-backup` to take one now.
3. Run `make prod-verify`. Restart the service with `docker compose -f docker-compose.prod.yml
   restart backup`.

### The books check says something does not add up

Do not close the month. Do not edit the database by hand: the database refuses edits to bills,
notes, purchases and payments on purpose. Send the list shown to support. If a bad restore or
upgrade is the cause, restore the last good backup (below) and re-enter the day's documents.

### Restore a backup (data loss, a bad upgrade, a stolen machine)

1. New machine: install Docker, copy the project folder and `.env`, `make prod-up`.
2. Copy the newest `erp-YYYYMMDD-HHMM.dump` and `erp-files-YYYYMMDD-HHMM.tar.gz` from the off-site
   copy into `backups/`.
3. `./scripts/restore.sh backups/erp-YYYYMMDD-HHMM.dump`. Type `RESTORE`. The script restores the
   database and the files, restarts the app and runs the integrity check.
4. Everything entered after that backup (up to a day) must be entered again from paper or from
   staff's memory. Ask staff to sign in again.

### A day was closed by mistake, or a bill was forgotten

The owner opens Reports, Daily closing, **Reopen** next to the day, and writes why. The change is
recorded. Make the entry, then close the day again with the cash count.

### A bill is wrong

Never delete or edit it (the database would refuse). Make a **credit note** for the wrong part
(Sales bills, open the bill, Return goods) and a new correct bill. A wrong supplier bill is
corrected with a **debit note** (Purchases, Return to supplier).

### The e-way bill provider is down

The bill still saves. On the bill, try again in a few minutes. If the provider stays down, make the
e-way bill on the government portal by hand and type its number on the bill ("The portal made it by
hand? Enter the number"). If it says no provider is set, `GSP_PROVIDER` and the provider keys are
missing from `.env` (see DEPLOYMENT).

### Someone forgot their password or PIN

Owner: Settings, Users, reset password. A forgotten **owner** password is reset from the server
(access to the server is the proof of ownership):
`docker compose -f docker-compose.prod.yml exec backend python -m app.scripts.reset_password owner`.
It prints a new random password once, ends the user's other sign-ins and clears any lockout.
Approval PIN: Settings, Approval PIN (needs the owner's password).

### The internet is down

With the server inside a shop, billing carries on inside that shop's network. The e-way bill and
IRN steps wait: finish them when the line returns (Sales bills shows "still without an e-way
bill"). With a cloud server, use the e-way bill portal on a phone and type the numbers in later.

### A staff member leaves

Settings, Users, switch the account off. Their sign-ins end at once; their past work stays
attributed to them in the audit log.

## Upgrades

1. `make prod-backup`, then `make prod-verify`.
2. `git pull && make prod-up` (migrations run on start).
3. Settings, System: all rows *Good*; sign in as owner and counter and make a test bill in a
   non-production copy first when the release notes say so (CHANGELOG).
4. If something is wrong, restore the backup taken in step 1.

## Numbers to remember

| What | Where |
| --- | --- |
| Backups | `backups/`, nightly at 02:30, kept 30 days; copied off-site daily |
| Uploaded files | the `files` Docker volume, inside every backup (`erp-files-*.tar.gz`) |
| Logs | `docker compose -f docker-compose.prod.yml logs -f backend` (JSON, one line per request) |
| Health check for an uptime service | `GET /api/v1/health/ready` |
| Tests that guard the rules | `make test`; CI runs them on every change |
