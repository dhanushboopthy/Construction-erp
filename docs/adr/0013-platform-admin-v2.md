# ADR 0013: Platform admin v2: roles, owner-granted access, Duolink billing, data management

**Status:** Accepted, Milestone 17. Amends [ADR 0012](0012-platform-admin-and-data-privacy.md).
The points below are built one milestone at a time (M17 to M30, `docs/prompts/SUPER_ADMIN_M17_M30.md`);
each says which milestone builds it.

**Context.** The Duolink admin of Milestone 16 can onboard companies, help locked-out users and
set plan limits. Running a hosted service needs more: Duolink must charge for plans and renew
them, answer support tickets, watch the platform, back up and restore one company, share a GSP
account, give a company its own bill design, and, when a company asks, look inside its books to
help. ADR 0012 said "if support needs more than counts, it must come through the company's
owner". The owner has now decided how that works (below). The WA project (Duolink AlignSuite) is
the behaviour reference; its code is not copied (`docs/reference/WA_SUPER_ADMIN.md`).

**Decision.**

1. **Two roles (M17).** `super_admin` and `support`. Support reads everything the admin shows and
   answers tickets, and changes nothing else. Every write route in `/api/v1/admin` is behind the
   `SuperAdminOnly` dependency, so the server enforces it; hiding a button is a courtesy. A new
   staff member defaults to `support`. The role is read from the database on every request (the
   token carries it for display only), so a demotion takes effect at once. The last active Super
   Admin cannot be demoted or deactivated (409 `LAST_SUPER_ADMIN`), and nobody lowers their own
   access (409 `SELF_CHANGE`). A temporary password must be changed before any other call (403
   `PASSWORD_CHANGE_REQUIRED`).
2. **Duolink billing (M20, M21, M30).** Plans with prices, subscriptions and payments are tables
   in the database. Duolink's own revenue is visible only under `/api/v1/admin/billing/...`. An
   expired subscription makes a company **read-only**, never unreadable: reading, reports, GST
   exports, Tally export and PDFs keep working, writes answer 403 `SUBSCRIPTION_EXPIRED`.
   **An ended trial with no payment also becomes read-only.** ADR 0012 only flagged it; this
   replaces that sentence. Suspending or cancelling a company still blocks everything (403), as
   before. A payment row is Duolink's receipt record; Duolink's own GST tax invoice for the plan
   is raised in Duolink's books, outside this ERP. Online renewal with Razorpay is optional and
   last (M30).
3. **Support tickets (M22).** A ticket's subject and messages are written for Duolink, so the
   admin may read them. No amount fields are allowed in them.
4. **Owner-granted support access (M23).** This is the only way Duolink sees a company's books.
   The owner turns it on for a set time (1, 4, 24 or 72 hours) and may revoke it at once. A Super
   Admin then enters the company **read-only**: a third token type, `support`, valid only on that
   company's address, acting as the owner for reads and refused on every write (403
   `SUPPORT_READ_ONLY`). Cost and margin stay hidden unless the owner ticks "show cost and
   margin" on the grant. Every request is checked against the live grant and logged (method and
   path, never bodies). There is no access without a live grant.
5. **Data management and numbering (M26).** A Super Admin may delete a company's business data,
   selected kinds or all of it, and set or reset document numbering. This is the **one, named
   exception** to "issued documents are never deleted" (B16, migration 0014) and "ledgers are
   append-only" (migration 0003). It works through a transaction-local purge switch
   (`app.platform = on` and `app.data_purge = on`) that only the platform data-management service
   and the company restore (M25) set. It runs after a protected backup, behind typed
   confirmations (`DELETE`, and the company's exact name for everything), with a preview and a
   full audit trail. It never creates or hides a bill: it removes records, and the safety backup
   keeps a copy.
6. **Backups (M25).** Per-company backup and restore run from the admin (a manifest-checked
   archive of that company's rows and files, restored in one transaction). **Restoring the whole
   platform stays a command-line runbook** (`scripts/restore.sh`): replacing the database from a
   web request that runs on that database is not safe. The admin shows the command and does not
   run it.
7. **Integrations (M27).** Duolink's GSP and GSTIN-lookup credentials are encrypted at rest, never
   returned (only their last four characters), and usage is counted per company without request
   or response bodies.
8. **Bill templates (M28).** An uploaded template is data with a small placeholder grammar. It is
   never a Jinja template and never executes code. An issued document pins the template version
   it was printed with, so reprinting never changes an old bill.

**What does not change.** ADR 0011 (row-level security on every company table) and
ADR 0012's other points: separate accounts, separate tokens, the admin address, reading across
companies only through platform mode, and "counts and statuses only" for every admin answer
outside `/billing`, `/support` (ticket text) and a live support session. Money stays `Decimal`
and `NUMERIC`. Cost and margin never reach non-owner roles, which includes Duolink support
inside a company.

**Consequences.**

- Tests that guard each point:
  - Roles (M17): `test_platform_staff.py` walks every route under `/api/v1/admin` from the
    OpenAPI document; each write answers 403 to Support and each read answers 200, so a new route
    cannot be forgotten. It also covers the two staff guards and the forced password change.
  - Money: `test_no_admin_answer_carries_money` keeps failing on any money-like field in an admin
    answer. From M20 it gets an explicit allow-list of `/billing` paths; the regex is not
    weakened.
  - Support session (M23): a parametrised test over every company route expects 403
    `SUPPORT_READ_ONLY` for each write under a `support` token.
  - Data catalogue (M26): a dependency test against `pg_constraint` checks that every table with
    `tenant_id` is either in the catalogue or on the preserved list.
  - Credentials (M27): a test greps every admin response for the saved key.
- Every later milestone adds its actions to `PlatformAction`, widens the CHECK on
  `platform_audit_log` by hand, and audits what an admin did with the admin, the company, the
  target, the reason and the request id, and never a password, token or key.
- The admin is a larger attack surface than in ADR 0012. Super Admin accounts should be few, and
  the Staff page shows who they are.
- Existing admins become Super Admins when migration 0030 runs, because before it every admin
  could change everything. Add Support accounts for read-only staff.

## Update, 2026-11-04 (Milestone 22): support tickets

- **The admin may read ticket subjects and messages.** The company writes them to Duolink on
  purpose, so this is not the company's books being read. The rest of ADR 0012 is unchanged: no
  amount, cost or document content from the books.
- **The money-field test is unchanged.** `test_no_admin_answer_carries_money` now also walks the
  ticket list and detail, and no support answer carries an amount-like key.
- **Support may write here.** Replying to and updating a ticket is a Support admin's job, so those
  two routes are open to every admin role. The Support-403 test lists them as the explicit
  exceptions; any other new admin write still needs a Super Admin.
- **The company does not see which admin answered.** Messages show "Duolink Support"; Duolink sees
  the real names.
- **Audit.** `support_reply` and `support_update` record the ticket number, the status change and
  whether a message was sent, never the text.

## Update, 2026-10-31 (Milestone 21): read-only on expiry is now enforced

- **An ended trial with no payment is now read-only.** ADR 0012 only flagged a trial that had
  ended; from M21 the server acts on it. The company can read and export but every write answers
  403 `SUBSCRIPTION_EXPIRED`. Companies whose trial had already ended when migration 0034 ran
  become read-only on that day.
- **The rule.** The stored subscription status is `trial`, `active` or `cancelled`. "Expired" is
  derived from `expires_at` on every request, so a renewal applies on the next request and nothing
  runs at midnight. A company whose subscription is expired, an unpaid ended trial, or cancelled is
  **read-only**: GET requests work (reports, GST exports, Tally export, PDFs) and any other method
  answers 403, except sign-in, refresh, logout and changing one's own password. The list lives in
  one place and is tested; every PDF and export is a GET, so none is listed. A suspended or closed company is
  still blocked completely.
- **Cancelled means read-only, not blocked.** Cancelling is a billing decision; closing the company
  is the separate block.
- **Payments.** `subscription_payment` is append-only by database trigger. A mistake is corrected
  with a negative reversal row. Reversing nets the revenue but does not shorten the expiry.
- **Revenue stays under `/api/v1/admin/billing/*`.** No other admin path and no company answer
  carries a payment or revenue figure; `test_no_admin_answer_carries_money` keeps its list of
  allowed billing paths. A payment row is Duolink's receipt record; Duolink's GST tax invoice for
  the subscription is raised in Duolink's own books, outside this ERP.

## Update, 2026-11-10 (Milestone 28): bill templates

- **Uploaded HTML is data, never a template.** A small placeholder grammar replaces `{{key}}` from
  a registry of known fields; anything else prints blank. Nothing is evaluated, no file or
  network address is read while drawing (the renderer's fetcher serves only the design's own
  images), and the hostile-input tests in `tests/unit/test_bill_html.py` and
  `tests/integration/test_bill_templates.py` guard this.
- **A document pins its design.** `bill_template_id` is set at insert on bills, quotations,
  proformas, credit notes and debit notes; a reprint uses it, and a null pin is the built-in
  layout. A design some document uses can never be deleted or changed: a change is a new version.
- **GST fields cannot be dropped.** A tax invoice, credit note or debit note design is refused
  when it omits a field the rules require, so a design can restyle a bill but never make it less
  than a full GST tax invoice.
- **Support may preview.** A preview reads nothing of the company's, so it is the second explicit
  Support write exception, listed in the Support-403 test.
