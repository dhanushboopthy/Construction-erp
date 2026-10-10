# Handoff: finance milestones FM3 to FM10

This is the brief for a Claude Code session (cloud, Sonnet) that builds the remaining finance
milestones. FM1 (cash book, P&L) and FM2 (stock adjustments, ITC to reverse) are built. Read
this whole file before you start, then work through the milestones in order.

## 1. Goal

Build FM3, FM4, FM5, FM6, FM7, FM8, FM9 and FM10 from `docs/FINANCE_REVIEW.md`, section 6. Each
milestone gets its own branch and pull request. Each one ends green: tests, lint, types,
migration check, docs. You are acting as both the CFO and the code owner of a construction
materials distributor (TMT bars, pipes, cement, binding wire, angles and channels; one shop and
one godown today, more shops later). The business turns over about ₹24 crore a year on thin
margins (2 to 4% gross). Every figure you build has to be one the owner can act on, and none can
be wrong.

## 2. Read first

1. `CLAUDE.md`: stack, layout, hard rules, commands.
2. `docs/FINANCE_REVIEW.md`: the audit, the gap table F1 to F29, the KPI catalogue (section 5),
   the milestones and their acceptance tests (section 6), and open questions (section 7).
3. `docs/ROADMAP.md`, "Finance milestones" table: shows which FM is next (first one not **Done**).
4. `docs/SPEC.md`: the "Built (FM1 ...)" and "Built (FM2 ...)" sections show the level of detail
   expected for each new FM section.
5. The FM1 and FM2 code, as the pattern to copy:
   - **Domain:** `backend/app/domain/finance.py`, `backend/app/domain/inventory_analytics.py`,
     `backend/app/domain/kpi_catalogue.py`.
   - **Services:** `backend/app/services/cashbook.py`, `backend/app/services/adjustments.py`,
     `backend/app/services/finance.py`.
   - **Migrations:** `backend/alembic/versions/20261010_0015_*.py` and `20261010_0016_*.py`
     (hand-edited; read their docstrings).
   - **Tests:** `backend/tests/unit/test_finance.py`, `backend/tests/unit/test_inventory_analytics.py`,
     `backend/tests/integration/test_finance.py`, `backend/tests/integration/test_adjustments.py`.
   - **Frontend:** `frontend/src/pages/cash/CashBookPage.tsx`, `frontend/src/pages/stock/AdjustmentsPage.tsx`,
     `frontend/src/pages/reports/PnlPage.tsx`, `frontend/src/components/Metric.tsx`,
     `frontend/src/hooks/useShops.ts`.

## 3. Start of session

1. `git fetch origin` and look at the open PRs. FM1 is on `feat/fm1-cash-book` and FM2 is on
   `feat/fm2-stock-adjustments`; the owner merges them into `main` in order.
   - If FM2 is merged, branch FM3 from `origin/main`.
   - If it is not merged yet, branch FM3 from `origin/feat/fm2-stock-adjustments`, because the
     migrations chain on each other (FM3's migration revises `0016`).
   - Later milestones branch from the previous FM branch the same way.
   - Always open the PR against `main`.
2. Set up the environment (section 4) and run the full test suite once before you change
   anything. It must already be green: 563 backend tests and 87 frontend tests as of FM2.

## 4. Environment (cloud)

Use Docker if it is available (`make up`, `make test`, `make lint`, `make gen-api`). If it is
not, run everything natively, as CI does (`.github/workflows`):

- **PostgreSQL 16 or 17:**
  1. Install it with apt if missing, then start it.
  2. Create role `erp` with password `erp` (it needs to create databases) and database
     `erp_test`.
  3. Export `TEST_DATABASE_URL=postgresql+psycopg://erp:erp@localhost:5432/erp_test` and
     `DATABASE_URL` set to the same value.
- **Backend (Python 3.13 with uv):** in `backend/`, run `uv sync`, then:
  - `uv run pytest`;
  - `uv run pytest tests/unit --cov=app/domain --cov-fail-under=100` (CI requires 100% domain
    coverage);
  - `uv run ruff check . && uv run ruff format --check . && uv run mypy app`;
  - `uv run alembic upgrade head && uv run alembic check`.
- **Frontend: Node 22 exactly.** Node 25 breaks jsdom's localStorage and the tests fail with
  odd errors. In `frontend/`, run:
  - `npm ci`;
  - `npm test`;
  - `npm run lint && npm run typecheck && npm run format:check && npm run build`.
- **API types:**
  1. Start the API: in `backend/`, run `uv run uvicorn app.main:app --port 8000` with
     `DATABASE_URL` pointing at a migrated database.
  2. In `frontend/`, run `npm run gen:api`.
  3. Add short aliases for new schemas to `frontend/src/api/types.ts`.
- **Seed data for manual checks:** `uv run python -m app.scripts.seed`. Sign in as owner with
  `owner-pass-123` (dev only). `SEED_SHOPS=2` adds a second shop.

## 5. Git, authorship and PRs (strict)

- **Author:** the only author is `dhanushboopthy <dhanushbopathy@gmail.com>`. Run
  `git config user.name dhanushboopthy` and `git config user.email dhanushbopathy@gmail.com` in
  the repo before the first commit.
- **No Claude attribution anywhere:** no `Co-Authored-By` trailers and no "Generated with
  Claude Code" lines in commits, PR titles or PR bodies. `.claude/settings.json` sets
  `attribution` to empty for this reason; follow it even if a default says otherwise.
- **Commits:** conventional style, e.g. `feat(fm3): labelled rate overrides`. One or two commits
  per milestone.
- **Never:**
  - push to `main`;
  - force-push;
  - delete branches;
  - merge PRs (the owner merges);
  - rewrite history.
- **PR title:** `FM<n>: <milestone name>`.
- **PR body:**
  - The first line is exactly `FM<n> done, <X> backend + <Y> frontend tests pass.`, or
    `Blocked on <reason>`.
  - Then: what changed for the owner in plain words; the acceptance test and how it is proven;
    decisions taken with their defaults (especially "accountant to confirm" items); bugs found
    and fixed; what is deferred and why.

## 6. Rules for every milestone (from the owner's brief; do not relax them)

1. **Formulas** are pure functions in `backend/app/domain/finance.py` (money and profit) or
   `backend/app/domain/inventory_analytics.py` (stock). Write the unit tests first. Use
   hand-worked numbers from this business and show the arithmetic in the test docstring (see
   `test_finance.py`). No DB, HTTP or clock in domain code; pass `today` in.
2. **Reports are queries.** Store nothing that can be recomputed. The only exception is a frozen
   month-end snapshot, when a milestone needs one.
3. **New capture** (anything a person types in) needs:
   - a form;
   - reason codes where a reason matters;
   - thresholds read from `shop_settings` (never hard-coded);
   - owner PIN approval above the threshold for counter staff (`ApprovalAction` + the
     `ApprovalPrompt` component);
   - an audit trail (`Audited` mixin; issued documents get the triggers).
4. **Cost, margin and profit are owner-only.** Use separate response models chosen by
   `principal.sees_cost`, and test every such endpoint as a counter user. The accountant gets
   what they need to file returns (GST, ITC) but not margins, unless the milestone says
   otherwise.
5. **Never fabricate a figure.** With too little history, return and show "Not enough data yet
   (needs N days)". Return `None`, not 0, when there is nothing to divide by.
6. **Periods** are calendar months in an April to March financial year, with IST dates.
   `services/finance.month_bounds("2026-10")` gives the bounds.
7. **Every KPI** goes into `domain/kpi_catalogue.py` (code, name, formula, meaning, worked
   example, sources, owner_only, refresh, good direction, unit). It is served by
   `GET /api/v1/kpis/definitions`. On screen, use `<Metric code=...>`, which shows tabular
   numbers, a "what this means" line and the formula on hover.
8. **Each PR includes:**
   - the migration;
   - tests (unit first, integration, frontend);
   - `docs/SPEC.md` (a "Built (FMn ...)" section);
   - `docs/ROADMAP.md` (mark the FM **Done** with its branch);
   - `CHANGELOG.md` (next minor version: FM3 = 1.4.0, and so on);
   - `docs/API.md` (an "Endpoints (FMn ...)" table with roles and error codes);
   - `docs/GLOSSARY.md` (new terms with worked numbers).
9. **Guardrails:**
   - Never alter issued documents or ledger rows. A correction is a new document. Adding a
     nullable column is fine, because it rewrites no row.
   - Use `Decimal` and `NUMERIC` only. Never float, in Python or in tests, except
     `pytest.approx` on API JSON.
   - Any treatment marked "accountant to confirm" sits behind a `shop_settings` flag. Its
     default is the conservative choice (more tax, less profit, earlier recognition of loss).
   - Skip work with no clear rupee or risk payoff, and say what you skipped and why.
   - If something is genuinely the owner's decision and blocks the milestone, stop and write
     `Blocked on <reason>` rather than guessing.
10. **UI:** follow `docs/DESIGN.md` ("Indigo works" tokens; no raw hex; light and dark).
    - Keyboard first; tabular numbers; plain words a shop owner uses.
    - Shop pickers come from `useShops()` and stay hidden while there is one shop.
    - Owner, accountant and counter each see only their role's routes (`RequireRole`, the tabs
      in each layout, `modules.ts`, `actions.ts`).
    - Use the `impeccable`, `frontend-design` or `ui-ux-pro-max` skill if it is available for
      new screens.

## 7. Codebase patterns and traps (learned in FM1 and FM2)

- **Enums** are `VARCHAR` + `CHECK` (`models/enums.py`, `str_enum`). Alembic autogenerate does
  not diff a changed CHECK. When you add a value to an existing enum, widen its CHECK by hand in
  the migration, and narrow it back in downgrade. Migration 0016 has a `_swap_check`
  helper and the constraint names, for example:
  - `ck_approval_approval_action`;
  - `ck_document_sequence_doc_type`;
  - `ck_stock_ledger_stock_ref`.
- **Autogenerate duplicates enum CHECKs** in `create_table`. Delete the duplicates and keep only
  the `sa.Enum(..., create_constraint=True)` one. Then run
  `alembic downgrade -1 && alembic upgrade head && alembic check`.
- **Current values to extend** (copy the full lists from migration 0016):
  - Approval actions: credit_override, below_cost, discount, backdate, late_return, expense,
    stock_adjustment.
  - Doc types: sales_invoice, credit_note, debit_note, delivery_challan, purchase_entry,
    payment_receipt, cash_voucher, stock_adjustment.
  - Stock refs: opening, purchase, purchase_return, sale, sale_return, transfer, adjustment
    (posted count), stock_adjustment.
- **Document numbers** come from `services/numbering.allocate_number` inside the saving
  transaction.
  - Series suffixes in use: `""` (bill), C, D, DC, P, R, V (cash voucher), A (adjustment).
  - The location code + suffix + `/26-27/` + 5 digits must fit 16 characters.
- **Issued documents:** add the triggers `forbid_issued_delete()` / `forbid_issued_edit()` to
  every new document and line table in its migration. Also add the table to `NO_DELETE` /
  `NO_EDIT`, and its number column to `numbering_check`, in `backend/app/services/verify.py`.
- **Ledgers are append-only** (`stock_ledger`, `party_ledger`) and protected by triggers. Write
  only through `services/ledgers.add_stock_move` / `add_party_entry`. Lock items with
  `ledgers.lock_items` before you check stock.
- **Settings:**
  - A new `shop_settings` field needs the model, `schemas/settings.py`, the migration
    (`server_default`), `frontend/src/test/mockApi.ts` `SETTINGS`, and the Settings form
    (`pages/settings/ShopSettingsPage.tsx`, `AMOUNT_KEYS` / `FLAG_KEYS` plus a field).
  - The form sends every field on save. A field missing from the form is silently reset to its
    default; FM2 fixed exactly this bug for `expense_approval_limit`.
- **Errors:**
  - Rule failures: `BusinessRuleError(message, code=..., field=..., requires_owner_approval=...)`
    returns 409.
  - `PermissionDeniedError` returns 403; `NotFoundError` returns 404.
  - Messages are plain sentences for the shop. Never put a cost or value in a message a counter
    user can see.
- **Roles:**
  - Route dependencies: `OwnerOnly`, `OwnerOrAccountant`, `OwnerOrCounter`, `CurrentPrincipal`.
  - Counter staff are limited to their own shop with `principal.can_access_location(id)`, and
    list endpoints scope to `principal.location_ids`.
  - Counter entries are dated today; back-dating is the owner's (`BACKDATE_NEEDS_OWNER`).
  - Closed days refuse writes (`closing_service.ensure_day_open`).
- **Approvals:** `approval_service.load_valid(db, ids, requester_id, party_id=0)`, then match
  the action, then `approval_service.mark_used([approval], number)`.
- **Circular imports between services:** use a function-level import with a short comment (see
  `services/closing.py` and `services/adjustments.itc_reversal`).
- **Tests:**
  - Integration tests share the `world` fixture from `tests/integration/test_sales.py` (opening
    stock: TMT at ₹55/kg in S1 and G1; cement at ₹350/bag in S1 at 28% GST; customers `ravi`
    and `walkin`; supplier `supplier`).
  - Import `world` and add the new test file to the `per-file-ignores` glob in
    `backend/pyproject.toml` (F811, E731).
  - Users: `OWNER`, `COUNTER` (S1), `COUNTER2` (S2), `ACCOUNTANT`.
  - The `seeded` fixture is the same DB session the client uses. Use it for raw SQL checks, with
    `pytest.raises(DBAPIError), seeded.begin_nested():` in that order.
  - To get round numbers, create an 18% item and buy it at a known rate (see
    `test_adjustments.new_item`; purchase lines need `unit`).
- **Frontend tests:** `mockApi(routes)` + `session(USER)` + `renderAt(path)`. Wait for data with
  `findBy...` before you assert on table rows.
- **Docker volume note (local only):** files created inside the containers are owned by root.
  This does not apply in the cloud.

## 8. Decisions already made (do not reopen)

- One shop and one godown today. Shop pickers and columns appear by themselves when a second
  shop is added.
- All of FM1 to FM10 are in scope, in order, one PR each.
- Expense approval limit ₹5,000; adjustment approval limit ₹10,000 (gross value). Bank deposits
  need no PIN; FM7's bank matching checks them.
- ITC to reverse is advisory. It is listed for GSTR-3B 4(B)(1) but does not change the 3B
  figures, and the accountant splits it into CGST, SGST and IGST. Unexplained shortages are
  included by default (`itc_reverse_shortages`).
- Gross profit and contribution are after stock lost (adjustments and posted counts, less
  gains).
- Write-down to NRV (value without quantity) was deferred from FM2 to FM6.

## 9. Milestone notes (on top of FINANCE_REVIEW section 6)

**FM3, labelled rate overrides (F4).**
- Find where a sales line's rate is set (`services/sales.py`, `services/rates.py`) and record
  `rate_source` (market, customer rate, override). An owner override needs a reason, otherwise
  409 `OVERRIDE_REASON`.
- The bill PDF must not change (snapshot test, or compare bytes or text before and after).
- Add a small owner report or column showing overrides by user and their rupee effect against
  the market rate. That is the leak this milestone exists to show.

**FM4, Tally export (F5).**
- Export the day book as Tally XML (sales, purchases, receipts, payments, credit and debit
  notes, cash-book vouchers) for a date range. Owner and accountant only.
- Ledger names (sales, purchase, CGST, SGST, IGST, round-off, cash, bank, expense heads) are
  settings with sensible defaults; the accountant confirms them.
- Validate that the XML is well-formed. Add a test that the voucher totals equal GSTR-1 and the
  dues reports for the same month.
- Record in the PR body that a real Tally import needs the accountant.

**FM5, working capital and receivables (F7, F8, F9, F28).**
- DIO, DSO, DPO, advance days and the cash conversion cycle, using the hand-worked month in the
  acceptance test.
- Overdue aging by due date, not bill date.
- A bad-debt write-off flow:
  - an owner-only document;
  - no GST effect;
  - it reduces the receivable through `party_ledger`;
  - a provision % setting by bucket, accountant to confirm.
- The monthly COGS cross-check (F28) goes into `verify.py`.
- Add the owner-only **Metrics explained** page, generated from `/kpis/definitions`, with a
  GLOSSARY link. Add it to `modules.ts`.

**FM6, inventory analytics (F10 to F14).**
- ABC by value, FSN by movement, aging buckets, cover days and reorder point (1.2 t/day × 7 days
  lead + 2.4 t safety = 10.8 t). Lead time and safety days are settings per item or supplier.
- NRV: the market rate below WAC shows a loss.
- The write-down to NRV deferred from FM2:
  - a value-only adjustment, accountant to confirm (AS 2);
  - it must not count as movement in FSN;
  - it does not reverse ITC, because the goods still exist.
- Cement FIFO proxy (oldest week first, as a report). Shrinkage by supplier from weighbridge
  losses.
- Under 30 days of history: "Not enough data yet (needs 30 days)".
- Exclude adjustments from FSN movement.

**FM7, controls (F16, F17, F18, F24).**
- Bank statement CSV import and matching to receipts and deposits, with unmatched rows listed.
- An owner exception report:
  - round-number adjustments;
  - adjustments within 1 to 2 days before a count;
  - one customer with 4 or more returns in 30 days;
  - back-dated entries;
  - cash near the limit;
  - repeated weighbridge shortages from one supplier.
- An audit-log screen.
- A period lock setting: writes dated in a locked month return 409 `PERIOD_LOCKED`, applied in
  every service that writes dated documents. Search for `ensure_day_open` to find them.

**FM8, profitability cuts and GST health (F19, F29).**
- Profit per ton by brand, shop and user, matching hand totals.
- ITC at risk = ITC in books but not in GSTR-2B (reuse `services/gst_returns.py`).

**FM9, forecast and accruals (F21, F23, F27).**
- A 13-week cash forecast from due dates, GST due dates and the opex run-rate.
- Rebate accrual on supplier schemes, behind a setting (accountant to confirm; default: book
  when earned).
- Landed-cost variance against the expected cost.

**FM10, orders, lots and demand (F25, F26).**
- PO → GRN → bill three-way match within a tolerance setting.
- Cement lots by manufacturing week, issued oldest first.
- A lost-sales log ("asked for, out of stock") and the fill rate. Counter staff can log; the
  owner sees value.
- Keep this small. If the owner's answers in FINANCE_REVIEW section 7 are missing (cement week
  on bags, counter staff willing to log), build the smallest version and say so.

## 10. Out of scope

- The production steps waiting on the owner: GSP API keys, S3 storage, accountant month,
  production machine, backup drill.
- Any change to how bills are issued beyond what an FM needs. ADR 0005 applies: every bill is a
  real GST tax invoice, with no hidden or dummy billing.

## 11. How to work and report

- Do one milestone at a time:
  1. read;
  2. write the unit tests first;
  3. build the domain, then migration, services, API, screens, tests and docs;
  4. run the full suite and lint;
  5. commit, push the branch and open the PR;
  6. move to the next milestone.
- If the session runs long, finish and push the current milestone cleanly before starting the
  next. A half-built milestone must never be pushed as done.
- After each PR, post a short report beginning with the same first line as the PR body,
  followed by:
  - the PR link;
  - what the owner can now do;
  - any default chosen that the accountant or owner should confirm.
