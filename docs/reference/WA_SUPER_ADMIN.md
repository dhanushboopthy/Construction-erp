# Reference: the WA (Duolink AlignSuite) super admin

Copied from the WA project (`duolinkin-ai/Alignment_ERP`, `README.md` and
`backend/src/Duolink.Alignment.Api/Controllers/`) on 2026-10-31, so a session that has only this
repository can read it. It is the **behaviour reference** for milestones 17 to 30
(`docs/prompts/SUPER_ADMIN_M17_M30.md`).

WA is a wheel-alignment and tyre workshop ERP written in C#, ASP.NET Core and EF Core. Where WA
says workshop, read company. Where WA names a C# class, it is only a pointer. Build every rule
here in this repo's stack and patterns. **Where the task file differs from this reference, the
task file wins.** For example, the ERP's support access needs the owner's consent and is
read-only, and the ERP's bill templates have different slots.

---

## 1. Platform roles

- `SUPER_ADMIN`: everything.
- `PLATFORM_SUPPORT`: read-only. It can read companies, users, backups, subscriptions and
  audit, and it answers support tickets. It cannot change a company, empty one, restore,
  connect integrations, or manage plans.
- Every Super Admin route is gated on the server (`[RequireSuperAdmin]`). Hiding a tab from
  Support in the UI is a courtesy, not the control.
- A new platform user defaults to the Support role, never Super Admin.

## 2. Admin API surface (WA `AdminController.cs` and siblings)

`SA` = Super Admin only; the rest are readable by Support.

| Area | Endpoints |
| --- | --- |
| Dashboard | `GET dashboard`: KPIs (companies by status, users, active subscriptions, monthly and yearly revenue, new companies, renewals this month, expiring in 30 days, open tickets), a 12-month revenue and sign-up trend, plan breakdown, expiring soon (10), recent companies (8) |
| Companies | `GET companies`, `GET companies/{id}`, `POST companies` (SA), `PATCH companies/{id}`, `POST/DELETE companies/{id}/logo` (SA), `POST companies/{id}/status` (SA, with reason) |
| Company data | `GET companies/{id}/data`, `GET .../data/{key}`, `POST .../data/preview`, `POST .../data/delete`, `POST .../data/delete-all` (all SA, reads included) |
| Company users | `POST companies/{id}/users/{userId}/reset-password` (SA), `PATCH companies/{id}/users/{userId}` (SA), `DELETE companies/{id}/users/{userId}` (SA, typed confirm) |
| Numbering | `GET/PATCH companies/{id}/numbering` (SA) |
| Company access | `POST companies/{id}/impersonate` (SA); `GET /api/impersonation/status`, `POST /api/impersonation/exit` |
| Plans | `GET plans`, `POST plans` (SA), `PATCH plans/{id}` (SA), `POST plans/{id}/duplicate` (SA), `DELETE plans/{id}` (SA) |
| Subscriptions | `GET subscriptions`, `GET payments`, `POST subscriptions/{id}/renew` (SA), `POST subscriptions/{id}/cancel` (SA) |
| Staff | `GET users/platform`, `POST users/platform` (SA), `PATCH users/platform/{id}` (SA), `GET users/company` (directory) |
| Support | `GET support`, `GET support/{id}`, `POST support/{id}/reply`, `PATCH support/{id}` |
| Audit | `GET audit` (filters), `GET audit/impersonations` |
| System | `GET system/health`, `GET system/notifications`, `GET/POST maintenance` (POST SA), `GET application-update/status`, `POST application-update/force` (SA) |
| Backups | `GET backups`, `GET backups/summary`, `POST backups`, `GET backups/jobs/{id}`, `GET backups/{id}/download`, `POST backups/{id}/restore`, `POST backups/upload`, `DELETE backups/{id}`, `GET/PUT backups/schedule` |
| GST API | `GET gst-api/status`, `POST gst-api/connect`, `POST gst-api/test`, `POST gst-api/disconnect`, `PATCH gst-api/settings`, `GET gst-api/logs`, `GET gst-api/usage`, `GET gst-api/companies` (all SA) |
| Bill templates | `GET invoice-templates/field-registry`, `GET invoice-templates`, `GET .../{id}`, `GET .../{id}/diagnostics` (SA), `GET .../{id}/file`, `POST` (SA), `POST .../{id}/activate` (SA), `POST .../{id}/deactivate` (SA), `DELETE .../{id}` (SA), `POST .../{id}/preview`, `GET storage-health` (SA) |
| Company-side billing | `GET /api/subscription`, `POST /api/subscription/orders`, `POST /api/subscription/verify`, `POST /api/subscription/webhook` |

**Notable request rules.**

- **Create company:**
  - name, owner name, owner email, owner mobile, owner password (strong);
  - `RequireOwnerPasswordChange` (default **false**: an owner onboarded by Duolink gets a
    working credential);
  - address, city, state, pincode, GSTIN;
  - plan, plan price, status (trial or active), duration days.
- **Update company:** every field is optional, and null means leave it alone. Includes PAN, CIN
  and state code (blank falls back to the GSTIN or the state name). These fields are editable
  because support is asked to correct exactly these when a company cannot get into its own
  settings.
- **Reset a user's password:** new password; `RequirePasswordChange` (default **true**: the
  password travels by phone, so it must stop working as a shared secret once used); reason.
  It revokes every session of the user. It is not reachable from inside "Login as Company",
  because the audit trail would read as if the company did it itself.
- **Update a company user:** name, email, mobile, status, reason. Null means leave it alone.
  Email is checked for collisions inside the company only.
- **Delete a company user:** a typed `Confirm`, checked on the server too, and a reason.
- **Renew a subscription:** plan, plan price (or `DurationDays`), amount, method (default
  bank), reference, notes.
- **Plan:**
  - code (`^[A-Z0-9_]+$`), name, short and long description;
  - web and mobile user limits, storage MB;
  - features (up to 40 codes);
  - active, popular (at most one active plan may be popular), sort order;
  - 1 to 6 prices, each with duration value and unit (DAY, MONTH or YEAR), a price, and
    active.

## 3. Dashboard notifications (the bell)

The bell's items are computed on read:

- subscriptions expiring within 7 days (WARNING);
- expired companies (CRITICAL);
- support tickets waiting (INFO);
- impersonation sessions not exited (WARNING).

Each item has an id, level, title, body and link.

## 4. Maintenance mode

The operator's own "closed for maintenance" switch is **one persisted row**: enabled, reason,
changed by (a name, not a foreign key), enabled at, updated at.

It is distinct from the **in-memory** switch a database restore uses, and deliberately so. A
process that dies mid-restore should come back serving traffic. An operator who takes the
platform down expects it to stay down across restarts until they say otherwise. The reason is
optional but worth asking for: "back at 9pm" is the difference between a workshop waiting and a
workshop phoning.

## 5. Application update (force)

A generation counter. "Force" mints a new generation and nothing else: no reload, no
`skipWaiting`, no business data touched. A client that sees the new generation calls the same
`registration.update()` its browser already calls periodically. The existing "Update now" toast
decides whether anything visible happens. A workshop mid-invoice sees nothing until it chooses
to.

## 6. GST API management

- It manages Duolink's own provider account: the credential, the limits, and what the platform
  is spending. Company users never see any of it.
- The whole controller is Super Admin only. Support answers "is GST lookup working" from status
  only. Changing the credential or the quota is a commercial decision.
- **The API key is never returned in any form.** `apiKeyLast4` is enough to tell one key from
  another and useless on its own. There is no endpoint, anywhere, that returns more.
- **Screens:**
  - connection (provider, API key);
  - configuration (daily limit, monthly limit, warn at %, cache duration in hours);
  - counts (today, this week, this month, cached this month, successful, failed, blocked, last
    success, last failure);
  - logs;
  - per-company usage.

---

## 7. SaaS mode and online renewal (Razorpay)

The same build runs two ways, decided only by whether Razorpay keys are configured:

| | Normal (no keys) | SaaS (keys set) |
| --- | --- | --- |
| Who renews | Super Admin, from Subscriptions | The company owner, online at `/app/subscription` |
| After expiry | Company is read-only | Company is locked out of everything except the renewal page |
| Payment | Recorded by hand | Razorpay Checkout, verified server-side |

> **ERP decision:** expired means read-only in both modes. There is no lock-out (task file, M21
> and M30).

- Plans and prices come from Super Admin → Plans. Every active price above zero is offered.
- **Renewal timing:**
  - paying during a trial starts the paid period today;
  - renewing a paid plan early adds the time on top of the current expiry.
- Only users with `settings:edit` (the owner and admins) can pay. Other staff see a message
  asking them to contact the owner.
- **Webhook (recommended).** In the Razorpay dashboard, point a webhook for `payment.captured`
  at `https://<api-host>/api/subscription/webhook` with the same secret.
  - A payment then still lands if the buyer closes the browser before Checkout returns.
  - Applying a payment is idempotent, so the browser callback and the webhook can both arrive
    safely.
- Each online payment is recorded as a subscription payment (reference = Razorpay payment id),
  so it shows up in Super Admin → Payments like a manual renewal.

## 8. Super Admin company access ("Login as Company")

> **ERP decision:** the owner must grant access first, the session is read-only, and costs stay
> hidden unless the grant allows them (task file, M23). The rest of WA's design below applies.

There is no master password. A Super Admin opens a company explicitly:

1. Companies → select a company → **Login as Company** (with an optional reason).
2. The platform session is swapped for a company-scoped session, and an `Impersonation` record
   is opened.
3. A permanent amber banner reads **"Super Admin Mode — Viewing \<Company\>"** with **Exit
   Company**.
4. Every action taken is written to the audit log against the admin's name and counted against
   the impersonation record. Passwords cannot be changed in this mode, and the admin portal is
   blocked until they exit.
5. Exiting closes the record and mints a fresh platform session.

`/admin/audit → Company access` shows who entered which company, why, when, for how long, and
how many actions they performed.

## 9. Super Admin company data management

`/admin/companies/{id}` → **Data Management** counts a workshop's business data and removes it.
It is the most destructive thing the platform can do, so it is built around two questions:
*whose data is this* and *what exactly goes*.

**Super Admin only.**

- Not platform support, who can read backups but not empty a workshop, and certainly not a
  company's own administrator.
- Every route is gated by `[RequireSuperAdmin]`, including the read-only ones. The tab is
  hidden from support as a courtesy rather than as the control.
- The company is resolved from the `companies` table before any statement is composed, so a
  company id in a URL is not authority over that company.

### Data inventory

Twenty-one kinds of tenant-owned business data are counted, each with **View** and **Delete**.
View shows the most recent 25 rows, as four identifying columns rather than the records
themselves, so a deletion is checked against data rather than against a number.

The **Dependencies** column is the real foreign-key graph, not a guess at it. `Customers` cannot
go while vehicles, job cards or invoices point at them, and the row says which and how many
instead of offering a button that would fail. A dependency that merely nulls out is not a
blocker and is not listed.

### What is never touched

These are never touched:

- the company record, its users, roles and permissions;
- its settings and branding;
- its subscription and payments;
- its **document number series**;
- its uploaded bill designs;
- the audit log, support tickets and backups.

Every one of those carries a tenant id, and would have been swept up by anything that worked
from the schema rather than from a list somebody wrote. That is why `CompanyDataCatalogue` is a
hand-written list, and `CompanyDataDependencyTests` asserts that nothing in that set ever
appears in it.

The number *series* is preserved: the prefix, and the fact that the series exists. But the
counters of the series that were emptied are reconciled with what survived, so a company with
no invoices left starts again from 1 rather than from 88. See section 10.

### Deleting

Two operations, kept apart on the screen:

- **Delete selected data:** tick the data types, confirm, type `DELETE`.
- **Delete entire company data:** everything. It additionally requires the company's own name
  typed out and a final acknowledgement. The company name is the check that the *right* company
  is on screen, which is the mistake a Super Admin is actually exposed to.

Both show a live preview first, with per-type counts and a total. It is fetched when the dialog
opens rather than carried over from whenever the tab was opened. Both are re-checked on the
server.

- The confirmation word is compared case-sensitively.
- An unrecognised data type is refused rather than skipped, because ignoring a typo is how
  "delete customers and vehicles" quietly becomes "delete customers".

Deletion runs in **one transaction**, in dependency order, with child rows removed by their own
statement rather than left to a cascade nobody checked. The outcome is then the same whether a
constraint cascades, restricts, or is changed later.

- Nothing uses `TRUNCATE`, and nothing disables a constraint.
- A failure rolls the whole thing back, writes `company.data_delete_failed` to the audit log,
  and reports that nothing was removed.

### Audit

`company.data_deleted` and `company.data_deleted_all`, category `PLATFORM`, against the company.
The entry names the Super Admin, the company, the operation, the per-table counts and the total.
Nothing resembling a credential ever reaches the metadata; this is asserted.

### Company data is not the company

Removing the workshop itself is a different operation, and it already exists: set its status to
**Archived** from the company header. Nothing here removes a company record.

### Tests

| Suite | What it covers |
| --- | --- |
| `CompanyDataManagementTests` | The endpoints against throwaway companies: inventory, table-wise delete, blocked selections, dependency ordering, delete-all, confirmation, and a bystander company asserted untouched after every run |
| `CompanyDataDependencyTests` | The catalogue against `pg_constraint`: every declared blocker is a real constraint, the order is a real topological order, nothing outside the catalogue cascades off it, and nothing preserved is in it |
| `npm run check:company-data` | The tab in a real browser: counts render, View shows records, the confirmation refuses to enable itself until the right words are typed, and the data is actually gone afterwards |

## 10. Document numbering

`INV/2026-27/0001` is a prefix, a financial year and a sequence, allocated per company, per
document type, per year.

> **ERP note:** the ERP's series is the location code plus a per-type suffix, per location, type
> and financial year (`services/numbering.py`). There is no free-text prefix (task file, M26).

### Two numbers, and only one of them may refuse you

The allocator is a counter row, created and incremented by a single
`INSERT … ON CONFLICT … DO UPDATE … RETURNING` inside the transaction that creates the document.
That makes simultaneous invoices get different numbers. It is the only allocator: nothing
anywhere does `SELECT MAX(number) + 1`.

A counter is a **high-water mark**. It records where a series has been. It is deliberately not
wound back when a document is deleted, because handing the next invoice the number of one
somebody just deleted is how two bills end up sharing a number in a customer's file.

But a high-water mark is not the same thing as what a company actually has, and confusing the
two was the bug this section documents. The Numbering screen used to read the counter and say
*"7 issued this year"*, then refuse to let a Super Admin start again from 1 after they had
deliberately deleted all seven invoices. It was enforcing a fact about a company that no longer
existed.

So there are two numbers now, and the screen states both:

| | Read from | Used for |
| --- | --- | --- |
| **Highest existing number** | The documents themselves: `MAX` of the sequence across surviving rows of that type and year | Deciding what may be refused |
| **Configured next number** | The counter row | What the next document will actually be called |

Only the first can refuse a value. A cancelled invoice counts, because the row is there and the
bill went out. A deleted one does not, because it is gone. That is the whole of the rule:

- Invoices 1 to 7 exist: the next number must be 8 or higher, and the message says so:
  *"Tax invoice number 7 already exists. The next number must be 8 or higher."*
- Invoices 1 to 5 exist and number 3 was deleted: the highest existing is still 5, so the next
  is 6. Not 3, and not 5.
- Every invoice deleted: there is no highest existing, and 1 is accepted.

The highest is matched on the **financial year**, never on the prefix. Changing `INV` to
`TAXINV` continues the series rather than restarting it, and never renumbers anything already
issued.

### After a company's data is deleted

Emptying a company from the Data Management tab reconciles the counters of the series it
emptied, inside the same transaction, down to whatever survived. That is nothing, so the next
number becomes 1 and the Numbering page opens on it. The deletion response and its audit entry
both name the series that moved.

Only that operation reconciles. Deleting one estimate from the company's own screen leaves the
counter where it is, on purpose. Reusing the number of a document a user deleted by hand is not
something anybody asked for, and the Super Admin can always set the series wherever they want
it.

### The Numbering page

`/admin/companies/{id}` → **Numbering**, Super Admin only. Per series it shows:

- the prefix and the next number;
- both of the numbers above;
- the document the next one will produce, written out in full (`INV/2026-27/0025`), because a
  prefix and a sequence are two abstractions and the bill is the thing.

A series whose counter is ahead of its documents says so, and offers the value that closes the
gap.

Saving writes the counter and the prefix to the database, so it survives a reload, a sign-out
and entering company mode. Changes are audited with the old and new prefix, the old and new next
number, the financial year, the Super Admin and the reason.

### Tests

| Suite | What it covers |
| --- | --- |
| `DocumentNumberingTests` | The whole policy against real documents: delete-all then start from 1, a partial deletion leaving a gap, a manual next number reaching the next bill, cancelled invoices staying reserved, prefix changes, company and document-type isolation, financial-year scoping, twenty concurrent allocations, and the audit entry |
| `npm run check:numbering` | The screen in a real browser: both numbers shown, a refused value refused as it is typed, Save surviving a reload, and the next invoice actually carrying the number that was set |

## 11. Backup and recovery

Backups are taken with PostgreSQL's own tooling, never by serialising entities to JSON. Long
operations run on a background worker, and the client polls a job id, because a
multi-gigabyte `pg_dump` cannot be held open by an HTTP request.

**Super Admin: `/admin/backups`**

| | |
| --- | --- |
| Full platform backup | `pg_dump --format=custom`, the whole database including schema, sequences and constraints |
| Company backup | server-side `COPY (SELECT … WHERE "tenantId" = …) TO STDOUT` per table, packed as `.tar.gz` with a manifest |
| Verification | SHA-256 recorded, archive re-read with `pg_restore --list`, core tables confirmed; only then is a backup marked **VERIFIED** |
| Storage | behind `IBackupStorage`; `LocalBackupStorage` ships, and S3-compatible providers drop in without touching backup logic |
| Retention | daily, weekly and monthly keep-counts, configurable; manual and pre-restore safety copies are never pruned |

**Restore** is the most defended operation in the product. In order:

1. The checksum is re-verified.
2. The archive is validated.
3. **A full backup of the current database is taken and retention-protected.**
4. The archive is rehearsed into a throwaway database.
5. The live database is replaced, with the API in maintenance mode.
6. On failure, the safety backup is put back automatically.

The Super Admin must type `RESTORE`, which the server enforces as well as the dialog.

> **ERP decision:** a platform restore stays on the command line (`scripts/restore.sh`). A
> company restore is built in the admin (task file, M25).

**Company restore.**

- It replaces one tenant's rows inside a single transaction.
- It verifies that the archive's own manifest names that tenant, so one company's data can never
  land in another.
- The tenant's audit log is deliberately exported but never overwritten. It is append-only
  history, and rolling it back would erase the record of the restore itself.

Company users can still export and download their own tenant's data, scoped so an export can
never contain another workshop's records. Restoring is Super Admin only.

Backup artefacts are never served as static files. Every download goes through an
authenticated, streamed endpoint and is written to the audit log, alongside these events:

- `BACKUP_CREATED`;
- `BACKUP_RESTORE_STARTED`, `BACKUP_RESTORE_COMPLETED`, `BACKUP_RESTORE_FAILED`;
- `BACKUP_DELETED`;
- `BACKUP_SCHEDULE_UPDATED`.

`pg_dump` and `pg_restore` are invoked through `PgToolRunner`, which:

- passes an argv array (no shell);
- resolves the executable from a fixed allow-list;
- sends the password via the child's environment rather than the command line;
- kills the process on timeout.

The PostgreSQL client tools must be on the server. The dashboard says plainly when they are
missing, rather than pretending backups are healthy.

## 12. Company billing templates

> **ERP note:** WA's four slots (service and tyre × estimate and invoice) become the ERP's tax
> invoice, proforma, quotation, credit note and debit note. WA renders with Chromium; the ERP
> renders with WeasyPrint. Placeholder names follow the ERP's own fields (task file, M28).

A company uploads its own bill as an **HTML file**, and that file *is* the bill format. It is
stored as uploaded and rendered as uploaded: the same dimensions, margins, borders, table widths,
row heights, fonts, logo, header, footer and page rules. Nothing recreates it, redraws it, or
works out where anything belongs, because the HTML and its CSS already say. The only processing
is substitution.

```text
upload HTML → sanitize → store in a slot → activate → new document of that slot
                                                            ↓
                                                  replace placeholders
                                                            ↓
                                                  render stored HTML → PDF
```

**Slots.**

- A document only ever renders with its own slot's design.
- A slot with nothing active uses the default layout.

**Placeholders.**

- Anywhere the design writes `{{key}}`, the live value goes.
- The keys are the field registry: the same fields the default bill is built from, so a template
  and the default layout can never disagree about what a total is.
- The buyer block is addressable part by part (`{{customer.addressLine1}}`,
  `{{customer.gstin}}`, `{{customer.stateCode}}`, and so on). The seller's half is
  `{{company.pan}}`, `{{company.stateCode}}` and `{{company.cin}}`. `{{consignee.*}}` fills
  "Ship To" and falls back to the buyer.
- The header grid and bank block have keys too: buyer order number, delivery note, e-way bill
  number, IRN, acknowledgement number, payment terms, destination, bank name, account number,
  branch, IFSC and jurisdiction.

**Per-line tax** (taxable, CGST/SGST/IGST rate and amount, total tax, unit):

- It comes from what the server already computed for that line, by the same function that
  produced the document's totals. There is exactly one tax engine.
- A tax that does not apply prints blank in both its rate and amount columns, not `0.00`.
- A unit test walks every alias and fails if any lands on a key the registry does not declare.

**Formatting.** `{{key|format}}` takes a date or number format, or `symbol` to prefix ₹. Money
prints as plain digits by default.

**The item row is the template's own row.**

- The `<tr>` holding `{{item.*}}` placeholders is cloned once per line, keeping its exact
  classes, inline styles, borders, column widths and cell structure.
- A bill not laid out as a table marks its repeating section with `<!-- items:start -->` and
  `<!-- items:end -->`.

**Scripts are removed, not refused.**

- The sanitizer takes out what a browser would *execute*:
  - `<script>` and `on*` attributes;
  - `javascript:` and `vbscript:` URLs;
  - `<iframe>`, `<object>`, `<embed>` and `<base>`;
  - a meta refresh;
  - CSS `expression()`, `behavior:` and `-moz-binding:`.
- It then stores the result, and the company is told what came out.
- An image whose address is unsafe loses only that image.
- Everything else is kept exactly as written: the markup, the `<style>` block (`@page`,
  `@media print`, page breaks, widths, fonts, borders, flex, grid), the attributes, images and
  every placeholder.
- Sanitisation is settled after one pass, so a stored design never drifts.

**Validation is technical only.**

- It checks for a readable file, a sane size and a document that parses.
- A template is never refused for a field it chooses not to print; that is a warning at most.
- An unrecognised placeholder renders blank rather than printing braces.

**Preview is the real thing.** The stored HTML is rendered with sample data, through the same
substitution and renderer a real bill uses.

**One active template per slot.**

- Activating a design stands down only the previous design in *that* slot.
- Versions run per slot. Re-uploading creates a new version, so an earlier design survives.
- Company A's template is never used for company B.
- Changing or deleting a template never alters an already-issued document: a bill is stamped
  with the design it was issued under and reprints on that.
