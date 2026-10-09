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
| Parties [11] | `supplier_scheme` | party_id, item_or_category, target_qty, period_start, period_end, rebate_rule |
| Purchase [4] | `purchase`, `purchase_line` | supplier_id, location_id, bill_no, bill_date, mode (stock/direct), status; line: item_id, qty, unit, rate, gst_rate, weight_billed, weight_received, unit_cost |
| Purchase [4] | `cost_component`, `purchase_cost` | name, basis (per_ton/per_base_unit/per_trip/flat), default_amount; line_id, component_id, amount |
| Stock [4] | `stock_ledger` | item_id, location_id, qty_in, qty_out, unit_cost, ref_type, ref_id, entry_date — **append-only** |
| Stock [4] | `stock_transfer`, `stock_count`, `stock_count_line` | from/to location, item, qty; count sessions and variances |
| Sales [6] | `sales_invoice`, `sales_line` | number, financial_year, location_id, party_id, site_id, bill_to, ship_to, place_of_supply, supply_kind, supply_type (B2B/B2C), invoice_date, due_date, totals, round_off, pending_balance_at_billing, idempotency_key (G19); line: item, qty, unit, rate, rate_source, discount, taxable, cgst/sgst/igst, fulfilment_source |
| Sales [9] | `drop_ship_link` | sales_line_id, purchase_line_id, freight_amount |
| Money [7] | `payment`, `payment_allocation` | party, site, location, amount, mode, reference, date, idempotency_key; allocation to invoice or purchase |
| Money [7] | `approval` | action, document, reason, requested_by, approved_by (G18) |
| Money [12] | `daily_closing`, `cash_drawer` | location_id, date, totals by mode, pdf_path, closed_by, reopened_by (G17) |
| Transport [9] | `vehicle`, `trip` | number, owner_name, is_own; trip: vehicle, ref, freight_amount, paid_amount |
| Compliance [10] | `eway_bill`, `einvoice` | invoice_id, number / IRN, vehicle_no, valid_until, raw API response (G12) |
| Compliance [11] | `attachment` | ref_type, ref_id, file_path, kind (weighbridge/delivery/other) |

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
