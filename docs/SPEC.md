# Construction Materials ERP: Build Spec

**Version 1.1 (2026-10-09).** Source of truth for business rules, data model and behaviour.
Version 1.0 was the Claude Doc written with the owner interview; 1.1 adds the gap fixes
`G1`–`G27` from [GAP_ANALYSIS.md](GAP_ANALYSIS.md). When a rule changes, edit this file first,
then the code.

Related: [ROADMAP.md](ROADMAP.md) (milestones and status) · [ARCHITECTURE.md](ARCHITECTURE.md) ·
[API.md](API.md) · [DESIGN.md](DESIGN.md) · [GLOSSARY.md](GLOSSARY.md)

---

## 1. Overview

A web ERP for a new construction-materials business that bills on paper today: **two shops and
one godown**. Version 1 serves this single client and must go live fast. Multi-tenant SaaS
comes later, so every table already carries `tenant_id` (ADR 0004).

**Products:** TMT bars, MS square pipe, round pipe, cement, binding wire, angles and channels.

**What v1 must do**

- Purchase entry that computes the true landed cost of every item.
- Live stock per location with its value, and a check that catches weight shortages.
- GST billing, with a separate bill and statement per customer site.
- Credit control for a few approved daily customers (default limit ₹10,000, 7 days).
- Drop-ship sales: material goes from the supplier straight to the customer's site.
- About 50 e-way bills a day, a daily closing report per shop, GSTR-1 and 3B data for the accountant.
- The owner sees cost, margin and profit; counter staff do not.

**Permanently out of scope:** any bill that is hidden, unaccounted or not a real GST document.
Every invoice is a real tax invoice. Test data lives only in development or staging and is
marked `TEST` (G27, ADR 0005).

## 2. Users and roles

| Capability | Owner | Counter staff | Accountant |
| --- | --- | --- | --- |
| See selling price and stock availability | Yes | Yes | Yes |
| Create sales invoice | Yes | Own shop | No |
| Enter purchase | Yes | Own shop | No |
| See cost, margin, profit | Yes | **No** | No |
| Set rates, margins, customer rates | Yes | No | No |
| Discount, sell below cost, override credit | Yes | No (asks owner, G18) | No |
| Approve returns after 2 days | Yes | No | No |
| Record payments | Yes | Own shop | No |
| Daily closing | All shops | Own shop | View |
| Supplier payables, advances, schemes | Yes | No | View |
| GST exports and reports | Yes | No | Yes |
| Users, settings, audit log | Yes | No | No |

Permissions are enforced in the API (`app/api/deps.py`), not only hidden in screens. Cost,
margin and profit fields are removed from responses for non-owners (`Principal.sees_cost`).

## 3. Business rules

Each rule becomes at least one automated test. "Setting" means the value lives in
`shop_settings` or on the party/item record, never in code.

| ID | Rule | Where it lives |
| --- | --- | --- |
| B1 | Landed cost per base unit = (billed qty × rate + charges) ÷ **received** qty. Charges: unloading (from ₹250/ton), loading, weighbridge (₹150/weighing), transport rent, commission, others. GST is **excluded** unless `include_gst_in_cost` (G1). | `domain/landed_cost.py` |
| B2 | Each charge attaches to one purchase line (items arrive separately). Basis: per ton, per base unit (e.g. per bag), per trip, or flat. | `domain/landed_cost.py` |
| B3 | Selling rate = active customer-specific rate, else the latest daily market rate on or before the bill date. No rate → the line is blocked. Margin (₹1,000–1,500/ton, ₹1–1.5/kg) is owner-only, per item; the rate screen suggests cost + margin. | `domain/pricing.py` |
| B4 | Counter staff cannot see cost, margin or profit, and cannot change rates or discounts. | API layer |
| B5 | Selling below landed cost needs owner approval. Selling below cost + minimum margin warns the owner. | `domain/pricing.py` |
| B6 | Suppliers are mostly paid in advance. Advances sit on the supplier ledger, are adjusted against bills, and any excess carries forward. Some purchases are credit on delivery, with a due date. | M4, M7 |
| B7 | Payment modes: cash, UPI, bank transfer. No cheques. Cash receipts are capped by income-tax law (G14). | `domain/compliance.py` |
| B8 | Credit only for approved customers. Default limit ₹10,000 and 7 days (settings, editable per customer). Due date = invoice date + credit days. A credit sale is blocked (owner can override) when outstanding + unpaid part of the bill > limit, or any unpaid invoice is overdue. | `domain/credit.py` |
| B9 | A customer has several sites. Each invoice belongs to one site. Separate bill and statement per site, plus a combined customer statement. | M2, M7 |
| B10 | A sale line is fulfilled from shop stock, godown stock, or direct from supplier (drop-ship). Direct lines move no stock. Profit = sale − purchase − freight. | M9 |
| B11 | A customer return within 2 days (setting) goes back to stock at the original cost, with an automatic credit note. After that, owner approval. | `domain/compliance.py` |
| B12 | Each shop has its own staff, cash drawer and daily closing. The owner sees a combined view. After closing, that shop-day is locked (G17). | M12 |
| B13 | Stock cannot go negative at a location, except direct-from-supplier lines. | `domain/stock_valuation.py` |
| B14 | Billed vs weighbridge weight (purchases) and billed vs slip weight (sales): variance above `weight_variance_pct` (default 0.50%, G20) flags the document and needs a note. | `domain/weight_check.py` |
| B15 | Supplier target schemes: volume target per period; progress updates on each purchase; alert at 80%; rebate recorded as a supplier credit note when earned. | M11 |
| B16 | Issued documents are never deleted or edited in place. Numbers are gapless per location, document type and financial year (April–March), at most 16 characters (G4). Corrections use credit or debit notes. Every change is audit-logged. | `services/numbering.py`, `services/audit.py` |
| B17 | Weighbridge slips and delivery proof are attached to purchases, sales and trips. | M11 |
| B18 | Transport is by hired vehicles today. Freight is payable to the vehicle owner. Vehicles carry an `is_own` flag for the future. | M9 |

Gap-fix rules added in 1.1 (details and status in GAP_ANALYSIS.md): G1 GST out of cost ·
G2 rates exclusive of GST by default · G3 rounding · G4 16-character numbers · G5 place of
supply · G6 company-wide average cost · G7 theoretical weight per piece · G8 brands ·
G9 purchase returns and debit notes · G10 discounts · G12 e-invoicing readiness ·
G13 e-way thresholds and ship-to GSTIN · G14 cash limits · G15 72-month retention ·
G17 day lock · G18 owner approvals · G19 idempotency.

## 4. Data model

Every table: `id`, `tenant_id` (default 1), `created_at`, `updated_at`, `created_by`,
`updated_by` (where it is a business record). Money `NUMERIC(14,2)`, quantity `NUMERIC(14,3)`,
unit cost `NUMERIC(14,4)`. Stock, balances and average cost are **derived from ledgers**, never
stored as editable numbers. Enums are `VARCHAR` + `CHECK`.

**Built (Milestone 1):** `shop_settings`, `location`, `app_user`, `user_location`,
`auth_session`, `audit_log`, `document_sequence`. A GSTIN is checked for format and check
digit, and its first two digits must equal the state code it is stored with. A location code
cannot change once created (it is printed inside document numbers).

**Built (Milestone 2):** `item`, `item_unit`, `party`, `site`.

- `item.base_whole_only` (added to the model above): bags and pieces are counted in whole
  numbers, so a conversion that would give 30.2 bags is refused. `item.base_unit` cannot change
  once the item exists.
- Units: the base unit is implicit (factor 1); `item_unit` lists the others. When an item is
  counted in kg and has `weight_per_piece_kg`, "piece" is available automatically (G7).
- `item.min_margin` is owner-only: counter staff and the accountant get `ItemOut`, the owner
  `ItemOwnerOut` (B4). Items are created and edited by the owner only; everyone can read them.
- Credit terms on a party (`credit_allowed`, `credit_limit`, `credit_days`) are set by the owner
  only (B8); a null limit or days means the shop default from `shop_settings`. Counter staff
  can create and edit customers and sites. A supplier has no sites, segment or credit.
- A site with no GSTIN prints "URP" on e-way bills (G13). A GSTIN's first two digits must match
  its state code, on shop settings, parties and sites.
- Excel import: one row per item, columns `name, category, brand, hsn, gst_rate, base_unit,
  base_whole_only, size, grade, weight_per_piece_kg, min_margin, units` (`units` is
  `unit:factor[:whole]` separated by commas). Same name updates the item; one bad row refuses the
  whole file; `dry_run=true` checks without saving.

**Built (Milestone 3):** `opening_balance`, `stock_ledger`, `party_ledger` (see ADR 0006). The
stock ledger moved here from Milestone 4 because opening stock is its first writer.

- `opening_balance.kind`: `stock`, `receivable` (a customer owes us), `customer_advance`,
  `payable` (we owe a supplier), `supplier_advance`. Draft until posted, then locked.
- `party_ledger` replaces the `v_party_ledger` view of the first spec; balances and aging are
  computed by `domain.ledger` (aging buckets 0-30, 31-60, over 60 days since the bill).
- Both ledgers are append-only, enforced by database triggers.
- Supplier payables, advances and what we owe are visible to the owner and accountant, not to
  counter staff; customers' dues are visible to all three roles.

**Built (Milestone 4):** `cost_component`, `purchase`, `purchase_line`, `purchase_cost`,
`payment` (supplier side), `stock_transfer`, `stock_transfer_line`, `stock_count`,
`stock_count_line`; `shop_settings.counter_can_enter_purchases` (G28). See ADR 0007.

- A purchase line is entered in any unit of the item (ton, bag...) and converted to the base unit;
  `goods_value` is the bill's own amount (quantity x rate in the entered unit, to paise), so a
  per-ton price never loses paise. `received_qty` (weighbridge) is what enters stock and divides
  cost, so a shortage raises the unit cost (B1).
- Charges attach to a line (B2) and are priced per ton, per base unit, per trip or flat. A charge
  flagged "on supplier's bill" is added to what we owe the supplier; others are cost only.
- Purchase number: `<location code>P/<FY>/<5 digits>`; transfers `<code>DC/...`; payments
  `<code>R/...`. A supplier's bill number is unique per supplier.
- A transfer is an out and an in at the company average cost, so it never changes value (G6),
  and the origin must hold the quantity (B13). A count's variance is posted at the average cost
  as an adjustment; only the owner posts, and only the owner sees rupee variances.
- Mode `direct` writes the supplier payable but no stock rows (Milestone 9 links it to a sale).

**Built (Milestone 5):** `market_rate`, `customer_rate`, `item_margin`.

- Rates are stored per base unit, excluding GST, to 6 decimals (G2). The owner types them in the
  unit he quotes in (per ton for steel, per bag for cement); with `rates_include_gst` on, the tax is
  backed out first (118 incl 18% is 100). The typed value and unit are kept for display.
- One market rate per item per day; re-entering the day overwrites it. The latest on or before the
  bill date applies; a rate dated in the future is ignored. A customer rate beats the market rate
  while active; two active customer rates for one customer and item cannot overlap.
- Margin is entered per ton (or per unit) and stored per base unit; suggested rate = average cost +
  margin. Saving a rate below cost or below the item's minimum margin returns a warning to the owner.
- Counter staff and the accountant can read the selling rate and resolve a price; they never
  receive cost, margin, suggestion or flags. Customer rates and margins are owner-only.

**Built (Milestone 6):** `sales_invoice`, `sales_line`; Walk-in customer party seeded.

- Saving a bill is one transaction: advisory locks on its items (so two counters cannot sell the
  last bag together, B13), price from rates (B3), tax per line then totals with a round-off line
  (G3), next gapless number, stock-out rows at the average cost, receivable debit on the
  customer's account (and site), commit.
- Place of supply is the ship-to site's state, else the billing shop's; the seller state is the
  shop settings' state; same state means CGST + SGST, otherwise IGST (G5). A customer with a GSTIN
  makes a B2B bill, otherwise a B2C tax invoice: still a real bill (ADR 0005).
- Counter staff cannot choose a price, give a discount or back-date; the API answers 409
  `DISCOUNT_NEEDS_OWNER` or `BACKDATE_NEEDS_OWNER` with `requires_owner_approval` (owner PIN in
  Milestone 7). A price below average cost needs the owner (`BELOW_COST`, message without figures).
  Owner discounts need a reason (G10).
- Each line keeps the average cost at the time (`cost_per_unit`); profit per line and bill is
  taxable less cost and is shown to the owner only. A bill also keeps the customer's pending
  balance and the stock left after each line, for printing.
- `Idempotency-Key` on create: a repeat returns the first bill; the same key for another customer
  or shop is a conflict (G19).
- A4 PDF: `GET /invoices/{id}/pdf?copy=` via WeasyPrint, template `app/templates/invoice_a4.html`
  behind the `InvoiceRenderer` interface (a thermal layout can be added). Outside production the PDF
  carries a TEST watermark (ADR 0005).

**Built (Milestone 7):** `approval`; `app_user.pin_hash`; `party_ledger.applies_to`;
`sales_invoice.paid_at_billing`. The planned `payment_allocation` table is not needed: a payment's
allocation is its ledger rows (ADR 0008).

- Credit (B8): a bill's unpaid part (total less money taken with it) is checked against the
  customer's approval, limit (customer's own, else the shop default) and overdue bills. The API
  answers 409 `CREDIT_NOT_ALLOWED`, `CREDIT_LIMIT_EXCEEDED` or `OVERDUE_INVOICES` with
  `requires_owner_approval`. The owner may bill anyway (an audit `override` event records the rule).
- Approvals (G18): owner PIN, one use, ten minutes, for one customer; actions `credit_override`,
  `below_cost`, `discount`, `backdate`. Wrong-PIN lockout after five tries.
- Receipts: counter staff (own shop) and the owner record money received; only the owner pays
  suppliers. Bills the user ticks are paid first, the rest oldest first, extra money is an advance
  (G21). Cash from one customer in a day at or above the limit is refused (G14), cash taken with
  a bill included. No cheques (B7).
- Money can be taken with the bill: one receipt per mode, applied to that bill, printed as
  "Paid at billing" and "Balance due".
- Statements per customer site balance with the combined statement (B9).

**Built (Milestone 8):** `credit_note`, `credit_note_line`, `debit_note`, `debit_note_line`. There is
no separate "return" table: the note is the return document (B16), and what has come back on a
line is the sum of its note lines.

- Credit note (B11): taken for part of one invoice, by counter staff at their own shop or the
  owner. Inside `return_window_days` (default 2) it needs no approval; later it needs the owner
  or a `late_return` PIN approval (409 `RETURN_WINDOW_CLOSED` with `requires_owner_approval`).
  Quantities are in the line's own unit and cannot exceed what is left (422 `RETURN_TOO_MUCH`).
- Value is pro rata to quantity on the line's taxable value (a whole-line return reverses it
  exactly); GST is worked out again per line with the invoice's supply kind; round-off per note.
  Stock goes back to the location it left at the cost it left at; lines delivered direct from a
  supplier restock nothing. The customer's receivable is credited against that invoice number.
- Debit note: owner only. Taxable value is pro rata to the billed quantity on the supplier line,
  GST by supplier state against shop state. Stock leaves at the line's landed cost and cannot
  exceed what is held (B13, 409 `INSUFFICIENT_STOCK`; direct purchases touch no stock). The
  supplier payable is debited against the purchase number. Accountant may read debit notes.
- Numbers: `<location>C/<fy>/<seq>` for credit notes and `<location>D/<fy>/<seq>` for debit
  notes. Notes print as A4 PDFs with the TEST watermark outside production.

**Built (Milestone 9):** `vehicle`, `trip`, `drop_ship_link`.

- Direct lines (B10, B13): a bill line with source "direct" moves no stock. It may name the
  supplier purchase line (mode `direct`, same item, enough unclaimed quantity) at billing, or the
  owner links it later. The link copies the purchase line's landed cost, so profit stays fixed.
  Profit = sale taxable − quantity × landed cost − freight of the trips on that bill. An unlinked
  direct line is costed at the average cost until linked, and is flagged in the direct-sales
  report. Counter staff may name a purchase from a cost-free list but never see supplier or cost.
- Vehicles (B18): hired ones get a supplier account named "Transport: owner (number)" so freight
  is paid through the normal payments screen; own vehicles (`is_own`) carry no freight.
- Trips: owner records a run (optionally for a sale or a purchase, not both). Freight credits the
  vehicle owner's payable as `TRIP-<id>`; a payment aimed at that reference shows as paid on the
  trip. Trips on a purchase only record the payable (its charge is already in landed cost).
- Cash payments to one person above ₹35,000 a day answer with a warning, not a block (G14).

**Built (Milestone 10):** `eway_bill`, `einvoice` (ADR 0009).

- E-way bill from a saved invoice: Part A from the invoice (shop GSTIN required; buyer GSTIN or
  "URP"; ship-to when delivered), distance and both pincodes typed by the user, optional vehicle
  (Part B) added or changed later. Validity is one day per 200 km or part (to midnight of the last
  day); cancel only within 24 hours, owner only. `required` is shown against the shop thresholds
  (G13) but making one below the threshold is allowed.
- One live bill per invoice; a cancelled one may be replaced. Provider failures save nothing
  (502, retryable). A bill made on the portal by hand can be recorded by number (fallback).
- `GET /eway-bills/pending` lists delivered bills over the threshold with no live bill;
  `POST /eway-bills/batch` makes many, each succeeding or failing alone.
- E-invoice: only when `einvoice_enabled` and the buyer has a GSTIN. The IRN, acknowledgement
  and QR print on the A4 bill; cancel within 24 hours, owner only. Credit and debit notes carry
  no IRN yet.
- Running costs: the GSP's price per bill is unknown (GAP_ANALYSIS open question).

**Built (Milestone 11):** `attachment`, `supplier_scheme`; `purchase_line` and `sales_line` gain
`weight_variance_pct`, `weight_flagged`, `weight_note` (and `slip_weight` on sales).

- Weight check (B14, G20): on a purchase line, billed against received quantity; on a sale line,
  billed against an optional slip weight. Above `weight_variance_pct` the line is flagged and
  saving needs a note (409 `WEIGHT_NOTE_REQUIRED`, field `lines[i].weight_note`). The shortage
  value (at the supplier's bill rate) is owner-only. A slip does not change the billed quantity (G30).
- Attachments (B17): weighbridge slips, delivery proof and other papers on purchases, bills and
  trips. Photos (JPEG, PNG, WebP) and PDF only, decided from the bytes, up to `MAX_UPLOAD_MB`
  (8), at most 20 a document, stored under a generated key behind `services/storage` (a folder,
  `STORAGE_DIR`), checked by SHA-256 on every read, never deleted. Counter staff: their own shop's
  purchases and bills; trips owner only (accountant reads).
- Supplier schemes (B15): item or category, a target in the base unit, a period and a rebate
  rule (percent of goods bought, rupees per unit, or flat). Progress is calculated from purchases
  in the period less debit-note returns (never stored); alert at 80% to the owner. When the target
  is met the owner books the rebate once as a debit on the supplier's payable (G29).

**Built (Milestone 12):** `daily_closing` (the cash drawer is part of it, so there is no separate
`cash_drawer` table).

- Daily closing per shop and day (B12, G17): figures from the day's bills, credit notes and
  receipts (cash, UPI, bank), cash paid out, items sold and the first and last bill numbers.
  The drawer is opening cash (the last count; entered by hand for a shop's first closing) plus
  cash received less cash paid out; the counted cash is typed in and any difference needs a note
  (409 `CASH_NOTE_REQUIRED`). The PDF carries no cost or profit, so staff can close their own shop.
- The PDF is saved date-wise (`closing/<shop>/<yyyy>/<mm>/<date>.pdf`) to storage: a local folder
  or an S3-compatible bucket (`STORAGE_PROVIDER`). If saving fails the day is not closed.
- Day lock: once closed, bills, purchases, payments, credit and debit notes, transfers, stock
  count posting and trips dated on that shop-day are refused (409 `DAY_CLOSED`); other shops and
  days are untouched. Only the owner reopens a day, with a reason (audit `override` event); it can
  then be closed again (the PDF is replaced and `times_closed` counts).
- Today: items in stock, what customers owe, what we owe (not for counter staff), sales today,
  profit today (owner only); counter staff see their own shop's sales.
- Profit (owner): sales less returns, less average cost (or the linked supplier cost for direct
  sales), less freight shared over a bill's lines by value; by item, customer or site, up to a year.
- Sales by customer segment (owner, accountant): monthly bars for a financial year, net of returns;
  customers without a segment fall under "No segment".

**Built (Milestone 13):** `gstr2b_import`. All return figures are rebuilt from issued documents on
each request, so they always agree with the books.

- GSTR-1 for a month: B2B (buyer GSTIN), B2CL (unregistered, between states, over ₹1,00,000),
  B2CS (all other B2C, by supply type, place of supply and rate, net of returns on those bills),
  CDNR (credit notes to registered buyers), CDNUR (credit notes on B2CL bills), HSN summary (net
  of returns, GST quantity code from the unit), document series summary with any missing numbers
  (there should never be any). Download as the portal's offline-tool JSON or as an Excel workbook
  with one sheet per table. `gt` and `cur_gt` (turnover) are left 0 for the accountant to fill.
- GSTR-3B figures: 3.1(a) sales at a rate net of credit notes, 3.1(c) sales at 0%, 4(A) input tax
  on the month's purchases (heads from supplier state against the shop's), 4(B) input tax taken
  back on debit notes, the input tax the uploaded 2B shows, and tax to pay per head. Reverse
  charge, imports, interest and late fees are not modelled.
- GSTR-2B: upload the portal's JSON or a simple CSV (`gstin, supplier, invoice_no, invoice_date,
  taxable, igst, cgst, sgst`). The newest upload for a month is kept (older ones stay for the
  record). Our purchase bills (from suppliers with a GSTIN, the month and the two before it) are
  matched by GSTIN and bill number (case, spaces and punctuation ignored); amounts within ₹1 count as
  equal. Results: matched, amounts differ, in books not in 2B, in 2B not in books.
- Owner and accountant only; the accountant can upload 2B files.

**Built (Milestone 14):** no new business tables. Database triggers `*_no_delete` and `*_no_edit`
on issued documents (ADR 0010).

- Issued documents (bills, credit and debit notes, purchases and their lines, payments, transfers,
  e-way bills, e-invoices, closings, attachments, 2B imports) cannot be deleted, and the figures of
  bills, notes, purchase lines, payments and attachments cannot be edited; only `updated_at` and
  `updated_by` move.
- `python -m app.scripts.verify [--full]`, `POST /system/verify` and Settings, System: integrity
  checks listed in the ADR. `GET /system/status` (owner): database version, newest backup age
  (fails over 30 hours), file storage, e-way provider, shops whose previous day is not closed.
- Backups: dump plus files archive, off-site copy script, restore drill, restore script that also
  restores files and runs the check. `python -m app.scripts.reset_password <user>` for a forgotten
  owner password, from the server only.
- Every route needs a sign-in (except sign-in, refresh, logout and the health checks); API
  answers are `Cache-Control: no-store`.
- Operations documents: [RUNBOOK](RUNBOOK.md), [GO_LIVE](GO_LIVE.md).

**Built (FM1, finance review F1, F2, F6):** `expense_category`, `cash_entry`;
`shop_settings.expense_approval_limit` (default ₹5,000). See
[FINANCE_REVIEW.md](FINANCE_REVIEW.md).

- Cash book: vouchers `<location>V/<FY>/<seq>` for an expense (with a head), cash taken to the
  bank, cash brought from the bank, the owner's drawing or capital. Mode cash, UPI or bank;
  deposits and withdrawals are always cash. Vouchers are permanent (triggers); a mistake is
  undone by an owner's reversal voucher dated today, which points at the original.
- Counter staff record expenses and bank deposits at their own shop, dated today; an expense
  above the limit needs the owner's PIN (`expense` approval). The owner records everything and
  may back-date; closed shop-days refuse vouchers (G17). The accountant reads.
- Daily closing: cash in = cash receipts + cash from the bank + owner's capital; cash out = cash
  paid to parties + cash expenses + deposits + drawings. A normal day closes with no difference.
- Expense heads have a nature: fixed, variable or interest (defaults seeded, owner edits).
- Profit and loss per calendar month (owner): net sales, COGS, freight, gross profit, expenses
  by head, EBITDA, interest, net profit, contribution and break-even sales
  (`domain/finance.py`). Nothing is stored; with no data it says "Not enough data yet".
- KPI catalogue (`domain/kpi_catalogue.py`, `GET /kpis/definitions`) drives the names,
  formulas and "what this means" lines in the app.
- Today shows net sales excluding GST and returns (was the GST-inclusive bill total).
- One shop and the godown by default (`SEED_SHOPS=2` for two); shop pickers hide while there
  is one shop and appear when a second is added.

**Built (FM2, finance review F3, F15):** `stock_adjustment`, `stock_adjustment_line`;
`stock_ledger.reason`; `shop_settings.adjustment_approval_limit` (default ₹10,000) and
`itc_reverse_shortages` (default on, accountant to confirm).

- Stock adjustment documents `<location>A/<FY>/<seq>`, one reason each: breakage, rust or
  damage, theft, free sample, weighbridge loss (stock out), weighbridge gain (stock in), count
  correction (either way, per line). Lines move stock at the weighted-average cost
  (`ref_type = stock_adjustment`); out lines cannot take stock below zero (B13). Documents
  and lines are permanent (triggers); a mistake is fixed by another adjustment.
- Every adjustment ledger row carries its reason (a CHECK allows a reason only on adjustment
  rows). Posting a stock count now writes `count_correction`; counts posted before FM2 have no
  reason and are read as count corrections. No existing ledger row is changed.
- Counter staff adjust their own shop, today only; above the limit (gross value of all lines)
  they need the owner's PIN (`stock_adjustment` approval). The error never shows the value.
  The owner adjusts any place and may back-date into open days. The accountant reads.
- Values, totals by reason and ITC are owner-only on the adjustments screen.
- ITC to reverse (owner, accountant), per month from the ledger: goods lost, stolen, damaged or
  given as free samples (s.17(5)(h)) always; count and weighbridge shortages when
  `itc_reverse_shortages` is on. Value at average cost × the item's GST rate. Advisory for
  GSTR-3B 4(B)(1): the 3B figures are not changed, and the accountant splits it into heads.
- Profit and loss: gross profit and contribution are after stock lost (adjustments and counts,
  less gains) (`domain/inventory_analytics.py`).
- Deferred: write-down to realisable value (value without quantity) moves to FM6 with NRV.

**Built (FM3, finance review F4, F24 in part):** `sales_line.list_rate`,
`sales_line.rate_override_reason`; `rate_source` gains `override`.

- A price typed on a bill (`rate_override`, owner, or counter staff with the owner's PIN
  approval) is saved with `rate_source = override`, not `market`. A reason is required: the
  bill is refused with 409 `OVERRIDE_REASON`, and a CHECK refuses an override line without a
  reason, so no route round the service can save one. A reason is stored only on overrides.
- Every new line keeps `list_rate`: what the system would have charged (the customer's rate, else
  the market rate on the bill date), per base unit, excluding GST. Bills issued before FM3 have
  it blank and are never edited, so their effect shows as "no rate to compare with".
- The printed bill is unchanged: it shows the rate, never how it was chosen (tested by comparing
  the bill HTML of a typed and a board-priced bill).
- Price overrides report (owner only, per month and shop): rupees given away = (list rate −
  billed rate) × base quantity per override line (`domain/finance.override_effect`); cuts and
  raises are shown apart; discount leakage = cuts + bill discounts; price realisation = billed
  value ÷ list value on hand-priced lines. By person means the user who saved the bill. KPIs
  `discount_leakage` and `price_realisation_pct` (owner only) are in the catalogue.
- The rest of F24 (realisation on every line, per item and customer) stays in FM7.

**Built (FM4, finance review F5):** `tally_ledger` (the accountant's ledger names, one row per
changed purpose, plus `company`); audit action `export`.

- Tally day-book export for a date range (at most 366 days), owner and accountant only
  (`domain/tally.py`, `services/tally.py`). Each issued document becomes one balanced voucher
  (debits equal credits, or the export is refused): bills (Sales), credit notes, supplier bills
  (Purchase), debit notes, receipts and payments (Cash for cash, Bank for UPI and transfers),
  cash-book entries (expenses are Payments, bank deposits and withdrawals are Contras, drawings
  and capital are Payments and Receipts; a reversal is posted the other way round), and
  supplier rebates and freight as Journals. Opening balances are not exported: Tally carries its
  own. Stock is not exported: Tally holds accounts only, no items.
- Bills post party, Sales, CGST, SGST or IGST and round off; purchases post Purchases (supplier
  payable less input tax, so charges on the supplier's bill sit there), input tax and the supplier.
  Input tax per head is worked out the same way as GSTR-3B.
- Ledger names are settings (`GET/PUT /tally/ledgers`), with defaults the accountant confirms:
  Sales, Purchases, Output and Input CGST, SGST, IGST, Round off, Cash, Bank, Owner's Drawings,
  Owner's Capital, Rebate Received, Freight; the company name defaults to the shop's legal name.
  Two ledgers may not share a name. Party ledgers use the party's name; expense heads use the head
  names. The file starts with the ledger masters (optional) so Tally finds every ledger a voucher
  uses, then the vouchers, each with a GUID built from type and number so a second import of the
  same file adds nothing.
- Checks, shown before the download and enforced by it (409 `EXPORT_MISMATCH`): the change in what
  customers owe and what we owe equals the change in the dues reports (party ledger, opening rows
  excluded); and, for ranges of whole months, sales taxable value and output tax equal GSTR-1, input
  tax equals GSTR-3B 4(A) less 4(B).
- Every export is audited. Real Tally has not been tried: the accountant imports one month into a
  test company before relying on it (docs/GAP_ANALYSIS.md).

**Built (FM5, finance review F7, F8, F9, F28):** `bad_debt_writeoff`; party ledger ref `write_off`;
number series `W`; `shop_settings.provision_pct_*` (not yet due 0, 1-15 days 1, 16-30 days 2,
31-60 days 10, over 60 days 50; accountant to confirm).

- Working capital for a calendar month, owner only (`GET /reports/working-capital`). Averages are
  of the balance at the end of the day before the month and at its end (today for this month).
  Stock at cost is replayed from the stock ledger as at each date. Receivables and payables are
  summed per party; a party in credit counts as an advance, not a negative due. DIO = average stock
  ÷ COGS x days; DSO = average receivables ÷ credit sales x days (credit sales = bills less what
  was paid with the bill, GST included); DPO = average payables ÷ purchases (net of debit notes);
  advance days = average supplier advances ÷ purchases; CCC = DIO + DSO + advance days - DPO from
  the days as shown (1 decimal). A day count is blank when there is nothing to divide by. With
  fewer than 7 days of bills in the month nothing is calculated: "Not enough data yet".
- Cash tied up = stock + receivables + supplier advances at month end. Working capital = that
  less payables; it leaves out cash and bank balances until bank statements are imported (FM7).
  Collection efficiency = collections ÷ (opening receivables + credit sales), where collections
  exclude money taken with the bill. Inventory turnover = COGS ÷ average stock (per month).
- Receivables aged from each bill's due date (`GET /reports/receivables`, owner and accountant):
  not yet due, 1-15, 16-30, 31-60 and over 60 days late; opening balances are due the day they
  start. Per customer: overdue, days late, credit used (outstanding ÷ credit limit; blank without
  credit), days to pay over the last 90 days, last payment. The provision (each bucket x its
  percentage) is owner only and is a report, not a booking: the P&L is not changed by it. The
  existing dues report (aging from the bill date) is unchanged.
- Bad-debt write-off (`POST /write-offs`, owner only): customer, shop, amount no more than the
  customer owes (409 `WRITEOFF_TOO_MUCH`), reason. It credits the receivable account (so the
  oldest bills clear first), has no GST effect and is not a credit note: GSTR-1 and GSTR-3B do not
  change. It is permanent (triggers) and numbered `<shop>W/<FY>/<seq>`. It comes off net profit
  in the month it is written off (`bad_debts` on the P&L; not in EBITDA, contribution or
  break-even). A customer who pays later makes an ordinary receipt. The Tally export posts it as a
  Journal: Dr "Bad Debts Written Off", Cr the customer.
- Integrity check "Cost of goods" (F28): for last month and this month, opening stock + purchases
  (bills) - cost of goods sold (bills, not direct sales) + other stock moves (ledger) must equal
  the stock ledger's closing stock, within 0.01% of what moved (minimum ₹10) for unit-cost
  rounding. Also checks write-offs against the party ledger and write-off numbers for gaps.
- Metrics explained (owner): `/metrics`, built from `GET /kpis/definitions`.
- Deferred: bank and cash balances in working capital (FM7); booking the provision; reversing a
  write-off (a later payment covers it).

**Built (FM6, finance review F10 to F14):** `stock_writedown`, `stock_writedown_line`; stock ledger
ref `stock_writedown`; number series `N`; `item.lead_time_days`, `item.safety_days`,
`party.lead_time_days`; `shop_settings.default_lead_time_days` (7), `default_safety_days` (2),
`fsn_fast_min_days` (15), `nrv_selling_cost_pct` (0), `nrv_writedown_enabled` (on; accountant to
confirm AS 2).

- Analysis (`GET /inventory/analytics`, owner): per item, rebuilt from the stock ledger. Movement
  means a purchase, sale or return (and opening stock); adjustments, count corrections, transfers
  and write-downs never count, so a theft entry cannot make dead stock look alive. Aging buckets
  0-30, 31-90, 91-180, over 180 days since the last movement, at cost. FSN: fast when it sold on
  at least `fsn_fast_min_days` of the last 90 days, slow when on at least one, else non-moving.
  ABC on the cost of what sold in 90 days: A while the share of items ranked above is under 80 %,
  B under 95 %, then C; items with no sales get no class. Average daily sales = quantity sold in
  the last 30 days ÷ 30; cover = on hand ÷ that; reorder point = daily x lead days + daily x
  safety days (1.2 t x 7 + 1.2 t x 2 = 10.8 t); an item is reordered when on hand is at or below
  it. Lead time comes from the item, else the supplier of its last purchase, else the shop;
  safety days from the item, else the shop. With fewer than 30 days since the first bill or
  purchase, classes, speed, cover and reorder points are blank and the page says "Not enough data
  yet (needs 30 days)". Not built: safety stock from demand variation after 90 days.
- Cement by age (`GET /inventory/fifo-age`, owner): for cement items, each day's receipts less
  sales and losses taken oldest first, shown by age (0-30, 31-60, 61-90, over 90 days). An
  estimate: there are no lots until FM10.
- Stock value (`GET /inventory/nrv`, owner and accountant): market rate on the rate board less
  `nrv_selling_cost_pct` is the net realisable value; loss = (average cost - NRV) x quantity when
  positive, never a gain; holding gain or loss = (last purchase landed cost - average cost) x
  quantity. Items with no rate show no NRV: nothing is guessed.
- Write-down to NRV (`POST /inventory/writedowns`, owner only, behind `nrv_writedown_enabled`):
  a permanent document `<shop>N/<FY>/<seq>` for chosen items. It writes the stock out at the old
  average and back in at the NRV at every place, so the average becomes the NRV, no quantity moves
  and no stock adjustment or input tax is involved (ITC to reverse is unchanged). It is not
  movement for FSN or aging. The loss is `write_downs` on the P&L, off net profit (not gross
  profit, EBITDA or break-even). Refused: no market rate (`NO_MARKET_RATE`), not worth less than
  cost (`NOTHING_TO_WRITE_DOWN`), switched off (`WRITEDOWN_DISABLED`). A further fall is a new
  document. Cost of goods check and ledger checks include write-downs. Not exported to Tally,
  which holds accounts only: the accountant values closing stock from the Stock value report.
- Weight shortages (`GET /inventory/shrinkage`, owner and accountant): purchase lines where the
  weighbridge showed less than the bill, by supplier (share of the value billed, rupees) and as a
  claims list; shortage value = goods value x (billed - received) ÷ billed. 90 days by default.

**Built (FM7, finance review F16, F17, F18):** `bank_account`, `bank_statement`,
`bank_statement_line`; `shop_settings.locked_through`, `bank_match_days` (3),
`exception_round_amount` (₹1,000), `exception_count_days` (2), `exception_returns_count` (4),
`exception_returns_days` (30), `exception_cash_near_pct` (80), `exception_shortage_count` (3).

- Period lock (`PUT /period-lock`, owner): `ensure_day_open` (every service that dates a
  document) first refuses any date on or before `locked_through` with 409 `PERIOD_LOCKED`; bad-debt
  write-offs and rebate booking, which had no day check, now check the lock too. Reopening (an
  earlier date, or none) needs a reason; each change is an audit event (`period_lock`) with
  from, to, reason. The settings form never carries the lock. Opening balances are not locked.
  Accountant to confirm whether to lock after GSTR-1 or after GSTR-3B. A month-end checklist
  (days closed, GSTR-2B imported, bank reconciled, exceptions) is advice only.
- Bank statements: any bank's CSV; the header row is found by column names (date, narration,
  reference, debit or withdrawal, credit or deposit, balance), dates as dd/mm/yyyy, dd-mm-yy,
  yyyy-mm-dd or dd-Mon-yyyy, commas in amounts allowed. One bad row refuses the whole file and
  names the lines. The same file twice is refused; rows already held from an overlapping file are
  skipped (counted per identical row, so two real equal rows both stay). Statements and lines are
  permanent (triggers). Owner and accountant upload; only the owner adds accounts.
- Matching is not stored: it is worked out when read (`domain/controls.match_statement`). A line
  pairs with at most one entry of the same direction and amount within `bank_match_days`;
  references are paired first (a UPI or bank reference of 4 or more characters found in the
  narration), then the nearest date. Entries considered: receipts and supplier payments by UPI
  or bank, cash deposits and withdrawals, and expenses, drawings and capital paid by UPI or
  bank. A voucher and its reversal are both left out. With several bank accounts the line is
  matched against all entries (entries do not name an account). Left over on each side:
  lines with no entry, and entries not on the statement.
- Exception report (owner, `domain/controls`, `services/exceptions`): round-number adjustment
  (value of all lines at average cost is a multiple of the step, at least one step); adjustment 0
  to N days before a stock count at the same place; N or more credit notes to one customer inside
  M days; entries (bills, receipts, vouchers, adjustments) dated at least a day before they were
  keyed in (IST); cash from one customer in a day at or above the given % of the cash limit; N or
  more purchase lines in 90 days where the weighbridge showed less than billed. Thresholds are
  settings; zero switches a rule off. Nothing is stored.
- Audit-log screen (owner): filters by record kind, action, user and dates, with before and after.
- KPIs `bank_unmatched_lines`, `bank_not_received`, `bank_statement_balance` (owner and
  accountant) and `exceptions_flagged` (owner).
- Not built: price realisation per item, customer and user on every line (the rest of F24);
  month-end snapshot; matching to a named bank account; reading PDF or Excel statements.

**Built (FM8, finance review F19, F29):** no new tables or settings; two reports.

- Profit cuts (`GET /reports/profitability`, owner; `services/profitability.py`): for a calendar
  month and optional shop, grouped by brand (blank brand is "No brand"), shop, user (who saved the
  bill; a credit note follows its bill), item or customer. Built from the same lines as the profit
  and loss (`services/reports._lines`: sold lines, credit-note lines as negatives, drop-ship cost
  from the link), with each bill's freight shared over its lines by taxable value
  (`reports.freight_shares`). Quantity: items whose base unit is kg are counted in tons
  (`finance.tons`), everything else in its base unit apart, so profit per ton uses only the lines
  sold by weight and profit per bag only the others. Rows add up to gross profit before stock
  lost (breakage, theft, shortages belong to no bill); the foot subtracts it once and equals the
  P&L gross profit for the same month and shop (asserted for every cut and for each shop in
  tests). `contribution_per_ton` (net sales - COGS - freight - variable expenses - stock lost, over
  tons) is shown only when every sale was by weight; otherwise `null` with a note, because a
  business-wide per-ton figure over mixed units would mislead. No quantity gives `null`, not 0.
- Profit and loss fix: freight now counts only bills sold in the month, so a credit note for an
  older bill no longer charges its freight twice.
- ITC at risk (`GET /gst/itc-at-risk`, owner and accountant): bills from suppliers with a GSTIN in
  the books (this month and the two before) are matched with `gstr.reconcile` against the latest
  GSTR-2B imported for the month and the two before it. In books, not in 2B = `missing_in_2b`
  (the bill's whole input tax); amounts differ = the books tax less the portal tax where positive.
  The two are shown apart and added for `at_risk_total`. An older bill is judged only if its own
  month has a 2B. Bills from suppliers with no GSTIN can never be in 2B and are shown as a note,
  not added. With no GSTR-2B for the month: `has_2b: false`, "No GSTR-2B imported for this month",
  no figure. The GST payable estimate is the GSTR-3B net payable for the month (to date while the
  month is open) due on the 20th of the next month, with the payable if the at-risk input tax
  cannot be claimed.
- KPIs `profit_per_ton`, `contribution_per_ton` (owner only), `itc_at_risk` and
  `gst_payable_estimate` (owner and accountant).
- Not built: profit cut by segment, a trend across months, a debit-note adjustment of the at-risk
  figure.

**Built (FM10, finance review F25, F26):** `purchase_order`, `purchase_order_line`,
`goods_receipt`, `goods_receipt_line`, `sales_line_lot`, `lost_sale`; `purchase.purchase_order_id`,
`purchase.match_approval_id`, `purchase_line.mfg_week` and `mfg_year`; number series `O` (order) and
`G` (receipt); approval action `po_mismatch`; `shop_settings.po_qty_tolerance_pct` (1) and
`po_rate_tolerance_pct` (0.5). FM9 (forecast and rebate accrual) was dropped by the owner.

- Orders (`services/orders.py`, owner places them; they carry rates). Order, receipt, lot and
  lost-sale rows are permanent (triggers); a mistake is a new document. A goods receipt records
  what arrived (counter staff, their shop, today; the owner may back-date) and moves no stock:
  stock enters with the supplier's bill, as before. Order status is read, not stored: open until
  every line is received, received until every item is billed, then billed.
- Three-way match (`domain/orders.match_line`): for each item, billed (this bill and earlier bills
  on the order) must not exceed goods received, nor ordered, by more than the quantity tolerance,
  and the bill rate per base unit must not exceed the order rate by more than the rate tolerance;
  an item not on the order, or a bill before anything is received, is an exception. Billing less,
  or a lower rate, is fine. A zero tolerance means exactly. Out of tolerance: 409
  `MATCH_EXCEPTION` for a counter user (owner approval `po_mismatch`, one use, 10 minutes, the
  message carries no rupee value); the owner may save it, and it shows in the report as "entered
  by the owner". Supplier and shop must match the order.
- Match report (`GET /reports/match-exceptions`, owner): computed when read against the goods
  received so far, so a late receipt clears an exception. PPV = (bill rate - order rate) x
  quantity billed per line, totalled over every line checked (KPI `ppv`, owner only).
- Cement lots (`services/lots.py`, `domain/orders.fifo_pick`) - the smallest version, built without
  the owner's answer on whether the week is printed on the bag (FINANCE_REVIEW section 7, question
  6): the week and year on a purchase line are optional and for cement only (409 `LOT_ONLY_CEMENT`,
  `BAD_LOT` for a week that does not exist or is after the bill date). A cement sale takes the
  oldest lot first and records the lots on the sale line (`sales_line_lot`). A delivery without a
  week is ordered by its bill date (the fallback). Stock the lots do not account for (opening
  stock, customer returns, transfers in) is treated as older and is sold first; if less is on hand
  than the lots hold, the missing quantity comes off the oldest lots. Costing is unchanged (one
  weighted-average cost); the bill PDF is unchanged; the lots show on the invoice screen.
  Transfers carry no lot, and a lot is kept per shop of the purchase.
- Lost-sales log (`services/lost_sales.py`), also the smallest version, built without the owner's
  answer on whether counter staff will log (question 7): item, quantity (any unit of the item),
  optional note, shop and user; counter staff log for their own shop, dated today; the owner may
  back-date. The market rate on the day is stored with the entry so the owner sees its value
  (counter staff and the accountant never do; the accountant has no access). Fill rate per item
  = quantity supplied (all bill lines in the month) ÷ (supplied + logged), and a line count
  (bill lines ÷ bill lines + entries) that works across units. KPI `fill_rate` (owner and counter).
- Screens: Purchases, Purchase orders; "Against order" and week-made boxes on a purchase; Reports,
  Order matches; Stock, Lost sales (and a link on the bill screen).
- Not built: order cancellation or change (an order is permanent; place another), a GRN that moves
  stock before the bill, matching a bill to several orders, lot-level stock report, TMT heat
  numbers and test certificates, and PPV against the last purchase rate (the dropped FM9).

**To build** (milestone in brackets):

| Group | Table | Key columns |
| --- | --- | --- |
| Items [2] | `item` | name, category, brand (G8), hsn (8 digits), gst_rate, base_unit, size, grade, weight_per_piece_kg (G7), min_margin, is_active |
| Items [2] | `item_unit` | item_id, unit, factor_to_base, whole_only |
| Prices [5] | `market_rate` | item_id, rate, effective_date, entered_by |
| Prices [5] | `customer_rate` | party_id, item_id, rate, valid_from, valid_to |
| Prices [5] | `item_margin` | item_id, margin_per_base_unit (owner only) |
| Parties [2] | `party` | name, type (customer/supplier/both), segment (retail/contractor/bulk), gstin, state_code, address, phone, credit_allowed, credit_limit, credit_days |
| Parties [2] | `site` | party_id, name, address, state_code, gstin or "URP" (G13, G22) |
| Parties [3] | `opening_balance` | party_id, site_id, amount, as_of |
| Purchase [4] | `purchase`, `purchase_line` | supplier_id, location_id, bill_no, bill_date, mode (stock/direct), status; line: item_id, qty, unit, rate, gst_rate, weight_billed, weight_received, unit_cost |
| Purchase [4] | `cost_component`, `purchase_cost` | name, basis (per_ton/per_base_unit/per_trip/flat), default_amount; line_id, component_id, amount |
| Stock [4] | `stock_ledger` | item_id, location_id, qty_in, qty_out, unit_cost, ref_type, ref_id, entry_date — **append-only** |
| Stock [4] | `stock_transfer`, `stock_count`, `stock_count_line` | from/to location, item, qty; count sessions and variances |
| Sales [6] | `sales_invoice`, `sales_line` | number, financial_year, location_id, party_id, site_id, bill_to, ship_to, place_of_supply, supply_kind, supply_type (B2B/B2C), invoice_date, due_date, totals, round_off, pending_balance_at_billing, idempotency_key (G19); line: item, qty, unit, rate, rate_source, discount, taxable, cgst/sgst/igst, fulfilment_source |
| Money [7] | `payment`, `payment_allocation` | party, site, location, amount, mode, reference, date, idempotency_key; allocation to invoice or purchase |
| Money [7] | `approval` | action, document, reason, requested_by, approved_by (G18) |

Derived views: `v_stock` (qty per item per location, company-wide average cost),
`v_party_ledger` (receivable/payable per party and site, aging 0–30/31–60/60+),
`v_scheme_progress`.

## 5. Core logic

All maths lives in `backend/app/domain/` as pure functions with unit tests
(`tests/unit/test_domain.py`). Worked examples there are the acceptance numbers.

1. **Landed cost** (B1, B2, G1). 10,000 kg TMT at ₹55/kg, unloading ₹250/ton, weighbridge ₹150,
   transport ₹4,000 → goods ₹5,50,000, charges ₹6,650, cost ₹55.6650/kg. A 1% weighbridge
   shortage raises the unit cost; it does not hide inside stock value.
2. **Weighted-average stock** (G6). On stock-in: `new_avg = (q·avg + q_in·c_in) / (q + q_in)`.
   Stock-out uses the current average. One average per item for the whole business; quantity
   per location. Returns restock at the original sale cost.
3. **Price resolution** (B3). Customer rate active on the bill date → else latest market rate on
   or before it → else blocked. Staff see only the result.
4. **GST** (G3, G5). Place of supply = ship-to site state, or the shop's state for counter pickup.
   Same state as the shop → CGST + SGST (half each, so they are always equal); else IGST.
   Tax is rounded per line to paise, half-up. The invoice total is rounded to the rupee with a
   visible round-off line. Rates are stored excluding GST unless `rates_include_gst` (G2).
5. **Credit check** (B8). Runs only on the unpaid part of a bill. Violations:
   `CREDIT_NOT_ALLOWED`, `CREDIT_LIMIT_EXCEEDED`, `OVERDUE_INVOICES`. The API answers 409 with
   `requires_owner_approval: true`; the owner approves with their PIN (G18).
6. **Payment allocation.** Oldest unpaid invoice first unless the user picks invoices. The
   remainder stays as an advance on the account (G21). Supplier advances work the same way.
7. **Drop-ship** (B10). A direct line links to a purchase line in mode `direct`; no stock rows.
   The invoice ship-to is the customer site; the e-way bill carries the site GSTIN or "URP" (G13).
8. **Returns** (B11). Within the window: credit note, GST reversed, stock-in at original cost,
   customer balance reduced. Outside: owner approval.
9. **Weight check** (B14). `variance% = |actual − expected| / expected × 100`; above the setting
   it flags, shows the shortage in kg and rupees, and needs a note.
10. **Numbering** (B16, G4). One counter per location × document type × financial year,
    incremented by an atomic upsert in the same transaction that saves the document. Format
    `<location code><series>/<FY>/<5 digits>`, e.g. `S1/26-27/00042` (invoice), `S1C/26-27/00003`
    (credit note). Location codes are 1–2 characters so every number fits in 16.
11. **Cash and e-way checks** (G13, G14). Cash from one party in one day reaching the limit
    (₹2,00,000) is blocked; ask for UPI or bank. An e-way bill is needed when the consignment
    value exceeds the inter-state (₹50,000) or state intra-state threshold (setting).

## 6. GST and compliance requirements

Confirm each with the shop's accountant before go-live; rules change.

- **Invoice content:** supplier name, address, GSTIN; number and date; buyer name and GSTIN
  (B2B); place of supply and state code; per line HSN, description, qty, unit, rate, taxable
  value, tax rate and amounts; totals with tax split, amount in words, round-off, bank details,
  vehicle number and e-way bill number where applicable; "Original for recipient" copy marks.
- **B2C** (no buyer GSTIN) is a normal tax invoice with the GSTIN left blank.
- **E-way bill:** through a GSP API from the saved invoice (Part A from the invoice, Part B
  vehicle), update vehicle, cancel within the allowed window, store the raw response; manual
  entry of a portal-generated number as fallback. Provider behind an interface.
- **E-invoicing (G12):** required for B2B invoices once aggregate turnover crosses ₹5 crore in
  any year; the same GSP should support IRN and QR. Keep `einvoice_enabled` off until the
  accountant says so.
- **GSTR-1** export (B2B, B2C, credit/debit notes, HSN summary, document series summary),
  **GSTR-3B** summary, **GSTR-2B** matching by supplier GSTIN and bill number.
- **Retention (G15):** keep accounts and records at least 72 months; no hard deletes.

## 7. API conventions

See [API.md](API.md). REST + JSON under `/api/v1`; errors `{code, message, field, request_id}`;
business blocks are 409 with a code; list endpoints take `limit`/`offset`; money is sent as a
decimal string; dates are ISO; times are stored in UTC and shown in Asia/Kolkata.

## 8. Reports (Milestone 12)

- Today (home): items and stock per item, customers owe, we owe suppliers, sales today,
  profit today (owner only).
- Daily closing PDF per shop, saved date-wise to cloud storage.
- Stock with value, dues list (weekly), aging, profit by item/customer/site.
- Sales by customer segment (retail / contractor / bulk) as a monthly bar chart, empty until
  data arrives (owner interview Q2).
