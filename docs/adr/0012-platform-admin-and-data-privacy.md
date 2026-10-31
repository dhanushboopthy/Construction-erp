# ADR 0012: A Duolink admin that sees counts, never the books

**Status:** Accepted, Milestone 16. Amended by [ADR 0013](0013-platform-admin-v2.md).

**Context.** With many companies on one server (ADR 0011), Duolink needs to onboard companies,
watch usage, help users who are locked out, and stop a company that does not pay. Companies trust
Duolink with their GST books, purchase costs and margins, so the admin must not become a way to
read them.

**Decision.**

- **Separate accounts.** Duolink admins are rows in `platform_admin`. They are not users of any
  company. They sign in with an email at `admin.<BASE_DOMAIN>/admin`. There is no sign-up: the
  first admin is created on the server (`python -m app.scripts.create_platform_admin`). Admins use
  the same password rules, lockout and rotating refresh sessions as company users, in their own
  tables (`platform_session`).
- **Separate tokens and address.** An admin token has type `platform` and a company token has
  type `access`, and each side refuses the other. `/api/v1/admin` answers 404 on any host except
  the admin subdomain. The admin refresh cookie is scoped to `/api/v1/admin/auth`.
- **Reading across companies is explicit.** Only `get_platform_admin` puts a session in platform
  mode (`set_platform`), which sets `app.platform = on` for its transactions. Migration 0025 adds
  a second, permissive policy, `platform_admin`, that shows rows of every company in that mode. A
  company request always clears platform mode (`get_tenant`).
- **Counts and statuses only.** Admin responses carry companies, users, sign-in events and
  counts: active users, shops, bills in the last 30 days, open sessions. They never carry an
  amount, a cost or a document's contents. `test_platform_admin.py` fails if any admin answer has
  a money-like field.
- **Support actions reuse the company's rules.** Deactivate, reactivate, unlock, reset a password
  and sign out everywhere all run through `services/users.py` on the user's own company, so "one
  active owner at least" and plan limits still hold. A reset makes a temporary password that is
  shown once.
- **Plans limit, never lock out.** Each plan (trial, basic, pro; `domain/plans.py`) limits active
  users and active shops and godowns, and a company may have its own limit. Adding beyond a limit
  answers 409 (`PLAN_USER_LIMIT`, `PLAN_LOCATION_LIMIT`). An ended trial is only flagged for the
  admin, because the company's books must stay reachable. Suspending a company is a deliberate
  act with a reason. It ends every session and blocks sign-in until the company is reactivated.
- **Everything an admin does is written down.** `platform_audit_log` is append-only (the trigger of
  migration 0003). It records every admin sign-in and every change, with the admin, the company,
  the user, details, IP and request id.

**Consequences.**

- An admin can see who uses the ERP and how much, but not what they sell or earn. If support needs
  more than that, it must come through the company's owner.
- A new admin feature must keep its response models free of money fields. The test enforces this.
- Billing (invoices for the plan) is not built. The plan is recorded and enforced; charging is done
  outside the ERP for now.
