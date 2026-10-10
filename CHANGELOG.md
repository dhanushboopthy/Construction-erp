# Changelog

## 1.9.0 (FM8): profitability cuts and GST health

- Reports, Profit per ton (owner): profit for a month by brand, shop, who made the bill, item or
  customer, with net sales, cost, freight, margin, share of profit, tons sold and profit per ton.
  Steel sold by weight is counted in tons; cement and other items are counted in bags or pieces
  apart, so a bag never inflates the tons. Every cut adds up to the Profit & loss gross profit
  once the stock lost is taken off. With no bills it says "Not enough data yet".
- Reports, ITC at risk (owner, accountant): input tax on supplier bills in your books that
  GSTR-2B does not show, plus bills where the supplier reported less tax than you booked, and
  the GST payable estimate for the month (the 3B figure, to date) with the 20th as the due date.
  With no GSTR-2B imported it says so instead of showing a figure.
- Fixed: Profit & loss freight counted an older bill's freight again when a credit note was
  issued for it in a later month.

## 1.8.0 (FM7): controls and exceptions

- Books lock (owner, Settings): lock the books through a date after a return is filed. A bill,
  receipt, credit or debit note, cash-book voucher, adjustment, stock count, transfer, write-off,
  rebate or supplier bill dated on or before it is refused ("PERIOD_LOCKED"). Moving the lock
  earlier, or removing it, needs a reason and is written to the audit log. A month-end checklist
  shows what needs a look first.
- Reports, Bank (owner, accountant): upload the bank's CSV (any bank, columns are found by name).
  Every line is matched to a receipt, supplier payment, deposit or withdrawal of the same amount
  and direction within a few days, a matching UPI or bank reference first. Lines with no entry,
  and entries the bank never showed (a failed or fake UPI), are listed. Matching is worked out
  when you open the page, so a late entry finds its line. Statements are permanent.
- Reports, Exceptions (owner): round-number stock adjustments, adjustments just before a stock
  count, many returns from one customer, entries dated well before they were keyed in, cash near
  the daily limit and repeated weighbridge shortages from one supplier. The limits are in
  Settings; zero switches a check off.
- Settings, Audit log (owner): who changed what and when, with filters and the before and after.
- Settings gain the bank matching days and the exception limits.

## 1.7.0 (FM6): inventory analytics and replenishment

- Stock, Analysis (owner): items to reorder now (reorder point = average daily sales x lead time
  + safety stock), days of stock, ABC class by what was sold, fast, slow or non-moving by days
  sold, and how old the stock is since its last sale or purchase. Stock not moving for over 180
  days is totalled. With under 30 days of bills it says "Not enough data yet (needs 30 days)".
- Cement by age (an estimate): oldest cement first from receipts and sales.
- Stock, Stock value (owner, accountant): stock against today's market rate; the loss when it is
  worth less than cost; gain or loss against the last purchase. The owner can write the stock
  down to market value: quantities do not change, no GST is reversed, the loss comes off the
  month's net profit.
- Stock, Weight shortages (owner, accountant): billed against the weighbridge by supplier, with
  the lines to claim.
- Lead time and safety days per item, lead time per supplier, and shop defaults in Settings.

## 1.6.0 (FM5): working capital and receivables

- Reports, Working capital (owner): days inventory outstanding, days sales outstanding, days
  payables outstanding, supplier advance days and the cash conversion cycle for any month, with
  cash tied up, working capital, inventory turnover, collection efficiency and a six-month
  trend. With too little history it says "Not enough data yet", never a made-up number. The
  Today screen shows cash tied up.
- Reports, Receivables (owner and accountant): what customers owe aged from the due date (not yet
  due, 1-15, 16-30, 31-60, over 60 days late), days late, credit used and days to pay per
  customer. The owner also sees the provision for doubtful debts.
- Bad-debt write-offs (owner only): a permanent, numbered document that clears a customer's oldest
  bills with no GST effect and comes off the month's profit. It is exported to Tally.
- Settings: the provision percentage for each overdue bucket (accountant to confirm).
- Integrity check "Cost of goods": opening stock + purchases - cost of goods sold + other moves
  must equal closing stock, for the last month and this month.
- Metrics explained (owner): every figure in the app, with its formula, meaning and an example.

## 1.5.0 (FM4): Tally export

- Reports, Tally export (owner and accountant): the day book for a date range as a Tally XML
  file. Sales, credit notes, purchases, debit notes, receipts, payments, cash-book entries
  (expenses, bank deposits and withdrawals, drawings, capital), supplier rebates and freight.
- Each file is checked against GSTR-1, GSTR-3B input tax and the dues reports before it can be
  downloaded; a file that disagrees with the books is refused.
- Ledger names for Tally (sales, purchases, each GST head, cash, bank, round off...) and the
  company name are settings the accountant confirms.
- Every export is written to the audit log.

## 1.4.0 (FM3): labelled rate overrides

- A price typed for one bill is saved as an override, not as the market rate, and needs a
  reason (Sales, New bill: "Different price" and "Reason for different price"). Without one the
  bill is refused (`OVERRIDE_REASON`). Bills are printed exactly as before.
- Every new bill line keeps the rate the system would have charged, so the rupees given away
  are exact. Bills issued before FM3 keep a blank list rate and are not changed.
- Reports, Price overrides (owner): discount leakage, price realisation, a table by person and
  every hand-priced line with its reason.

## 1.3.0 (FM2): stock adjustments and ITC to reverse

- Stock, Adjustments: breakage, rust or damage, theft, free samples, weighbridge differences
  and count corrections, each with its own permanent document and a reason on the stock
  ledger. Counter adjustments above ₹10,000 need the owner's PIN.
- The owner sees the value lost this month by reason; the P&L takes stock lost off gross
  profit.
- Reports, ITC to reverse (owner and accountant): input tax on goods lost, for GSTR-3B.
- Settings: approval limits for vouchers and adjustments, and whether unexplained shortages
  reverse ITC. Fixed: saving Settings no longer resets the cash-book approval limit.

## 1.2.0 (FM1): cash book and profit and loss

- Cash book per shop: expenses by head, cash taken to or brought from the bank, the owner's
  drawings and capital. Permanent vouchers, reversed by the owner; counter expenses above
  ₹5,000 need the owner's PIN.
- The daily closing counts every cash voucher, so a normal day closes with no difference.
- Monthly profit and loss (owner): gross profit, expenses, EBITDA, net profit, break-even sales.
- KPI catalogue (`/kpis/definitions`) with formulas and "what this means" on hover.
- Today shows net sales without GST. One shop and the godown by default; shop pickers appear
  when a second shop is added.
- Finance and inventory review (`docs/FINANCE_REVIEW.md`).

## 1.1.0: new look

- "Indigo works" design: lavender canvas, white rounded cards, indigo-to-violet gradient,
  Plus Jakarta Sans, uppercase tracked labels; light and dark mode with a toggle.
- Today is a dashboard: KPI cards that open their screens, stock levels with a reorder tip, and a
  monthly sales chart (owner and accountant).
- Search box doubles as a command palette (Ctrl+K or /); alerts bell for out-of-stock items and
  waiting e-way bills; quick actions menu; gradient user card with Sign out.

## 1.0.0 (Milestone 14): ready for go-live checks

- The database refuses to delete issued documents or change their figures (ADR 0010).
- Integrity check of the books (command line and Settings, System) and a system status page.
- Backups hold the database and the uploaded files; off-site copy script; monthly restore drill;
  restore script restores files and re-checks the books.
- Password reset from the server for a forgotten owner password.
- Every route proven to need a sign-in by a test; API answers are never cached.
- Runbook and go-live plan: training, a week of parallel running, sign-off.

## 0.14.0 (Milestone 13)

- GSTR-1 tables (B2B, B2CL, B2CS, credit notes, HSN, document series) as portal JSON and Excel.
- GSTR-3B figures with input tax from purchases and debit notes.
- GSTR-2B upload and matching against purchase bills.
- Screen: Reports, GST returns (owner and accountant).

## 0.13.0 (Milestone 12)

- Daily closing per shop: figures, cash drawer count, PDF saved date-wise to a folder or an
  S3-compatible bucket, and a lock on that shop-day until the owner reopens it.
- Today strip with real figures and stock; profit by item, customer or site (owner); dues with
  ageing; monthly sales by customer segment chart.
- Screens: Reports (Alt+8) with Daily closing, Profit, Dues, Sales by segment; Today.

## 0.12.0 (Milestone 11)

- Weight checks on purchases (billed vs received) and sales (billed vs slip): a difference above
  the setting is flagged and needs a note; shortage value shown to the owner only.
- Weighbridge slips and delivery proof kept as photos or PDFs against purchases, bills and trips.
- Supplier target schemes with progress, an 80% alert and a once-only rebate booking.
- Screens: Papers on purchase and bill views, weight note fields, Supplier schemes page.

## 0.11.0 (Milestone 10)

- E-way bills from a saved bill through a GSP (fake in development, sandbox or live by
  configuration), vehicle update, 24-hour cancel, manual-number fallback, pending list and batch.
- E-invoice (IRN and QR) for B2B bills once switched on; printed on the A4 bill.
- Screens: E-way bill and e-invoice panel on the bill view, "still without an e-way bill" notice.

## 0.10.0 (Milestone 9)

- Direct-from-supplier sales linked to their purchase line: no stock moves, profit is the sale
  less the purchase's landed cost less freight, owner-only.
- Hired vehicles and trips; freight is payable to the vehicle owner and paid through Payments.
- Warning when cash paid to one person in a day passes ₹35,000.
- Screens: Transport (Alt+T) with trips, vehicles and direct sales; supplier-purchase pick on a
  bill line; link action on the owner's bill view.

## 0.9.0 (Milestone 8)

- Credit notes for goods customers bring back: automatic inside the return window, owner PIN
  after it. GST worked out again on the returned value; stock returns at its original cost; the
  customer's balance falls against the bill.
- Debit notes for goods sent back to a supplier (owner): stock leaves at landed cost and is
  refused when already sold; what we owe the supplier falls.
- A4 PDFs for both notes; invoice lines show how much has come back.
- Screens: "Return goods" on a sales bill and "Return to supplier" on a purchase.

## 0.8.0 (Milestone 7)

- Credit control at billing: approved customers, limit, days and overdue bills; unpaid part only.
- Owner PIN approvals at the counter (credit, below-cost price, discount, back-dating): one use,
  ten minutes, full audit trail, lockout after five wrong PINs.
- Receipts from customers: oldest bill first or aimed at ticked bills; advances; cash limit;
  receipts printed on the bill when money is taken with it.
- Screens: Payments (Alt+6), "Money taken now" and the owner-approval prompt on the bill screen,
  Approval PIN setting.

## 0.7.0 (Milestone 6)

- GST sales invoices: price from rates, GST per line (CGST + SGST or IGST), round-off, B2B and B2C,
  customer site as ship-to, gapless numbers, stock and customer balance updated in one transaction.
- Pending balance and stock left printed on the bill; A4 PDF with amount in words, Original,
  Duplicate and Triplicate marks and a TEST watermark outside production.
- Safe under concurrency: item locks stop overselling; numbers stay gapless with racing bills.
- Counter staff cannot change prices or discount; cost and profit are owner-only.
- Screens: Sales bills (Alt+2): keyboard bill entry with live totals, invoice view and print.

## 0.6.0 (Milestone 5)

- Daily market rates per item with history, customer-specific rates with periods, owner-only
  margins and a suggested rate (cost + margin), warnings below cost or minimum margin.
- Price resolution: customer rate, else latest market rate on or before the date, else blocked.
- Rates quoted per ton or bag, stored per base unit without GST; GST-inclusive quoting supported.
- Screen: Daily rates (Alt+7) with a one-sheet rate entry and a Customer rates tab.

## 0.5.0 (Milestone 4)

- Purchase entry with landed cost per base unit (charges per ton, unit, trip or flat), weighbridge
  shortage raising cost, GST kept out of cost unless the shop cannot claim it.
- Supplier payable on the party ledger; supplier payments and advances with an Idempotency-Key.
- Stock transfers (Delivery challan numbers) and physical stock counts with owner posting.
- Charge types (Settings), setting for counter-staff purchase entry (G28), live landed-cost
  preview computed by the server for the owner.
- Screens: Purchases (Alt+3) with keyboard bill entry, Stock tabs: levels, transfers, counts.

## 0.4.0 (Milestone 3)

- Append-only stock ledger and party ledger (database triggers refuse UPDATE and DELETE).
- Opening balances wizard (Settings, Opening balances): stock, what customers owe, what we owe
  suppliers; drafts first, then one confirmed post.
- Stock screen (Alt+4): quantity per place from the ledger; average cost and value for the owner
  only. Statement panel on each party with aging, per site.
- `GET /reports/dues` for receivables and payables with aging.

## 0.3.0 (Milestone 2)

- Item master: category, brand, HSN, GST rate, base unit, size, grade, theoretical weight per
  piece, unit conversions (bag ↔ ton, piece ↔ kg), owner-only warning margin.
- Customers, suppliers and customer delivery sites; credit terms are owner-only.
- Excel import with a check-first step and per-row errors; downloadable template.
- Screens: Items (Alt+0) and Customers and suppliers (Alt+5), with search, unit converter and
  site management. Counter staff see items without any margin figure.

## 0.2.0 (2026-10-09)

- Milestone 0 closed: frontend installed, lint and format fixed, `package-lock.json` committed,
  CI and the frontend Docker image use `npm ci`.
- Milestone 1 screens (owner only): Settings with Shop details (each business-rule value shows
  the spec rule it controls), Users (create, edit role, name, shops and status, reset password)
  and Shops and godown (create, edit, deactivate; code fixed once created). Keyboard: Alt+N
  new, arrows move between rows, Enter opens, Esc closes.
- Frontend API types are generated from the OpenAPI spec (`src/api/schema.d.ts`).
- Role guard on every module route; navigation strip on phones; sidebar colours are tokens.
- Settings API rejects a GSTIN whose state digits differ from the shop's state code.
- Tests: role test for every API route (110 backend tests), `app/domain` at 100% coverage
  enforced in CI, screen tests with Vitest (10 frontend tests).

## 0.1.0 (2026-10-09)

- Foundation: FastAPI backend, React + TypeScript frontend, PostgreSQL, Docker Compose (dev and
  simple production with nightly backups), CI, pre-commit, Dependabot.
- Milestone 1 API: sign-in with rotating refresh sessions and lockout, roles, users, locations,
  shop settings, audit log, gapless document numbering.
- Business rules with unit tests: money, financial year, GST split and totals, units, landed
  cost, weighted-average stock, pricing, credit, weight check, compliance thresholds.
- Docs: spec v1.1 with gap fixes G1–G27, roadmap, architecture, API, design, deployment,
  glossary, ADRs 0001–0005. Claude Code `/milestone` command and two UI skills.
