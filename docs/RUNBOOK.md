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

## Duolink admin (admin.duolink.app/admin)

- **First admin:** on the server, `docker compose -f docker-compose.prod.yml exec -e
  PLATFORM_ADMIN_PASSWORD=... backend python -m app.scripts.create_platform_admin
  you@duolink.app "Your Name"`. Without the variable, a password is printed once. It creates a
  Super Admin; add `--role support` for a read-only account.
- **Two roles:** a Super Admin changes companies, users and staff. Support only reads. Keep the
  Super Admins few. Add everyone else on the Staff page (Super Admin only) with a temporary
  password; they must choose their own at the first sign-in.
- **A staff member forgot their password or is locked out:** Staff, open them, Reset password (a
  temporary password, shown once) or Unlock. If the only Super Admin is locked out, run
  `create_platform_admin` on the server for a second Super Admin, then unlock the first.
- **A staff member leaves:** Staff, open them, Deactivate. They are signed out at once. The last
  active Super Admin cannot be deactivated, so promote a replacement first.
- **A new company:** Companies, Add company (Super Admin). One form does it all: the company name
  and code (its address), state and city; the seller details that print on bills (name on bills and
  GSTIN, both optional); the first shop's name and code (a godown is added too); the plan, and
  either a trial length (1 to 90 days, 14 if blank) or "Active, no trial"; and the first owner's
  name, username, email, mobile and password. Tick "Make them choose a new password" only if you
  are sending the password by message; by default an owner gets a working password. When it is
  saved the page shows the owner's sign-in address.
- **Find a company:** Companies searches the name, the code, the owner's name or email and the
  GSTIN. Filter by status, plan, trial state or "ending within 30 days"; sort by name, joined, last
  activity or users. "Last activity" is the last request from anyone there, to the minute.
- **The company's page** (Companies, then the name) has tabs: Overview (contact, seller details,
  logo, status), Users, Subscription (plan and limits), Usage (counts only) and Activity (sign-ins
  and what admins did there). Support can open every tab and change nothing.
- **A company cannot get into its own Settings but its GSTIN or bill details are wrong:** open the
  company, Overview, Seller details on bills, change the field and write the reason. The change is
  checked as the company's own form is, and recorded in both audit logs. Do not use this to change
  what a company sells or owes; there is no way to, by design.
- **A company has left:** Overview, Status, write the reason and Close company. Everyone is signed
  out and nobody can sign in. The data is kept. To reopen it, write the reason and Reopen company.
- **Find a user:** Users searches the name, username and company; filter by company, role, status
  (active, deactivated, locked out, never signed in). "Show removed" includes removed accounts.
- **A user is locked out or forgot their password:** Users, find them, then use Unlock or Reset
  password. A reset shows a temporary password once, with a Copy button. Read it out to them. All
  their sessions end, and at the next sign-in they must choose their own password before anything
  else opens. The temporary password cannot be shown again; reset again if it is lost.
- **A user's name, mobile, username or role is wrong:** open them, Edit user, write the reason. A
  username must be free in that company. You cannot make the last active owner anything else.
- **A phone or PC was lost or shared:** open the user, "Signed in on" lists each device and
  address; End signs out that one device only. Sign out everywhere ends them all.
- **Someone has left the company:** open the user, Remove access, type their username and write the
  reason. They are switched off, signed out and hidden from the owner's user list. Their account
  is never deleted, so their name stays on the bills they made. The last active owner cannot be
  removed: make another person an owner first. A removed account cannot be brought back from the
  admin; add the person again with a new username if they return.
- **A company does not pay:** open the company, write the reason, then Suspend company and
  confirm. Everyone there is signed out. Reactivate company undoes it. Nothing is deleted.
- **Trials:** the overview lists trials ending this week. Change the plan, or move the trial end, on
  the company's page.
- **Who did what:** Activity shows sign-ins at every company, and every admin action is listed
  under "What Duolink admins did".

## Several companies on one server

The scripts work for one company at a time. Without `--tenant` they use the default company:

- `python -m app.scripts.seed --tenant acme` sets up a new company (or completes one).
- `python -m app.scripts.verify --tenant acme [--full]` checks one company's books.
- `python -m app.scripts.reset_password owner --tenant acme` resets a password.

Backups and restores cover **every company at once**. Restoring a backup puts every company back
to that night. A per-company export and restore is not built yet, so think before restoring a
shared server for one company's mistake.

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
