# ADR 0011: Many companies in one database, picked by subdomain

**Status:** Accepted, Milestone 15. Supersedes [ADR 0004](0004-single-tenant-first.md).

**Context.** Duolink will sell the ERP to more construction-materials suppliers as a hosted
service. ADR 0004 put `tenant_id` on every table but fixed it to 1, so a second client needed its
own server. Running one stack per client does not scale, and a Duolink admin (Milestone 16)
needs to see every company in one place.

**Decision.**

- **One database, a `tenant` table.** Each company is a row (`slug`, `name`, `status`, `plan`,
  limits). Every business table's `tenant_id` is a foreign key to it with no default. Today's
  company is tenant 1 (slug `DEFAULT_TENANT_SLUG`, else `main`). Companies are never deleted, only
  suspended or cancelled, because their GST books must be kept.
- **The subdomain names the company.** `acme.<BASE_DOMAIN>` is the company `acme`. The backend
  reads `X-Forwarded-Host` (set by nginx) or `Host`. Any host outside `BASE_DOMAIN`, such as the
  bare domain or an IP address on a shop LAN, uses `DEFAULT_TENANT_SLUG`. That keeps single-shop
  installs working. On a SaaS server leave it blank. `admin` and a few other subdomains are
  reserved (`domain/tenancy.py`). Usernames stay unique only within a company.
- **The tenant lives on the session.** `get_tenant` (`api/deps.py`) resolves the company before
  any route runs and calls `set_tenant(db, id)`. Services filter every query on
  `current_tenant_id(db)` (`core/tenancy.py`). The signed-in user's token must belong to the same
  company as the address, and so must a refresh session.
- **The session guards writes.** A `before_flush` listener (`services/tenancy.py`) gives new rows
  the session's company. It refuses a row that names another company (`CrossTenantWriteError`)
  and a row saved with no company set (`NoTenantError`).
- **PostgreSQL enforces it too.** Row-level security with FORCE is on for every table with
  `tenant_id`. The policy `tenant_isolation` shows and accepts only rows whose `tenant_id` equals
  `app.tenant_id`, and each transaction sets that value from the session (`after_begin`). With no
  company set, no rows are visible. Superusers skip these policies, so the app's connections
  switch to the role `erp_app` (`DB_APP_ROLE`, created by migration 0024, no login and no
  superuser). Migrations keep running as the owner.
- **Closed companies stop.** A suspended or cancelled company gets 403 (`TENANT_SUSPENDED`,
  `TENANT_CANCELLED`) on every request, including sign-in and refresh.

**Consequences.**

- A forgotten filter cannot leak another company's rows: the database hides them. Tests run as
  `erp_app`, so they exercise the policies. `test_tenancy.py` fails if a table with `tenant_id`
  lacks the policy, or if a new table lacks `tenant_id`.
- Every new table needs `TenantMixin`, and its migration must enable and force row-level security
  and add the `tenant_isolation` policy (see migration 0024).
- Backups hold every company. Restoring one company alone needs a per-tenant export, which is not
  built yet.
- Each company needs a DNS name: a wildcard record `*.duolink.app` and a wildcard certificate.
- Indexes do not yet lead with `tenant_id`. Add them when one company's size slows another's
  queries.
