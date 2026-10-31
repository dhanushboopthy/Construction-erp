# Handoff: Duolink super admin, milestones 17 to 30

This is the brief for a Claude Code session (Sonnet) that brings the Duolink super admin of the
construction ERP up to what the WA project (Duolink AlignSuite) already has. WA's behaviour is
copied into `docs/reference/WA_SUPER_ADMIN.md`; the WA code is not in this repository. Milestone
16 built a small admin: companies, users across companies, sign-in activity, plans and limits.
Read this whole file before you start, then build the milestones in order, one branch and one
pull request each.

## 1. Goal

Duolink staff run every company from `admin.<BASE_DOMAIN>/admin`. They need to:

- onboard companies;
- sell plans and record renewals;
- support users;
- answer tickets;
- watch the platform;
- back up and restore companies;
- manage shared integrations and bill designs;
- with the owner's consent, look inside a company to help it.

The WA project is the reference for behaviour and screens. **Do not copy its code.** WA is C#
and Tailwind, while this repo is FastAPI, SQLAlchemy, React and CSS Modules. Copy what it does,
and build it the way this repo builds everything else.

## 2. Decisions already taken by the owner (do not reopen them)

| Topic | Decision |
| --- | --- |
| Looking inside a company | **Owner-granted support access.** The company owner turns access on for a set time, then a Super Admin can enter the company **read-only**, under a banner, with everything audited. The owner can revoke it at any time. There is no access without a live grant. (M23) |
| Company data deletion and numbering | **As WA.** A Super Admin can delete selected kinds of a company's business data, or all of it, and can set or reset document numbering (back to 1 once a series is empty). Guarded by typed confirmations, a preview, a safety backup and the audit log. (M26) |
| Charging companies | **Manual first, Razorpay last.** Plans with prices, subscriptions, manual renewals with payment records and a Duolink revenue dashboard. When a paid subscription expires, the company becomes **read-only**: it can still read and export its books but cannot write. Razorpay online renewal is the last, optional milestone. (M20, M21, M30) |
| Extras in scope | Per-company backup and restore, GSP / GSTIN-lookup API admin, bill templates per company, a PWA with "force update". (M25, M27, M28, M29) |
| Always included | Platform staff roles (Super Admin, read-only Support), company profile editing, user support tools, support tickets, system health, notifications bell, maintenance mode, audit log with filters. |

These decisions change ADR 0012, so **M17 starts by writing ADR 0013** (section 7). Every later
milestone points to it.

### Rules that stay exactly as they are

- **Row-level security** stays on every tenant table (ADR 0011).
- **Money** is `Decimal` and `NUMERIC`.
- **Cost and margin never reach non-owner roles.** That includes Duolink support inside a
  company, unless the owner ticks "show cost and margin" on the grant (M23).

## 3. Read first

1. `CLAUDE.md`: stack, layout, hard rules, commands.
2. `docs/adr/0011-multi-tenant-saas-by-subdomain.md` and
   `docs/adr/0012-platform-admin-and-data-privacy.md`.
3. `docs/ROADMAP.md`, the "SaaS milestones" table. **In M17, add rows 17 to 30 from section 6
   of this file**, so `/milestone <n>` works.
4. `docs/SPEC.md`, the M15 and M16 sections: the level of detail expected for each new section.
5. The M16 code, as the pattern to copy:
   - **API:** `backend/app/api/v1/admin/{auth,tenants,users,monitoring}.py` and
     `backend/app/api/deps.py` (`get_platform_admin`, `get_tenant`).
   - **Services:** `backend/app/services/platform/{auth,tenants,users,monitoring,audit}.py`.
   - **Models:** `backend/app/models/{tenancy,platform}.py`.
   - **Domain:** `backend/app/domain/plans.py`.
   - **Schemas:** `backend/app/schemas/platform.py`.
   - **Migrations:** `0024` (row-level security) and `0025` (platform admins, the
     `platform_admin` policy, the append-only trigger on `platform_audit_log`).
   - **Tests:** `backend/tests/integration/test_platform_admin.py` (including
     `test_no_admin_answer_carries_money`) and `test_tenancy.py`.
   - **Frontend:** `frontend/src/admin/` (`AdminApp.tsx`, `AdminShell.tsx`, `pages/*`, `api.ts`,
     `client.ts`).
6. **The WA reference: `docs/reference/WA_SUPER_ADMIN.md`.** Read it in full before M17, and
   re-read the sections named in each milestone. It holds:
   - the roles and the full admin API surface, with request rules (sections 1 and 2);
   - the bell, maintenance mode, force update and GST API (sections 3 to 6);
   - Razorpay renewal, "Login as Company", data management, numbering, backups and bill
     templates, copied from WA's README (sections 7 to 12).

   The WA class and screen names in the "WA reference" lines below (`AdminController.cs`,
   `Plans.tsx` and so on) are pointers into that file. The WA code itself is not in this
   repository, so do not look for it. If a sibling checkout `../WA` happens to exist, you may
   read it, but nothing depends on it.

## 4. Start of session, environment, git

Follow sections 3, 4 and 5 of `docs/prompts/FINANCE_FM3_FM10.md` exactly. They cover:

- the environment (Docker, or native Postgres 17, uv and **Node 22**);
- the full green check before any change;
- git authorship (`dhanushboopthy <dhanushbopathy@gmail.com>` only, **no Claude attribution
  anywhere**, never push to `main`, never force-push, never merge).

Then, for each milestone:

- **Branch** `feat/m<n>-<short-name>` from `origin/main`, or from the previous milestone's
  branch if that one is not merged yet: migrations chain.
- **Migrations:** the head today is `0029`. M17's migration is `0030`; number on from there.
- **PR title:** `M<n>: <milestone name>`.
- **PR body:** the first line is `M<n> done, <X> backend + <Y> frontend tests pass.`, or
  `Blocked on <reason>`. Then write:
  - what changed for Duolink staff and for companies, in plain words;
  - the acceptance criteria and the test that proves each one;
  - decisions taken, with their defaults;
  - what was deferred and why.

## 5. Rules for every milestone

1. **Tenancy.**
   - Every new company-owned table has `tenant_id` (`TenantMixin`). Its migration enables and
     forces row-level security and adds the `tenant_isolation` policy (copy 0024) **and** the
     `platform_admin` policy (copy 0025).
   - Platform-only tables (no company owns the row, e.g. `platform_plan`) carry no `tenant_id`.
     List them in the exclusion set in `test_tenancy.py` with a comment saying why.
   - Only `services/platform/` reads across companies.
2. **Two kinds of platform admin** (from M17): `super_admin` and `support`. Every new write
   endpoint uses `SuperAdminOnly` unless the milestone says Support may do it. Test each write
   endpoint as a Support admin and expect 403.
3. **Money in admin answers.**
   - Duolink's own revenue (plan prices, subscription payments) may appear only under
     `/api/v1/admin/billing/...`.
   - A company's money (bills, costs, balances) may appear **only** inside an owner-granted
     support session (M23), and never through `/api/v1/admin`.
   - Extend `test_no_admin_answer_carries_money` with an explicit allow-list of billing paths.
     Every other admin path must still fail on a money-like field.
4. **Everything an admin does is audited** in `platform_audit_log`. Add each new action to
   `PlatformAction` and widen the CHECK by hand in the migration (see section 9). Include the
   admin, the company, the target, the reason and the request id. Never put a password, token
   or API key in `details`; test it.
5. **Typed confirmations are checked on the server**, not only in the dialog:
   - `RESTORE` for restores;
   - `DELETE` for deletions;
   - the company's exact name for "delete everything";
   - the user's username for removing access.

   Compare them case-sensitively.
6. **Business maths and lifecycle rules go in `backend/app/domain/`**, unit tests first:
   subscription periods, access state, plan limits, the numbering floor, the deletion order,
   template placeholder parsing. No DB, HTTP or clock there; pass `now` or `today` in. CI
   requires 100% domain coverage.
7. **Each PR includes:**
   - the migration;
   - tests (unit first, then integration, then frontend);
   - `docs/SPEC.md` (a "Built (M<n> ...)" section);
   - `docs/ROADMAP.md` (mark the milestone **Done** with its branch);
   - `CHANGELOG.md` (the next minor version);
   - `docs/API.md` (an "Endpoints (M<n> ...)" table with the admin role and error codes);
   - `docs/RUNBOOK.md` wherever an operator procedure changes;
   - `docs/ERP_GUIDE.md` wherever company users see something new.
8. **UI.** Follow `docs/DESIGN.md` and use the `frontend-design`, `ui-ux-pro-max` or `impeccable`
   skill for new screens.
   - Use tokens only, never raw hex. Support light and dark. Keyboard first. Use tabular
     numbers.
   - Admin screens live in `frontend/src/admin/`. Company-side screens live in
     `frontend/src/pages/`.
   - Every destructive dialog shows a live preview fetched when it opens, not cached from
     earlier.
9. **If something is truly Duolink's or the owner's decision and blocks a milestone**, stop and
   write `Blocked on <reason>` rather than guessing.

## 6. Milestones

Each milestone below has:

- **Goal**;
- **WA reference**;
- **Tasks** (numbered, with subtasks);
- **Acceptance criteria**: each line must be proven by a named test, or by a manual check
  written up in the PR.

---

### M17: Foundation (ADR 0013, platform roles, platform staff)

**Goal.** Record the owner's decisions and split Duolink staff into Super Admin and read-only
Support.

**WA reference.** `PlatformRole` (`SUPER_ADMIN`, `PLATFORM_SUPPORT`), `[RequireSuperAdmin]`,
`/api/admin/users/platform`, `web/src/pages/admin/Users.tsx` (the "Platform staff" half).

**Tasks.**

1. **ADR 0013**, "Platform admin v2: roles, owner-granted access, Duolink billing, data
   management". Write it as section 7 below says. Mark ADR 0012 "Amended by ADR 0013" in its
   status line, and change nothing else in ADR 0012.
2. **ROADMAP.** Add rows 17 to 30 (from this section) to "SaaS milestones", status "Planned".
3. **Roles model.**
   1. Add `PlatformRole` (`super_admin`, `support`) to `models/enums.py`.
   2. Add `platform_admin.role` (default `support`), plus `mobile` and `must_change_password`.
   3. Migration 0030: give existing admins `super_admin`, and widen `platform_action`.
   4. The token carries the role. `PlatformPrincipal` exposes `is_super_admin`.
   5. Add a `SuperAdminOnly` dependency in `api/deps.py`, and apply it to every existing write
      route in `api/v1/admin/` (tenant create, update, suspend, reactivate; user deactivate,
      activate, unlock, reset password, sign out). Support keeps every read.
4. **Platform staff API** (`/api/v1/admin/staff`, Super Admin only):
   - list;
   - create (name, email, mobile, password, role; default role `support`);
   - update (name, mobile, role, active);
   - reset password (must change on next sign-in);
   - unlock;
   - sign out everywhere.
   Two guards:
   - An admin cannot demote or deactivate themselves.
   - The last active Super Admin cannot be demoted or deactivated (409 `LAST_SUPER_ADMIN`).
5. **Forced password change.** An admin with `must_change_password` can call only `/auth/me`,
   `/auth/change-password` and `/auth/logout` until they change it (403
   `PASSWORD_CHANGE_REQUIRED`). The admin UI routes them to a change-password screen.
6. **Admin UI.**
   1. Add a "Staff" page: a table, a create dialog, and row actions.
   2. Hide write buttons from Support (a courtesy only: the server enforces).
   3. Show the role badge in `AdminShell`.
7. **`create_platform_admin` script:** add `--role`, default `super_admin` (it creates the first
   admin).

**Acceptance criteria.**

- A Support admin gets 403 on every write route in `/api/v1/admin` and 200 on every read
  (a parametrised test over the router's routes, so a new route cannot be forgotten).
- Demoting the last Super Admin answers 409 `LAST_SUPER_ADMIN`. Self-deactivation answers 409.
- A new staff member created with a temporary password must change it before any other call.
- Every staff change writes a `platform_audit_log` row naming the admin and the target, with no
  password in `details`.
- ADR 0013 exists, ADR 0012 links to it, and ROADMAP lists M17 to M30.

---

### M18: Company profile, onboarding and the company page

**Goal.** Duolink can record and correct who a company is, onboard it fully in one form, and see
it on one page with tabs that later milestones fill in.

**WA reference.**

- `CreateCompanyRequest` and `UpdateCompanyRequest` in `AdminController.cs`.
- `POST /companies/{id}/logo`.
- `Companies.tsx` and `CompanyDetail.tsx` (tabs: overview, users, subscription, usage, activity,
  numbering, backup, data, invoiceTemplates, support).

**Tasks.**

1. **Contact fields on `tenant`** (Duolink's own record of its customer):
   - `owner_name`, `owner_email`, `owner_mobile`;
   - `city`, `state_code`;
   - `notes` (internal, Super Admin and Support only);
   - `last_activity_at` (updated at most once a minute by the company request path; cheap).
2. **Seller details stay in `shop_settings`** (`legal_name`, `gstin` and the rest). The admin
   may correct them for a company that cannot get into its own settings.
   1. Add `PATCH /api/v1/admin/tenants/{id}/seller-details` (Super Admin) for legal name,
      GSTIN, PAN, address, state code and CIN. Validate them as the company form does.
   2. It writes through the same service the company's settings screen uses, inside that
      company's tenant context. It writes the company's own `audit_log` row (actor: "Duolink:
      <admin name>") **and** a `platform_audit_log` row with old and new values.
   3. Add CIN to `shop_settings` if it is missing (R7 noted "no CIN yet"), and print it on the
      bill where the layout has a slot.
3. **Onboarding form.** Extend `POST /tenants` with:
   - the owner's contact details;
   - the seller details (legal name, GSTIN, state code);
   - the first shop's name and code;
   - the plan;
   - trial length (days) or "start active";
   - `require_owner_password_change` (default false, as WA).
   The whole form is one transaction. On success it returns the company's sign-in address.
4. **Logo from the admin:** `POST` and `DELETE /api/v1/admin/tenants/{id}/logo` through
   `services/tenant_logo.py` (same checks, PNG/SVG rules), run in the company's tenant
   context. Super Admin only.
5. **Company list:**
   - search (name, slug, owner, GSTIN);
   - filters (status, plan, trial state, expiring within 30 days);
   - sorting (created, last activity, users);
   - pagination (`Page[...]`).
6. **Company page tabs** at `/admin/companies/:id`:
   - Overview;
   - Users;
   - Subscription;
   - Usage (counts only: users, shops, bills in 7/30/90 days, purchases in 30 days, storage
     used by attachments);
   - Activity (sign-ins and admin actions on this company).
   Tabs that later milestones add (Numbering, Backups, Data, Bill design, Support, Access) are
   registered in a single list, so each later milestone only adds an entry.
7. **Status changes:** keep suspend and reactivate, and add **cancel** (status `cancelled`,
   reason required, every session ended). A cancelled company's data is kept. Reactivating a
   cancelled company is Super Admin only and needs a reason.

**Acceptance criteria.**

- A Super Admin onboards a company in one form. Its owner signs in at `<slug>.localhost` and
  sees the seller details and first shop already set.
- Correcting a GSTIN from the admin shows in the company's own audit log as done by Duolink,
  and in the platform audit log with old and new values.
- Support can open every tab but sees no edit, logo or status buttons, and the API refuses them.
- The Usage tab and every company list answer pass the money-field test.
- Search finds a company by GSTIN. Filters and pagination are covered by a test.

---

### M19: User support tools

**Goal.** Support can fix a locked-out or wrongly set up user without the owner's help.

**WA reference.** `PATCH /companies/{id}/users/{userId}`, `reset-password`,
`DELETE /companies/{id}/users/{userId}`, `Users.tsx` ("company users" directory),
`SessionsController`.

**Tasks.**

1. **Directory.** `GET /api/v1/admin/users` gains:
   - search (username, full name, company);
   - filters (company, role, active, locked, never signed in);
   - pagination.
2. **Edit user** (Super Admin): full name, mobile, and username (unique within the company,
   409 `USERNAME_TAKEN`). Role changes go through `services/users.py`, so "at least one active
   owner" and plan limits still hold. Reason required.
3. **Reset password.** As M16, plus a `must_change_password` flag on `app_user`, if it is
   missing, which the company login honours. The reset ends every session of that user.
4. **Sessions.** Add `GET /api/v1/admin/users/{id}/sessions`, which lists device, IP, created
   and last used, and `DELETE .../sessions/{session_id}` to revoke one.
5. **Remove access** (WA "delete user"). Users are referenced by `ActorMixin` on every document,
   so a user row is **never deleted**.
   - "Remove" deactivates the user, ends every session and marks the account `removed_at`;
     the user is hidden from the company's user list by default.
   - It needs the typed username (rule 5).
   - The last active owner cannot be removed.
6. **Admin UI:** a user drawer with details, sessions, and actions. Show the temporary password
   once, with a copy button.

**Acceptance criteria.**

- A reset password works once and forces a change at the next sign-in. Old sessions are gone.
- Removing the last active owner answers 409. Removing a counter user keeps every bill they
  issued, still showing their name.
- Support gets 403 on every action and 200 on the directory and the sessions list.
- Each action is in the platform audit log and in the company's own audit log.

---

### M20: Plans and pricing catalogue

**Goal.** Duolink edits what it sells without a code change.

**WA reference.** `Plan` and `PlanPrice` in `Domain/Entities/Platform.cs`; `PlanRequest`,
`/api/admin/plans` (create, update, duplicate, delete); `Plans.tsx`.

**Tasks.**

1. **Tables** (platform-only, no `tenant_id`):
   - `platform_plan`: code (unique, upper snake case), name, short and long description,
     `max_users`, `max_locations`, `features` (JSONB list of feature codes), `is_active`,
     `is_popular`, `sort_order`;
   - `platform_plan_price`: plan, `duration_value`, `duration_unit` (day, month, year), price
     (`NUMERIC(12,2)`), currency `INR`, `is_active`, `sort_order`.
2. **Migration.**
   1. Seed `TRIAL`, `BASIC` and `PRO` from today's `domain/plans.PLANS`.
   2. Replace `tenant.plan` (enum) with `tenant.plan_id` (FK), mapping existing rows.
   3. Keep `max_users` and `max_locations` on `tenant` as company overrides.
3. **Domain.**
   1. `domain/plans.py` keeps the pure rules (`limits_for`, `can_add`, trial state) but takes a
      `PlanLimits` value instead of a code.
   2. Add a feature catalogue (`domain/plan_features.py`) with code, name and description.
      Start with e-way bill, GST exports, Tally export, multi-shop and attachments. Gating
      features by plan is **not** built now; the list only shows on the plan card.
4. **API** (`/api/v1/admin/billing/plans`):
   - list (all roles);
   - create, update, duplicate (Super Admin);
   - archive (Super Admin): sets `is_active` false. A plan in use by any company cannot be
     deleted (409 `PLAN_IN_USE`); one never used can be.
   - Only one active plan can be popular.
   - A plan has 1 to 6 prices.
5. **UI:** a Plans page with cards, an editor with a live card preview, and price rows.

**Acceptance criteria.**

- After the migration every company has the same limits as before (an integration test
  compares them before and after).
- Lowering a plan's `max_users` below a company's current users does not deactivate anyone. The
  next add answers 409 `PLAN_USER_LIMIT`, as before.
- Deleting a plan in use answers 409. Archiving it hides it from the onboarding plan picker.
- Prices are `Decimal` in and out, with no float anywhere (a test posts `"999.90"` and reads
  back `"999.90"`).
- `/billing/plans` is on the money allow-list. No other admin path is.

---

### M21: Subscriptions, manual renewals, Duolink revenue, read-only on expiry

**Goal.** Every company has a subscription with an end date. Duolink records renewals by hand and
sees its own revenue. A lapsed company can still read its books but cannot write.

**WA reference.**

- `RenewSubscriptionRequest` and `CancelSubscriptionRequest`;
- `/api/admin/subscriptions`, `/payments`, `/dashboard` (the KPIs, the 12-month trend,
  `planBreakdown`, `expiringSoon`);
- `Subscriptions.tsx`, `Payments.tsx`, `Dashboard.tsx`;
- the "SaaS mode" table in `README.md` (normal mode: expired = read-only).

**Tasks.**

1. **Tables** (company-owned, so `tenant_id`, row-level security and both policies):
   - `subscription`: plan, plan price, status (`trial`, `active`, `expired`, `cancelled`),
     `starts_at`, `expires_at`, `cancelled_at`, `cancel_reason`;
   - `subscription_payment`: subscription, amount `NUMERIC(12,2)`, method (cash, bank, UPI,
     cheque, Razorpay), reference, notes, `paid_at`, `recorded_by_admin_id`. It is
     **append-only**: add the `forbid_ledger_change` trigger. A mistaken payment is corrected
     with a negative "reversal" payment row that references it.
2. **Migration.** Create one subscription per existing company from `tenant.status`,
   `tenant.plan_id` and `trial_ends_at`. A trial gets `expires_at = trial_ends_at`; an active
   company gets `expires_at` set one year out, flagged for Duolink to review (record this in
   the PR).
3. **Domain** (`domain/subscriptions.py`, unit tests first, with worked dates):
   - `renewal_period(current, price, today)`:
     - paying during a trial starts the paid period today;
     - renewing early adds the time on top of the current expiry;
     - renewing after expiry starts today;
     - month arithmetic clamps the day (31 Jan + 1 month = 28/29 Feb).
   - `access_state(subscription, now)` returns `full`, `read_only` (expired) or `blocked`
     (suspended or cancelled company: unchanged, still 403).
   - `days_left`, and `expiring_within(days)`.
4. **Read-only enforcement** (company side).
   1. In `get_tenant` (or a dependency right after it), a `read_only` company answers 403
      `SUBSCRIPTION_EXPIRED` on every non-GET request, **except**:
      - sign-in, refresh and logout;
      - changing one's own password;
      - exports and PDFs that are POSTs;
      - (from M30) the renewal endpoints;
      - (from M22) raising a support ticket.
   2. List the exceptions in one place and test them.
   3. Reads, reports, GST exports, Tally export and PDF downloads keep working, because the
      books must stay reachable.
   4. **Ended trials:** ADR 0012 only flagged them. From now on an ended trial with no payment
      also becomes `read_only`. Record this change in ADR 0013.
5. **Company-side UI:**
   - a banner from 7 days before expiry: "Your Duolink plan ends on 12 Nov 2026. Contact
     Duolink to renew.";
   - a read-only banner after expiry;
   - every save button disabled with that reason, driven by `GET /tenant` returning
     `access_state` and `expires_at`. The server is still the enforcement.
6. **Admin API** (`/api/v1/admin/billing/...`):
   - `GET subscriptions` (filters: status, plan, expiring within N days);
   - `POST subscriptions/{id}/renew` (Super Admin: plan, price option or custom days, amount
     received, method, reference, notes);
   - `POST subscriptions/{id}/cancel` (Super Admin, reason);
   - `POST payments/{id}/reverse` (Super Admin, reason);
   - `GET payments` (date range, method, company; totals for the filter);
   - `GET dashboard`:
     - companies by status;
     - active subscriptions;
     - revenue this month and this financial year;
     - new companies this month;
     - renewals this month;
     - expiring in 30 days;
     - a 12-month revenue and sign-up trend;
     - companies by plan.
7. **Admin UI.**
   1. The Overview page gains the revenue KPIs and the trend chart (use the `dataviz` skill;
      tokens only).
   2. Add Subscriptions and Payments pages.
   3. The company page's Subscription tab shows history, payments and a renew dialog.
8. **Scope note for the PR.** A payment row is Duolink's receipt record. Duolink's own GST tax
   invoice for the subscription is raised in Duolink's books, outside this ERP. Say so in
   SPEC.

**Acceptance criteria.**

- Domain tests cover trial → paid, early renewal, late renewal and month-end clamping, each
  with dates written out in the docstring.
- When a company expires: GET and the PDF/export endpoints answer 200; saving a bill answers
  403 `SUBSCRIPTION_EXPIRED`; sign-in still works.
- After renewal the same bill saves at once. No sign-out is needed, because access is checked
  per request.
- A payment cannot be updated or deleted (the database refuses). A reversal row nets it out of
  the revenue totals.
- Revenue figures appear only under `/api/v1/admin/billing/*`, and the money-field test still
  fails for any other admin path.
- Support can read the billing pages but cannot renew, cancel or reverse.

---

### M22: Support tickets

**Goal.** A company raises a question from inside the ERP. Duolink answers it from the admin.

**WA reference.** `SupportController.cs` (company side), `TicketReplyRequest`,
`UpdateTicketRequest`, `/api/admin/support`, `Support.tsx` (admin), `pages/app/Support.tsx`
(company).

**Tasks.**

1. **Tables** (company-owned):
   - `support_ticket`: number from `services/numbering.py` with a new `DocType.SUPPORT_TICKET`
     (or a simpler per-company counter if a location-scoped series does not fit; decide and
     record it); subject; category (sign-in, billing, GST/e-way, stock, printing, other);
     priority (low, normal, high, urgent); status (`open`, `in_progress`, `waiting_on_company`,
     `resolved`, `closed`); `raised_by_user_id`; `assigned_admin_id`; `last_reply_at`;
   - `support_message`: ticket, body, author kind (`company_user` or `platform_admin`), author
     id, `created_at`. It is append-only.
2. **ADR 0013 note.** The admin may read ticket subjects and messages, because the company writes
   them to Duolink. The money-field test allow-lists only the `body` and `subject` keys under
   `/support`, and **no amount fields**.
3. **Company API** (`/api/v1/support`):
   - owner and accountant can raise tickets, reply, list their company's tickets, and close
     their own;
   - counter users can raise tickets and see only their own;
   - this works while the company is read-only (M21 exception).
4. **Admin API** (`/api/v1/admin/support`):
   - list with filters (status, priority, company, assigned to me) and counts by status;
   - detail;
   - reply (optional body, optional status; at least one of the two);
   - update status, priority or assignee;
   - Support admins **may** do all of this (it is their job).
5. **UI.**
   - Company: "Help" in the user menu, with a ticket list, a new-ticket form and a thread.
   - Admin: a Support page with KPIs, a list and a thread. The company page's Support tab shows
     that company's tickets.
6. **Signals.** An unread reply shows a dot on the company's Help menu (polling every 60 s is
   fine). New and urgent tickets count in the admin notifications bell (M24).

**Acceptance criteria.**

- A counter user raises a ticket. Duolink Support replies. The counter user sees the reply, and
  another counter user does not see the ticket.
- Company A's tickets never show in company B (a row-level security test as `erp_app`).
- Replying with neither a body nor a status answers 422.
- An expired (read-only) company can still raise a ticket.

---

### M23: Owner-granted support access ("Login as Company", with consent)

**Goal.** With the owner's consent, a Super Admin enters a company read-only to see exactly what
its staff see. It is time-limited, revocable and audited.

**WA reference.** README "Super Admin company access", `POST /companies/{id}/impersonate`,
`ImpersonationController` (`/api/impersonation/status`, `/exit`), `/api/admin/audit/impersonations`,
and the amber "Super Admin Mode" banner. **Two differences from WA:**

- WA needs no consent; here the owner must grant access.
- WA allows writes; here access is read-only.

**Tasks.**

1. **Table** `support_access_grant` (company-owned):
   - `granted_by_user_id` (an owner);
   - `starts_at`, `ends_at` (choices: 1 h, 4 h, 24 h, 72 h);
   - `include_costs` (bool, default false);
   - `reason` and an optional `ticket_id`;
   - `revoked_at` and `revoked_by_user_id`.
   At most one live grant per company at a time (a new grant replaces the old one, which is
   recorded as revoked).
2. **Company side** (owner only): Settings → "Duolink support access".
   - Grant (duration, include cost and margin, reason).
   - See the live grant and its countdown. Revoke it now.
   - History: who from Duolink entered, when, for how long, and how many pages they opened.
3. **Entering** (admin, Super Admin only): `POST /api/v1/admin/tenants/{id}/support-session`
   with a reason.
   1. Refuse it (409 `NO_SUPPORT_GRANT`) without a live grant.
   2. Open a `support_session` row (grant, admin, `started_at`, `ended_at`, request count).
   3. Mint a token of a **third type**, `support`, carrying the admin id, tenant id, grant id
      and session id. Its expiry is the earlier of 2 hours and the grant's `ends_at`.
4. **The support principal.**
   1. `get_tenant` / `get_current_principal` accept a `support` token only on the company's own
      subdomain.
   2. The principal acts as role `owner` for **reads** (so every screen opens). `sees_cost`
      equals the grant's `include_costs`.
   3. **Every non-GET answers 403 `SUPPORT_READ_ONLY`**, except `POST /support-session/exit`.
   4. Every request checks that the grant is still live and the session is still open, so a
      revoke takes effect on the next request.
   5. The platform admin API refuses a `support` token, and the company API refuses a
      `platform` token (ADR 0012's rule, extended).
5. **Audit.**
   - Entering and exiting write to `platform_audit_log` and to the company's `audit_log`.
   - Each request under a support token increments the session's request count and logs
     method and path (not bodies) in a `support_session_event` table, which is append-only and
     kept for 1 year.
   - The admin Audit page gains a "Company access" tab, as WA.
6. **UI.**
   1. The admin company page shows "Enter company (read-only)", enabled only while a grant is
      live, with the time left.
   2. Entering opens `https://<slug>.<BASE_DOMAIN>/support-entry#token=...`. A fragment, so the
      token never reaches server logs. The page stores the token in memory and loads the app.
   3. A permanent banner in the warning token colour reads "Duolink support · read-only ·
      viewing <Company> · ends 16:40 · Exit".
   4. Save buttons are disabled with the reason "Read-only support session".
7. **Notifications.** An admin support session still open after its token expired shows in the
   admin bell (M24).

**Acceptance criteria.**

- With no grant, entering answers 409. With a grant, the admin opens the Today page and the
  bills list and sees what the owner sees.
- With `include_costs` false, cost and margin fields are absent, as for a counter user (reuse
  the counter-user response tests with a support token).
- Every POST, PUT, PATCH and DELETE under a support token answers 403 `SUPPORT_READ_ONLY`
  (a parametrised test over every company route).
- The owner revokes the grant and the admin's next request answers 401.
- A support token for company A used on company B's subdomain answers 401. A support token on
  `/api/v1/admin` answers 401.
- The owner's history shows the session with its request count. The platform audit shows the
  same session.

---

### M24: System health, notifications, maintenance mode, audit log

**Goal.** Duolink can see that the platform is healthy, gets told what needs attention, and can
take the platform down for maintenance in a controlled way.

**WA reference.**

- `GET /system/health` (API, database latency and size, host, counters, recent backups);
- `GET /system/notifications` (the bell);
- `PlatformMaintenance` (a persisted singleton) and `GET/POST /maintenance`;
- `GET /audit` with filters;
- `SystemHealth.tsx`, `Audit.tsx` and `PlatformSettings.tsx`.

**Tasks.**

1. **Health** (`GET /api/v1/admin/system/health`, all roles):
   - API: uptime, version from `CHANGELOG`/build stamp, Python version;
   - database: up, round-trip ms, size, connections in use;
   - disk: free space on the backups and files volumes;
   - the backup row: last success from `backups/.last-success`, plus the off-site sync time
     when it is known;
   - counters: companies, active users, open sessions, audit events today, open tickets.
   Reuse whatever `/api/v1/health/ready` and the company "System" page already compute; do not
   duplicate it.
2. **Notifications** (`GET /api/v1/admin/notifications`): computed on read, no table. The items:
   - subscriptions expiring within 7 days;
   - expired companies;
   - trials ending;
   - open and urgent tickets;
   - support sessions left open;
   - last backup older than 26 hours;
   - disk below 20% free;
   - failed admin sign-ins in the last 24 hours above 10.
   Each item has a level, a title, a body and a link. Add a bell with a count in `AdminShell`.
3. **Maintenance mode.**
   1. Add a singleton table `platform_maintenance` (enabled, message, `changed_by`,
      `enabled_at`), read at start-up and cached for at most 5 seconds.
   2. While it is on, every company request answers 503 `MAINTENANCE` with the message. The
      company UI shows a full-page "Back soon: <message>" screen and retries every 30 s.
   3. The admin API, health checks and `/tenant` keep working.
   4. Toggle it with `POST /api/v1/admin/system/maintenance` (Super Admin, message optional).
      It is audited.
   5. Restore (M25) uses an in-memory flag in the same check, which does not survive a
      restart. Keep the two separate, as WA explains in `PlatformMaintenance.cs`.
4. **Audit log page.**
   - Filters: date range, admin, company, action.
   - Export the filtered rows as CSV (Super Admin).
   - Tabs: "Admin actions", "Company access" (from M23) and "Sign-ins".
5. **Platform settings page** (read-only): security configuration (from the environment, never
   secrets), the subscription lifecycle explained in plain words, and links to each control.

**Acceptance criteria.**

- With maintenance on, a company bill save answers 503 `MAINTENANCE`, while the admin and
  `/api/v1/health/live` answer 200. With it off, everything works without a restart.
- Maintenance survives an API restart (a test that rebuilds the app reads the row).
- Each notification rule has a test that creates the condition and sees the item.
- Health never returns a secret or a connection string (test the JSON keys).
- The audit CSV has one row per audited action with the same filters as the screen.

---

### M25: Backup and recovery from the admin, including one company

**Goal.** Take, verify, download and restore backups of the whole platform **or one company**
from the admin, safely.

**WA reference.**

- README "Backup & Recovery";
- `SuperAdminBackupsController.cs` (list, summary, create, job status, download, restore,
  upload, delete, schedule);
- `BackupRecovery.tsx`;
- `PgToolRunner` (argv only, allow-listed executable, password in the environment, timeout).

**Tasks.**

1. **Table** `platform_backup` (platform-only):
   - kind (`platform`, `company`), tenant (for company backups);
   - file name, size, SHA-256;
   - status (`running`, `verified`, `failed`);
   - `started_at`, `completed_at`, `created_by_admin_id`;
   - `protected` (safety copies are never pruned);
   - `note`.
   Also a `platform_backup_job` table so the UI can poll long jobs.
2. **Job runner.**
   1. Long work runs outside the request: a worker thread, or a `backup` container task that
      polls the job table. Pick the smallest thing that fits the current Docker Compose setup
      and record the choice.
   2. The HTTP call returns a job id, and the UI polls `GET jobs/{id}`.
3. **Platform backup:**
   - `pg_dump --format=custom` plus the files tarball, as `scripts/backup-loop.sh` does
     (reuse its file naming);
   - verified with `pg_restore --list` and the SHA-256;
   - the nightly loop records its runs in `platform_backup` too, so one list shows everything.
4. **Company backup.**
   1. For every table with `tenant_id`, in foreign-key order, run
      `COPY (SELECT * FROM t WHERE tenant_id = :id) TO STDOUT` (CSV, with header).
   2. Add the company's files (attachments, logo, closing PDFs) from storage.
   3. Add `manifest.json` (tenant id and slug, schema revision, per-table row counts, created
      at, SHA-256 per file).
   4. Pack it all as `.tar.gz`. Never `pg_dump` with a filter.
5. **Company restore.**
   1. Check the archive's manifest names this company and this schema revision (409
      `BACKUP_WRONG_COMPANY` or `BACKUP_SCHEMA_MISMATCH`).
   2. Take a protected company backup first.
   3. In **one transaction**, in reverse foreign-key order, delete the company's rows. This
      uses the M26 purge switch for the trigger-protected tables; build that switch here if M26
      is not built yet, and M26 reuses it.
   4. `COPY FROM` each table in forward order.
   5. Reset sequences to at least the maximum id.
   6. Run `services/verify.py` for that company. On any failure, roll back.
   7. The company's `audit_log` is exported but **never overwritten**, as WA does.
   8. The company is in maintenance (403 `TENANT_RESTORING`) while this runs.
6. **Platform restore** stays a command-line runbook (`scripts/restore.sh`). The admin shows the
   exact command and the backup's path, but does not run it. Replacing the whole database from a
   web request that runs on that database is not safe here. Record this in ADR 0013 and the
   PR.
7. **Download, upload, delete.**
   - Download is streamed through an authenticated endpoint, never a static file, and audited.
   - Upload a company archive for restore (size limit, `.tar.gz` only, manifest checked before
     it is accepted).
   - Delete removes an unprotected backup; it needs `DELETE`.
8. **Schedule and retention** (a singleton `platform_backup_schedule`):
   - the daily time;
   - keep N daily, N weekly and N monthly copies;
   - pruning never touches protected or manual backups;
   - `scripts/backup-loop.sh` reads it through a small CLI (`python -m app.scripts.backup_schedule`).
9. **Process safety.** Run `pg_dump`, `pg_restore` and `tar` through one helper:
   - argv list, `shell=False`;
   - absolute paths from an allow-list or `PG_BIN_DIR`;
   - the password via the `PGPASSWORD` environment variable, never on the command line;
   - a timeout that kills the process.
   The dashboard says plainly when the tools are missing.
10. **Roles.** Super Admin does everything. Support may list backups and see their status, but
    not create, download, restore or delete.
11. **UI:** a Backups page with:
    - summary tiles (last backup, verified count, storage used, next scheduled);
    - the list;
    - "Back up all companies";
    - "Back up one company";
    - the schedule form;
    - a restore dialog with `RESTORE`, showing the target company and the backup date.

**Acceptance criteria.**

- Back up company A, delete one of A's bills from the database **as superuser in the test**,
  restore A: the bill is back, and company B's rows are byte-for-byte unchanged (compare
  counts and a checksum of B's rows).
- Restoring A's archive onto B answers 409 `BACKUP_WRONG_COMPANY`.
- A failed restore (a corrupted file in the test) leaves A exactly as before. The failure is
  audited and the safety backup exists and is protected.
- A company archive contains no row whose `tenant_id` is another company's (a test reads every
  CSV in the archive).
- No password appears in any process's argv (the helper's unit test asserts the argv).
- Support gets 403 on create, download, restore and delete.

---

### M26: Document numbering and company data management (as WA)

**Goal.** A Super Admin can see and set each company's number series, and can delete selected
kinds of a company's business data, or all of it, under heavy guards.

**WA reference.** `docs/reference/WA_SUPER_ADMIN.md` sections 9 ("Super Admin company data
management") and 10 ("Document numbering") in full. They are the specification for this milestone, and every rule there
applies unless this section says otherwise. Endpoints: `GET /companies/{id}/data`,
`/data/{key}`, `/data/preview`, `/data/delete`, `/data/delete-all`, `GET/PATCH
/companies/{id}/numbering`. Tests to mirror: `CompanyDataManagementTests`,
`CompanyDataDependencyTests` and `DocumentNumberingTests`.

**This milestone deliberately overrides two ERP rules for this one admin operation.** ADR 0013
must say so:

- "issued documents are never deleted" (B16, migration 0014's `forbid_issued_delete`);
- "ledgers are append-only" (migration 0003's `forbid_ledger_change`).

Everywhere else these rules stay as they are. Deleting a company's data removes records, and the
safety backup (task 5) keeps a copy.

**Tasks.**

1. **Purge switch** (if M25 did not build it).
   1. Write a migration that redefines `forbid_ledger_change()`, `forbid_issued_delete()` and
      `forbid_issued_edit()` to allow the operation **only** when both
      `current_setting('app.platform', true) = 'on'` and
      `current_setting('app.data_purge', true) = 'on'`.
   2. Only `services/platform/data_management.py` and the M25 company restore set
      `app.data_purge`, with `set_config(..., true)`, which is transaction-local.
   3. Add a test that a normal company session, and a platform session without the switch,
      are still refused.
2. **Catalogue** (`services/platform/data_catalogue.py`), a **hand-written list**, as WA's
   `CompanyDataCatalogue`. Each kind has:
   - a key and a label;
   - its tables, child tables first;
   - 4 identifying columns for "View";
   - the deletion order.
   Kinds to cover:
   - items and units;
   - parties and sites;
   - opening balances;
   - purchases (with costs, batches, returns);
   - stock transfers and adjustments;
   - rates and customer rates;
   - quotations and proformas;
   - sales bills (with lines, e-way bills, IRN rows, drop-ship links);
   - credit and debit notes;
   - payments and allocations;
   - the cash book and expenses;
   - daily closings;
   - bank statements and matches;
   - orders, goods receipts and lots;
   - transport (vehicles, trips);
   - attachments (the files too);
   - the stock and party ledgers.
   **Never in the catalogue:**
   - the `tenant` row, users, locations, `shop_settings`;
   - `document_sequence` (it is reconciled, not deleted);
   - the logo and bill templates;
   - subscriptions and payments;
   - support tickets, support access grants and sessions;
   - `audit_log` and `platform_audit_log`;
   - backups.
3. **Dependency test** (as `CompanyDataDependencyTests`), checked against `pg_constraint`:
   - every declared blocker is a real foreign key;
   - the order is a valid topological order;
   - no table outside the catalogue cascades from one inside it;
   - nothing on the preserved list is in the catalogue;
   - every table with `tenant_id` is either in the catalogue or on the preserved list, so a new
     table cannot be forgotten.
4. **Inventory API** (Super Admin only, including reads):
   - per kind: count and dependencies ("Parties: blocked by 120 bills, 40 payments");
   - View: the latest 25 rows, the 4 columns only;
   - Preview: counts for a selection, or for `all`;
   - unknown keys are refused, never ignored.
5. **Delete.**
   - **Selected kinds:** `DELETE` typed. A selection blocked by a kind that is not selected
     answers 409 and names the blocker.
   - **Everything:** `DELETE` typed, plus the company's exact name, plus a tick-box
     acknowledgement.
   - Both:
     1. Take a **protected company backup first** (M25), and refuse to proceed if it fails.
     2. Delete in one transaction, in catalogue order, each child with its own statement: no
        `TRUNCATE`, no disabled constraints, no `session_replication_role`.
     3. Delete the files from storage after the commit.
     4. Reconcile `document_sequence` for the emptied series (task 6).
     5. On any failure, roll back, write `company_data_delete_failed`, and answer that nothing
        was removed.
   - Audit `company_data_deleted` / `company_data_deleted_all` with per-table counts, the
     total, the backup id and the series that moved.
6. **Numbering** (`/admin/tenants/{id}/numbering`, Super Admin only), one row per location,
   document type and financial year. Show:
   - the **highest existing number**, read from the documents themselves (cancelled bills
     count; deleted ones do not);
   - the **configured next number** (`document_sequence.next_value`);
   - the next document written out in full, e.g. `MAIN/26-27/00025`.
   Rules (domain function, unit tests first):
   - the next number must be ≥ highest existing + 1, otherwise 409 with "Bill MAIN/26-27/00007
     already exists. The next number must be 8 or higher.";
   - with no documents left, 1 is accepted;
   - a reason is required;
   - the change is audited with old and new values.
   The series prefix in this ERP is the location code plus `SERIES_SUFFIX`, so there is no
   free-text prefix to edit. Do not add one; say so in the PR.
7. **`services/verify.py`.**
   1. `numbering_check` must accept a gap that an audited numbering change explains, and a
      series that a data deletion reset.
   2. Store both in `document_sequence_event` (append-only: location, doc type, FY, from, to,
      reason, the admin, at).
   3. `make prod-verify` must stay green after both operations.
8. **UI.** Add the company page's **Numbering** and **Data** tabs, hidden from Support:
   - Data has an inventory table with View and Delete, and a separate "Danger zone" card for
     delete-everything;
   - the dialogs fetch a fresh preview when they open;
   - the confirm button stays disabled until the typed words match.

**Acceptance criteria.**

- Delete "quotations" for company A: A's quotations are gone, A's bills untouched, and company B
  untouched (counts before and after for every table of B).
- Deleting "parties" while bills exist answers 409 and names the bills.
- Delete everything for A: A's catalogue tables are empty. A's users, shops, settings,
  subscription, tickets and audit log remain. A's owner can still sign in. The next bill is
  `…/00001`.
- A wrong confirmation word, wrong case, or wrong company name answers 422 and deletes nothing.
- A forced failure halfway rolls back completely and is audited.
- Bills 1 to 7 exist and the admin sets next = 5: 409. Setting 8 works. Setting 20 works, and
  `verify` still passes because the gap is recorded.
- A Support admin gets 403 on every data and numbering endpoint, including the reads.
- Every table with `tenant_id` is classified (the dependency test).

---

### M27: GSP and GSTIN-lookup API admin

**Goal.** Duolink's shared GSP account (e-way bill and IRN, ADR 0009) and a GSTIN lookup are
configured, tested, limited and watched from the admin, not only from environment variables.

**WA reference.** `AdminGstApiController.cs` (status, connect, test, disconnect, settings, logs,
usage, per-company usage) and `GstApi.tsx`. Note the rule that the key is never returned, only
its last 4 characters.

**Tasks.**

1. **Table** `platform_integration` (platform-only, one row per provider kind: `gsp`,
   `gstin_lookup`):
   - provider and base URL;
   - encrypted credentials (Fernet, key from `INTEGRATION_SECRET_KEY` in the environment;
     refuse to start if credentials exist and the key is missing);
   - the key's last 4 characters;
   - status, last success, last failure and the failure message (trimmed, no secrets);
   - daily and monthly limits per company, the warn-at %, the cache hours for GSTIN lookup.
2. **Precedence.** Database settings win over environment settings. The environment remains the
   fallback for single-shop installs. `services/gsp/__init__.py` builds the client from
   whichever is set.
3. **GSTIN lookup.**
   1. Add `lookup_gstin(gstin)` to the GSP interface (fake: deterministic sample data; sandbox:
      the provider's taxpayer search).
   2. Cache the results in a platform-only `gstin_cache` table (GSTIN, legal name, trade name,
      address, state, status, `fetched_at`). This is public registry data.
   3. **Company side:** add a "Fetch details" button next to GSTIN on the party form and the
      onboarding form (M18), through `POST /api/v1/parties/gstin-lookup`. It answers 429
      `GSTIN_LOOKUP_LIMIT` over the company's limit.
4. **Usage log** `integration_call` (`tenant_id`, kind, operation, outcome `ok`, `failed`,
   `cached` or `blocked`, latency, at). **No request or response bodies.** Count per company per
   day and month.
5. **Admin API** (Super Admin; Support may read status only):
   - status;
   - connect or update the credentials;
   - test the connection (one live call);
   - disconnect;
   - update limits;
   - usage (today, week, month; by outcome);
   - per-company usage;
   - recent failures (no bodies).
6. **UI:** an Integrations page with two cards (GSP, GSTIN lookup), a connection form (the key
   input is write-only; show only the last 4), usage tiles and a per-company table.

**Acceptance criteria.**

- Saving a key, then reading the status, shows only the last 4 characters. No endpoint returns
  more (a test greps every admin response for the key).
- With database settings present, e-way bill generation uses them. Without them, it falls back
  to the environment. Both are tested with the fake provider.
- A company over its daily lookup limit gets 429, and the call is logged `blocked`.
- A cached lookup does not call the provider and is logged `cached`.
- Support gets 403 on connect, disconnect and limits.

---

### M28: Bill templates per company

**Goal.** Duolink can give a company its own bill design (tax invoice, proforma, quotation,
credit and debit note) and a second logo, without changing what was already issued.

**WA reference.**

- README "Company billing templates" and "Print and PDF";
- `AdminInvoiceTemplatesController.cs` (field registry, upload, activate, deactivate, delete,
  preview, diagnostics);
- `InvoiceFieldRegistry`, `InvoiceTemplateSanitizer` and `InvoiceTemplateRenderer` in
  `Application/Billing`.

**Tasks.**

1. **Never let an uploaded template be Jinja.** Uploaded HTML is data. Build a small placeholder
   grammar in `domain/bill_template.py` (pure, unit tests first):
   - `{{invoice.number}}`, `{{company.logo}}`, `{{company.secondaryLogo}}`;
   - a repeating `<tr>` holding `{{item.*}}` placeholders;
   - `{{hsn.*}}` rows;
   - totals and amount in words.
   An unknown placeholder is reported and prints blank. The field registry lists every
   placeholder with a description and a sample value, built from the same fields
   `services/invoice_pdf.py` already passes to `invoice_a4.html`.
2. **Sanitizer** (with lxml or html5lib, an allow-list):
   - drop `<script>`, event handlers, `javascript:` URLs, `<iframe>`, `<object>`, `<form>`, and
     external `url()` and `@import`;
   - images only from the company's own uploaded assets;
   - a size cap (500 KB HTML, 2 MB per asset).
   Validation is technical only: it must parse and stay within limits.
3. **Tables** (company-owned):
   - `bill_template`: slot (`tax_invoice`, `proforma`, `quotation`, `credit_note`,
     `debit_note`), name, version, the HTML stored through `services/storage.py`, `is_active`,
     `uploaded_by_admin_id`, a SHA-256;
   - `bill_template_asset`.
   One active template per slot per company. A template, once used by an issued document, is
   immutable: editing creates a new version.
4. **Pinning.** Add a nullable `bill_template_id` to the document tables, set at issue time.
   Reprinting an old bill uses its pinned version, or the built-in layout when null.
   This is a nullable column, so it rewrites no row and the "never edit issued documents" rule
   holds: it is set once at insert. Check that `forbid_issued_edit` is not tripped.
5. **Rendering.** `invoice_pdf` picks the pinned template (else the active one, else the built-in
   `invoice_a4.html`). It fills placeholders with the escaped values and renders with
   WeasyPrint.
6. **Admin API** (`/api/v1/admin/tenants/{id}/bill-templates`; Super Admin writes, Support
   reads):
   - field registry;
   - list;
   - upload (HTML plus assets);
   - activate, deactivate;
   - delete (only if never used);
   - preview (a PDF from sample data);
   - diagnostics (unknown placeholders, missing assets, page size).
   Also the secondary logo upload.
7. **UI:** a Bill design tab on the company page with the slot cards, upload, a live preview
   (PDF in an iframe) and the diagnostics list.

**Acceptance criteria.**

- A template with `<script>` or `onload=` is cleaned, and the preview runs no script (a test
  inspects the rendered HTML).
- A bill issued under template v1 reprints identically after v2 is activated (compare the PDF
  text).
- A `{{config.__class__}}`-style placeholder renders blank and is listed as unknown. No template
  can execute code (a unit test of the renderer with hostile input).
- Company A's template is never used for company B's bill (a row-level security test).
- Deleting a used template answers 409. Deactivating it falls back to the built-in layout for
  new bills.

---

### M29: PWA shell and "force update"

**Goal.** The ERP installs as an app on the shop's PC or phone and picks up a new release
reliably. Duolink can tell every open browser to check for the new build at once.

**WA reference.**

- `application-update/status` and `/force` in `AdminController.cs` (a generation counter, which
  never reloads anyone mid-bill);
- `usePwaUpdate` and the "Update now" toast in `web/src`;
- `PwaDiagnostics.tsx`.

**Tasks.**

1. **PWA.** Add `vite-plugin-pwa`:
   - a manifest (name from the tenant, icons from the logo or the Duolink mark);
   - a service worker that precaches the app shell only.
   **No offline data and no offline billing**: API calls are network-only. A bill must reach
   the server to get its number.
2. **Update flow.**
   1. The service worker checks for updates every 30 minutes and on focus.
   2. A new build shows a toast: "A new version is ready. Update now". It never reloads
      automatically, and never while a form has unsaved changes (reuse the existing
      dirty-form guard if there is one; otherwise add a small `useUnsavedChanges` hook).
3. **Force update.**
   1. Add a singleton `platform_app_update` (generation, `forced_at`, `forced_by`).
   2. Company clients read the generation from `GET /tenant` (or a response header) and call
      `registration.update()` when it changes.
   3. `POST /api/v1/admin/system/force-update` (Super Admin) increments it, and is audited.
4. **Diagnostics.** Add an admin page that shows, for the admin's own browser:
   - whether the app can be installed;
   - service worker state;
   - whether the offline shell is ready;
   - whether an update is waiting;
   - the user agent.
   Also show the build stamps of the backend and frontend.

**Acceptance criteria.**

- `npm run build` produces a manifest and service worker. Lighthouse's installability check
  passes locally (a manual check, with a screenshot in the PR).
- With the network off, the app shell loads and shows "No connection". No bill can be saved.
- Forcing an update makes an open client show the toast within one poll, and an open bill form
  is not reloaded (a frontend test with a mocked registration).
- Support gets 403 on force-update.

---

### M30: Razorpay online renewal (optional, last)

**Goal.** A company owner renews online. The payment lands as a subscription payment
automatically.

**WA reference.** README "SaaS mode and online renewal (Razorpay)" and
`SubscriptionBillingController.cs` (`GET`, `POST orders`, `POST verify`, `POST webhook`).

**Tasks.**

1. **Configuration.** `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET`
   (optional) in settings, as `SecretStr`. Without them, the renewal page says "Contact Duolink
   to renew", as in M21.
2. **Company API** (`/api/v1/subscription`, owner only; works while read-only):
   - `GET`: the current plan, expiry, and the active prices of active plans;
   - `POST orders`: create a Razorpay order for one plan price, and store it in
     `subscription_order` (company-owned: amount, Razorpay order id, status, created by);
   - `POST verify`: check the HMAC-SHA256 signature on the server, then apply the payment.
3. **Webhook.** `POST /api/v1/subscription/webhook` handles `payment.captured`, verified with the
   webhook secret. It is open (no auth) and answers 200 on a duplicate.
4. **Idempotent apply.**
   - One function, keyed on the Razorpay payment id (unique index on `subscription_payment`
     reference for method `razorpay`).
   - It applies `renewal_period` from M21 and records a `subscription_payment` with method
     `razorpay`.
   - The browser callback and the webhook can both arrive in any order; the second is a no-op.
5. **UI.** Add a Plan & billing page for the owner (Settings): current plan, expiry, price
   options, and Pay with Razorpay Checkout. Other roles see "Ask your owner to renew".
6. **Admin.** Razorpay payments show in Payments like manual ones, with the method `Razorpay`.

**Acceptance criteria.**

- A forged signature answers 400 and records nothing.
- Verify and the webhook for the same payment, in either order, give exactly one payment row
  and one renewal.
- A read-only (expired) company can open the page and pay, and is writable again immediately
  after.
- No secret appears in any response or log line (a test).

---

## 7. ADR 0013 outline (write it in M17)

`docs/adr/0013-platform-admin-v2.md`, in the style of ADR 0011 and 0012 (Context, Decision,
Consequences). The Decision section covers:

1. **Two roles:** `super_admin` and `support`. Support reads, answers tickets, and changes
   nothing else.
2. **Duolink billing:** plans with prices, subscriptions, payments. Duolink's own revenue is
   visible under `/admin/billing` only. An expired subscription or an ended trial makes the
   company read-only, never unreadable, and exports always work.
3. **Support tickets:** ticket text is written for Duolink and may be read by it.
4. **Owner-granted support access:**
   - consent, a time limit, read-only;
   - cost hidden unless the owner allows it;
   - revocable at once;
   - every request logged.
   This is the only way Duolink sees a company's books.
5. **Data management and numbering:** a Super Admin may delete a company's business data
   (selected kinds or all) and set number series. This is the one, named exception to "issued
   documents are never deleted" and "ledgers are append-only". It is done through a
   transaction-local purge switch that only the platform data-management and company-restore
   services set, after a protected backup, under typed confirmations, and fully audited. It
   never creates or hides a bill.
6. **Backups:** per-company backup and restore from the admin; platform restore stays on the
   command line.
7. **Integrations:** credentials encrypted at rest, never returned, usage counted without bodies.
8. **Bill templates:** uploaded HTML is data with a placeholder grammar, never a Jinja template.
   An issued document pins its template version.

Consequences: list the new tests that guard each point (the money allow-list test, the
Support-403 parametrised test, the support-token read-only test, the catalogue dependency test,
the key-never-returned test).

## 8. Order and dependencies

```text
M17 ─► M18 ─► M19
  │      └──► M20 ─► M21 ─► M30
  │             │      └──► M22 ─► M23
  └──► M24 ─► M25 ─► M26
              M27, M28, M29: after M18, in any order
```

Build them in number order unless a PR is blocked. Then move to the next independent one and
say so in the PR.

## 9. Codebase traps (read before the first migration)

- **Enums** are `VARCHAR` + `CHECK`. Widen `ck_platform_audit_log_action` (and any other CHECK)
  by hand with the `_swap_check` helper from migration 0016. Autogenerate does not see it.
- **Autogenerate duplicates enum CHECKs** in `create_table`. Keep only the
  `sa.Enum(..., create_constraint=True)` one, then run
  `alembic downgrade -1 && alembic upgrade head && alembic check`.
- **Migration 0023 (tenant logo) revises 0022**, and 0024 revises 0023. The chain is linear up
  to `0029`. Start at `0030`.
- **Policies.** A new tenant table needs both `tenant_isolation` (0024) and `platform_admin`
  (0025). `test_tenancy.py` fails if one is missing.
- **Tests run as `erp_app`**, so row-level security is exercised. A test that must break a rule
  on purpose (M25's "delete a bill as superuser") uses the owner connection explicitly.
- **The money-field test** (`MONEY_WORDS` in `test_platform_admin.py`) matches `rate`, `value`,
  `paid`, `balance` and more. Name admin fields carefully (`users`, `bills_30d`), and put
  billing endpoints on the allow-list rather than weakening the regex.
- **Company writes made by an admin** (M18 seller details, M19 user edits) must run in that
  company's tenant context. Use `set_tenant(db, id)` inside the platform service, then clear
  it, so the `before_flush` listener stamps the right company.
- **Node 22 exactly** for the frontend; Node 25 breaks jsdom.
