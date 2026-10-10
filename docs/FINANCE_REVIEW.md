# Finance and inventory review (Phase 1 audit)

**Date:** 2026-10-10 · **Scope:** `main` at `92c6464` (Milestones 0–14 and the UI redesign) ·
**Reviewers:** CFO of a building-materials distributor (finance, working capital, controls) and
the engineer who owns the code. Read-only audit: no code was changed.

Related: [SPEC](SPEC.md) · [GAP_ANALYSIS](GAP_ANALYSIS.md) · [GLOSSARY](GLOSSARY.md) ·
[ROADMAP](ROADMAP.md) · [ADR 0003](adr/0003-append-only-ledgers.md) ·
[ADR 0006](adr/0006-ledger-tables-and-opening-balances.md)

## 1. Verdict

The system is a strong **billing, stock and GST engine**. Landed cost, company-wide weighted
average cost, append-only ledgers, gapless numbering, credit control with owner PINs, day locks
and the integrity check are better than most shops of this size ever get. As a **finance system**
it stops at gross profit. Shop expenses, bank deposits and cash expenses have nowhere to go, so:
- the owner cannot see net profit;
- the daily drawer cannot balance without a "difference" note, and that hides leakage;
- stock losses can only enter through a stock count, with no reason, no threshold and no GST
  reversal.

Every working-capital question ("how much cash is tied up, who pays late, what is ageing, what
should I reorder") can be answered from data the system **already captures**. Those answers are
reports, not new forms. The four gaps that need new capture before go-live:
- an expense and cash book;
- reasoned stock adjustments with approval;
- labelled rate overrides;
- an export the accountant can load into Tally.

## 2. Planning model behind the ₹ estimates

There is no real trading history yet. The estimates below use this model. **Replace it with the
owner's real figures** (questions in section 6), and every estimate scales with it.

| Assumption | Value | Basis |
| --- | --- | --- |
| Net sales (excl. GST) | ₹2 crore a month, ₹24 crore a year | ~50 e-way bills a day (SPEC §1); e-invoicing at ₹5 crore expected to be crossed (G12) |
| Mix | Steel (TMT, angles, channels, pipes) 70%, cement 25%, wire and others 5% | Product list in SPEC §1 |
| Gross margin | about 3.5% (₹1,000–1,500 a ton on ~₹56,000 a ton steel; ₹10–20 a bag on ₹380 cement) | Margin figures in B3 |
| Inventory at cost | ~₹1.2 crore (about 18 days of COGS) | Two shops and a godown |
| Credit sales | ~30% of sales | B8: credit for a few approved customers |
| Supplier advances | ~₹40 lakh on average | B6: suppliers are mostly paid in advance |
| Cost of money | 12% a year (cash-credit limit) | Typical MSME CC rate |
| One day of sales | ₹24 crore ÷ 365 = **₹6.6 lakh** | Each day cut from the cash cycle frees this much |

## 3. Audit by check

"Captured?" says whether the data needed already exists (a report-only fix) or needs new capture.

### A. Inventory and stock movement

| Check | What exists today | What is missing | Captured? |
| --- | --- | --- | --- |
| A1 Movement types | `stock_ledger` (append-only, trigger-enforced) with `ref_type` in `models/enums.py:StockRef`: opening, purchase (GRN = the purchase entry), purchase_return (debit note), sale, sale_return (credit note), transfer, adjustment. Unit cost and `created_by` on every row. Drop-ship moves no stock (B10). | No **reason code** column (free-text `narration` only). Adjustments only come from posting a stock count (`services/stock_ops.py:310`); you cannot record breakage, rust, theft, weighbridge loss or a free sample on its own. No **write-down to NRV** row type. No value threshold or approval for adjustments (only "owner posts the count"). Transfers are an instant out and in on the same date: no **in-transit**. | Partly. Reason codes, thresholds and write-downs need new capture. |
| A2 Stock status | On hand per item per location (`services/ledgers.py:stock_summary`, `/stock`). | Reserved, in transit and available. There are no sales orders, and transfers are instant. | No; low payoff today (see F20). |
| A3 Replenishment | Nothing. The Today screen counts zero-stock items. | Lead time (needs a PO date), safety stock, reorder point, stock-cover days, a weekly reorder list, low-stock alerts. | Sales velocity: yes. Lead time: no. |
| A4 Classification | Nothing. | ABC, FSN and dead-stock aging can all be built from `stock_ledger` and `sales_line`. XYZ is skipped (F22). | Yes. |
| A5 Accuracy | `stock_count` and `stock_count_line` store system qty, counted qty and variance; the variance is posted at average cost; the owner sees ₹ variance. `purchase_line` stores `weight_variance_pct`, `weight_flagged` and `weight_note`. | Shrinkage % by item, location, supplier and vehicle; a book-vs-physical ₹ report across counts; an ABC cycle-count schedule. Vehicle is linked only through an optional `trip.purchase_id`. | Yes (vehicle partly). |
| A6 Product-specific | Attachments on purchases can hold a mill test certificate (MTC) as a file. | Cement manufacturing week and lots, FIFO issue, TMT heat number per lot. Stock is one weighted-average pool with no lots. | No. |
| A7 Demand capture | Nothing. | An enquiry and lost-sales log, which gives fill rate and stock-out rate. | No. |
| A8 Purchase cycle | Purchase entry = supplier bill + GRN in one document: `received_qty` (weighbridge) vs `billed_qty`. Supplier advances sit on the payable ledger (B6). | No purchase order; so no three-way match and no PPV against a PO. PPV against the **last purchase** can be computed now. | Last-purchase PPV: yes. PO: no. |
| A9 Price risk | `market_rate` history per item per day. WAC is rebuilt by replay. Each bill warns when it is below cost (B5). | Holding gain or loss (replacement cost vs WAC) and an NRV check across stock (today's selling rate vs WAC). | Yes. Replacement cost can use the last purchase cost as a proxy. |
| A10 Truck economics | `trip`: vehicle, from, to, freight, and an optional invoice or purchase. Purchase charges per trip or per ton. | Freight per ton per route, full vs part load, supplier MOQ. | Partly (tonnage comes through the linked document). |

### B. Costing and profitability

| Check | What exists today | What is missing | Captured? |
| --- | --- | --- | --- |
| B1 COGS | Each `sales_line` stores `cost_per_unit` (WAC at issue); a direct line uses the linked purchase cost (`services/reports.py:_lines`). | A cross-check: opening + purchases − closing at WAC = COGS + adjustments, per month. | Yes. |
| B2 Margins | `/reports/profit`: taxable − cost − freight, with margin %, by item, customer or site. | Gross margin per ton and per bag, and contribution after loading labour (loading is not captured: F1). | Yes, except loading. |
| B3 Profitability cuts | Item, customer, site; segment for sales only. | Brand, segment profit, shop and counter user. All the keys exist on the bill or item. | Yes. |
| B4 Price realisation | Bills keep `rate`, `discount`, `discount_reason` and `rate_source` (customer or market). | An **owner rate override is saved as `rate_source = market` with no reason** (`services/sales.py:251-257`), so a manual price cut cannot be told apart from a market sale. No realisation or discount-leakage report. | Partly. The billed rate can be compared with the market rate on that date, but overrides are unlabelled. |
| B5 Scheme rebates | `supplier_scheme` progress is computed; the rebate is booked once when earned (G29). | Accrual of the expected rebate as volume builds. | Yes (report). |
| B6 Landed-cost variance | Charges are fixed at purchase entry; a later trip on that purchase records the freight payable. | Estimated charge vs actual freight bill. | Partly (trip freight vs the purchase's transport charge). |

### C. Working capital and cash

| Check | What exists today | What is missing | Captured? |
| --- | --- | --- | --- |
| C1 Receivables | `/reports/dues?account=receivable`: balance, advance and aging 0–30, 31–60 and over 60 **days since the bill date**. Credit limit and days are on the party. `due_date` is on the bill. | Aging by **days overdue** (since the due date); DSO; collection efficiency; credit utilisation; doubtful-debt provision. There is **no write-off**: the only way to clear a bad debt today is a credit note, which is a GST document and the wrong tool. | Yes for the reports. Write-off needs a new entry type. |
| C2 Payables | `/reports/dues?account=payable`: balance, **advance** and aging; `purchase.due_date`. | DPO, advance days, and the cash tied up in advances shown as a figure. | Yes. |
| C3 Overall | Nothing. | DIO, cash conversion cycle, working capital, and inventory as % of it. | Yes, except cash and bank (C4). |
| C4 Cash and bank | Payments carry a mode (cash, UPI, bank) and a reference. The daily closing drawer = opening + cash received − cash paid to parties. | No cash book or bank book; no bank account entity; no UPI or bank **statement reconciliation**; **no way to record a shop expense, a deposit of cash into the bank, or a withdrawal**; no cash-flow forecast. | No. |

### D. Accounting completeness

| Check | What exists today | What is missing | Captured? |
| --- | --- | --- | --- |
| D1 OPEX | **Confirmed absent.** "Profit" everywhere is gross profit after freight. | Rent, salaries, power, loading labour, vehicle, interest, and with them net profit and break-even. | No. |
| D2 General ledger | **No GL**: no chart of accounts, no journals, no trial balance; no Tally export. The party and stock ledgers are sub-ledgers. | See the options below. | Partly (documents exist). |
| D3 Month-end close | A shop-day lock (G17) with an audited owner reopen; the integrity check (ADR 0010). | A month or period lock after GST filing; a close checklist (count, NRV, provision, accrual, GST and bank reconciliation); frozen month-end snapshots. | Partly. |
| D4 Lower of cost and NRV | Nothing. | A month-end NRV report and a write-down entry. Accountant to confirm (AS 2 for a non-Ind-AS MSME). | Yes for the report; the write-down needs a new row type. |
| D5 GST | GSTR-1, 3B and 2B matching (Milestone 13); ITC on debit notes taken back. | **ITC reversal** when stock is lost, stolen, destroyed or written off (CGST Act s.17(5)(h)); a GST payable forecast; the ₹ value at risk from 2B mismatches. | Mostly yes; reversal needs the adjustment reason (F3). |

**General ledger options (D2)**

| Option | What it is | For | Against |
| --- | --- | --- | --- |
| (a) Expense book + monthly P&L | Expense vouchers with categories; P&L = gross profit − expenses | Small (M); the owner gets net profit in weeks | Not books of account; the accountant still keeps Tally |
| (b) Auto-posted double-entry GL | Chart of accounts; every document posts journals; trial balance, P&L, balance sheet | Single source of truth, audit-ready | Large (L+); duplicates Tally, which the accountant already uses; high risk before go-live |
| (c) No GL, clean Tally export | Day-book export (sales, purchases, notes, receipts, payments, expenses) as Tally XML vouchers | Uses the accountant's existing tool; no re-keying; small (M) | Two systems; mapping to ledger names must be agreed |

**Recommendation: (a) + (c).** The expense book gives the owner net profit and a balanced drawer;
the Tally export gives the accountant books without re-keying. Revisit (b) only for the SaaS
version, where customers will not all have an accountant on Tally.

### E. Controls and risk

| Check | What exists today | What is missing | Captured? |
| --- | --- | --- | --- |
| E1 Maker-checker | Owner PIN approvals (`approval`): credit override, below cost, discount, backdate, late return. Count posting is owner only. | Thresholds in settings for stock adjustments and write-offs (none exist). Discounts and rate changes are already owner-only (zero threshold). | Partly. |
| E2 Exception reports | Approvals, `audit_log` (override events) and weight flags are all stored. `GET /audit` exists. | **No exception report and no audit-log screen.** Rate overrides are invisible (B4). | Yes, except rate overrides. |
| E3 Fraud red flags | Raw data is in the ledgers and audit log. | Adjustments just before a count; frequent returns by one customer; repeated weight shortages from one supplier or vehicle; round-number adjustments; cash near the limit. | Mostly yes. |

### F. Owner decision support

| Question | Answerable in under a minute today? |
| --- | --- |
| Cash tied up in stock, credit and supplier advances | **No.** Stock value is on `/stock` (owner), dues on two reports, and no total |
| Which items and customers make money per ton | **Partly.** Profit by item or customer in ₹ and %, not per ton or bag |
| Who pays late | **Partly.** Aging is from the bill date, not the due date; no DSO per customer |
| What to reorder this week | **No** |
| Which stock is ageing | **No** |
| Net profit this month; break-even sales | **No** (no expenses) |

Also: the Today screen shows **Sales today GST-inclusive and before returns** (₹14,632 in the dev
data) next to **Profit today**, which is net of returns and excludes GST (₹900). The two figures
are on different bases (`services/reports.py:today`).

## 4. Gap table

Priority: **P0** before go-live, **P1** within a month of go-live, **P2** later. Effort: S ≤ 2
days, M ≤ 1 week, L > 1 week. ₹ figures are per year on the planning model unless stated.

| ID | Area | Gap | Business impact | Data captured? | Fix | Effort | Priority | Confirm? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F1 | D1 | No operating expenses, so "profit" is gross profit | Profit overstated by the whole opex (est. **₹40–60 lakh a year**: rent, 6–10 salaries, power, loading labour, vehicle, interest). Pricing at ₹1,000/ton cannot be checked against break-even | No | Expense book: categories, vouchers (cash, UPI or bank, shop), monthly P&L = gross profit − opex; break-even | M | P0 | Owner (categories) |
| F2 | C4 | Cash expenses, bank deposits and withdrawals cannot be recorded; the drawer only nets cash from and to parties | Every day ends with a "difference" note; est. **₹7–20 lakh a year** of cash movement unexplained (₹1,000–3,000 a shop a day in petty cash, plus deposits); real shortages hide among normal ones | No | Cash-book entries: shop expense, deposit to bank, withdrawal from bank, owner drawing; included in the closing drawer | M | P0 | No |
| F3 | A1, E1 | Stock adjustments have no reason code and no ₹ threshold, and come only from counts | Shrinkage and loss invisible: **₹6–12 lakh a year** at 0.25–0.5% of throughput; theft can be posted as a "count correction" | No | Adjustment document with reason codes (weighbridge gain/loss, breakage, rust/damage, theft, count correction, free sample, write-down); owner approval above `adjustment_approval_limit`; reason column on `stock_ledger` | M | P0 | No |
| F4 | B4, E2 | Owner rate override saved as "market" with no reason | Manual price cuts are untraceable; discount leakage est. **₹2.4–7.2 lakh a year** (0.1–0.3% of sales) | Partly | New `rate_source = override` and a required reason (forward only: past rows are not edited); then the realisation and leakage report (F24) | S | P0 | No |
| F5 | D2 | No books of account: no Tally export | Accountant re-keys ~1,500 documents a month: **₹2–4 lakh a year** in fees, plus keying errors in filed returns | Yes | Tally XML day-book export (sales, purchases, notes, receipts, payments, expenses) with a ledger-name mapping in settings | M | P0 | Accountant (Tally version, ledger names) |
| F6 | Today | "Sales today" includes GST and is before returns, beside a net profit | Misread margin (₹14,632 vs ₹900 looks like 6%; the true margin on net taxable value is 9.7%) | Yes | Show net sales excl. GST, returns shown separately; "what this means" line | S | P0 | No |
| F7 | C1–C3 | No working-capital KPIs: DSO, DPO, DIO, advance days, CCC, cash tied up | Each day cut from the cash cycle frees **₹6.6 lakh**; 5 days = ₹33 lakh freed, **~₹4 lakh a year** interest | Yes | Working-capital report and a Today card (owner): stock + receivables + advances − payables; trend by month | M | P1 | No |
| F8 | C1 | Receivable aging from bill date, not due date; no DSO, credit utilisation or collection efficiency per customer | Late payers are not visible early; est. bad debts **₹3–6 lakh a year** (0.5–1% of ₹7 crore credit sales) plus interest on overdue money | Yes | Overdue-days aging (current, 1–15, 16–30, 31–60, 60+), DSO and utilisation per customer, top late payers | S | P1 | No |
| F9 | C1, D3 | No bad-debt write-off or provision; the only tool is a credit note (a GST document) | Write-offs through credit notes misstate GST outward supply: tax risk + **18% interest** on reversed tax | No | Write-off entry (owner PIN, reason) on the party ledger with no GST effect; provision % by overdue bucket as a report (setting, conservative default) | M | P1 | Accountant |
| F10 | A4 | No dead-stock aging, ABC or FSN | Slow stock ties up money: est. **₹6–12 lakh** (5–10% of inventory) carrying ~₹1 lakh a year interest, plus markdown and rust | Yes | Inventory analytics: aging buckets 0–30, 31–90, 91–180, 180+ by last movement; ABC by consumption value; FSN by issue frequency | M | P1 | No |
| F11 | A6 | Cement age and FIFO not tracked (one average pool) | Cement older than ~90 days loses strength: claims, returns, forced discounts. Est. **₹1–3 lakh a year** at 0.5–1% of cement sales | No (full); Yes (proxy) | First a **FIFO age estimate** from receipts vs issues (report only); later lots with manufacturing week (F25) | S (proxy) | P1 | Owner |
| F12 | A9, D4 | No NRV check or holding gain/loss on stock | When steel falls ₹2,500/ton, ~130 t on hand loses **~₹3.2 lakh** in value; the owner should see it and sell down or stop buying | Yes | Report: WAC vs today's market rate (NRV) and vs last purchase cost (replacement); month-end lower-of-cost-and-NRV value | S | P1 | Accountant (AS 2) |
| F13 | A5 | No shrinkage or weight-loss report by supplier, vehicle, item or location | Repeated weighbridge shortages from one supplier: est. **₹3–7.5 lakh a year** recoverable (0.2–0.5% of ~₹15 crore steel purchases) | Yes (vehicle partly) | Shrinkage % and ₹ by supplier, item, location; weight-shortage claims list per supplier | S | P1 | No |
| F14 | A3 | No reorder list or low-stock alerts | Stock-outs lose sales at ₹1,000–1,500/ton margin and customers; over-buying ties up cash | Velocity: yes. Lead time: no | Average daily sales, stock-cover days, reorder point = sales × lead time + safety stock; lead time per supplier as a setting until POs exist; weekly list | M | P1 | Owner (lead times) |
| F15 | D5 | No ITC reversal when stock is lost, stolen, destroyed or written off | GST demand on the reversed ITC (~18% of the loss value: **~₹1–2 lakh a year** at F3's losses) + interest + penalty | No (needs F3 reasons) | Adjustment reasons map to "ITC to reverse"; monthly reversal report for 3B 4(B); setting, default reverse | S | P1 | Accountant |
| F16 | C4 | No bank or UPI reconciliation | Fake or failed UPI payments recorded as received: a single incident costs **₹50,000–2 lakh**; receipts never reconciled | No | Bank accounts; statement upload (CSV); match by amount, date and reference; unmatched lists | M | P1 | No |
| F17 | E2, E3 | No exception report or audit-log screen | Fraud red flags (adjustments before counts, returns by one customer, round-number entries, back-dating, cash near the limit) go unseen | Yes | Owner exception report, weekly, with drill-down; audit-log screen | M | P1 | No |
| F18 | D3 | No month or GST-period lock | A credit note dated into a filed GSTR-1 month puts the books out of step with the return | Yes | Period lock after filing (owner reopen with reason, audited); month-end checklist | S | P1 | Accountant |
| F19 | B2, B3 | Profit not per ton or bag, nor by brand, shop, segment or counter user | Cannot see which brand or customer earns per ton; e.g. a ₹900 margin on 150 kg is ₹6,000 a ton | Yes | Extend the profit report: per-unit margin, and brand, segment, shop and user cuts | S | P1 | No |
| F20 | A2, A1 | No reserved or in-transit stock | Low for now: no sales orders, and shop–godown moves finish the same day | No | **Skipped** until sales orders exist | — | P2 | No |
| F21 | B5, B6 | No rebate accrual; no landed-cost variance | Monthly profit understated until a rebate is booked; freight overruns unseen. Est. ₹0.5–2 lakh a year timing and visibility | Yes | Accrual report (expected rebate on progress); estimated vs actual freight per purchase | S | P2 | Accountant (rebate treatment) |
| F22 | A4, A3 | XYZ classes and EOQ | Little value at this size: truckloads and price moves decide order size | — | **Skipped**; EOQ shown as guidance only if asked | — | P2 | No |
| F23 | C4 | No 13-week cash-flow forecast | Supplier advances and GST due dates squeeze cash; the CC limit is overdrawn by surprise | Mostly (due dates, 3B; opex after F1) | Forecast: collections by due date, supplier payments, GST on the 20th, opex run-rate | M | P2 | No |
| F24 | B4 | No price-realisation or discount-leakage report | See F4 | Yes (after F4) | Billed rate vs market rate on the bill date, per item, customer and user | S | P1 | No |
| F25 | A6, A8 | No lots (cement week, TMT heat number, MTC), no purchase orders, no three-way match | Quality claims and supplier rate disputes; PO-based PPV | No | Purchase orders → GRN → bill match; lots on purchase lines and FIFO pick. Large change to stock costing | L | P2 | Owner |
| F26 | A7 | No lost-sales or enquiry log | Unknown unmet demand; fill rate unknown | No | One-tap "asked for, not in stock" at the counter | S | P2 | Owner (will staff use it?) |
| F27 | A10 | No truck economics | Freight per ton per route and part loads unseen | Partly | Freight per ton by route from trips and the linked documents | S | P2 | No |
| F28 | B1 | No COGS cross-check | A costing bug would go unnoticed | Yes | Monthly check opening + purchases − closing = COGS + adjustments, in the integrity check | S | P1 | No |
| F29 | D5 | No GST payable forecast or 2B value at risk | ITC not in 2B is unclaimable: value at risk unknown | Yes | ₹ of "in books, not in 2B" ITC; GST payable estimate from 3B to date | S | P1 | No |

## 5. KPI catalogue

One catalogue, to live in `backend/app/domain/kpi_catalogue.py` and be served at
`GET /api/v1/kpis/definitions`. Periods are calendar months in an April–March financial year,
IST. "Owner only" metrics never reach the counter role (tested per endpoint). With too little
history the screen says "Not enough data yet (needs N days)".

| Code name | Metric | Formula | Source (tables.columns) | Owner only | Refresh | Good is |
| --- | --- | --- | --- | --- | --- | --- |
| `net_sales` | Net sales | Σ sales_line.taxable − Σ credit_note_line.taxable | sales_line, credit_note_line | No | Live | Up |
| `cogs` | COGS | Σ (qty issued × WAC at issue), net of returns at their cost | sales_line.base_qty, cost_per_unit; drop_ship_link.unit_cost; credit_note_line | Yes | Live | — |
| `gross_profit` | Gross profit | net_sales − cogs − freight on sales | above + trip.freight_amount | Yes | Live | Up |
| `gross_margin_pct` | Gross margin % | gross_profit ÷ net_sales × 100 | above | Yes | Live | Up |
| `contribution_per_ton` | Contribution per ton (or per bag) | (net_sales − cogs − freight − loading) ÷ tons sold | above + item units; loading from F1 | Yes | Daily | Up |
| `opex` | Operating expenses | Σ expense vouchers by category | expense (F1) | Yes | Live | Down |
| `ebitda` | EBITDA | gross_profit − opex excluding interest | above | Yes | Monthly | Up |
| `net_profit` | Net profit | gross_profit − opex (incl. interest) ± write-downs and write-offs | above | Yes | Monthly | Up |
| `break_even_sales` | Break-even sales | fixed opex ÷ (contribution ÷ net_sales) | above | Yes | Monthly | Down |
| `inventory_value` | Inventory at cost | Σ on hand × WAC | stock_ledger replay | Yes | Live | — |
| `inventory_turnover` | Inventory turnover | cogs ÷ average inventory at cost | above | Yes | Monthly | Up |
| `dio_days` | Days inventory outstanding | average inventory ÷ cogs × days | above | Yes | Monthly | Down |
| `stock_cover_days` | Stock cover | on hand ÷ average daily sales qty (last 30 days) | stock_ledger, sales_line | No (qty only) | Daily | Neither too low nor too high |
| `reorder_point` | Reorder point | average daily sales × lead time + safety_stock | sales_line; supplier lead time (F14) | No | Weekly | — |
| `safety_stock` | Safety stock | average daily sales × safety days; after 90 days z × σ(daily demand) × √lead time | sales_line | No | Weekly | — |
| `gmroi` | GMROI | gross_profit ÷ average inventory at cost | above | Yes | Monthly | Up |
| `shrinkage_pct` | Shrinkage % | (book qty − physical qty) ÷ book qty | stock_count_line; adjustments (F3) | ₹ owner only | Per count | Down |
| `weight_loss_pct` | Weight loss % | (billed − received) ÷ billed | purchase_line.billed_qty, received_qty | No | Live | Down |
| `nrv` | Net realisable value | expected selling rate − costs to sell, per unit | market_rate; settings for costs to sell | Yes | Daily | — |
| `holding_gain_loss` | Holding gain or loss | (replacement cost − WAC) × qty on hand | last purchase_line.unit_cost; replay | Yes | Daily | Up |
| `ppv` | Purchase price variance | (actual rate − reference rate) × qty; reference = PO rate (F25) or last purchase | purchase_line | Yes | Live | Down |
| `fill_rate` | Fill rate | qty supplied ÷ qty requested | sales_line + lost-sales log (F26) | No | Weekly | Up |
| `price_realisation_pct` | Price realisation | billed rate ÷ market rate on the bill date × 100 | sales_line.rate; market_rate | Yes | Daily | Up (≈100) |
| `discount_leakage` | Discount leakage | Σ (market rate − billed rate) × qty, where positive, + discounts | sales_line; market_rate | Yes | Daily | Down |
| `dso_days` | Days sales outstanding | average receivables ÷ credit sales × days | party_ledger (receivable) | No | Monthly | Down |
| `collection_efficiency_pct` | Collection efficiency | collections ÷ (opening receivables + credit sales) × 100 | party_ledger; payment | No | Monthly | Up |
| `credit_utilisation_pct` | Credit utilisation | outstanding ÷ credit limit × 100 | party_ledger; party.credit_limit | No | Live | Below 80 |
| `overdue_receivables` | Overdue receivables | Σ open bills past due_date | sales_invoice.due_date; party_ledger | No | Live | Down |
| `dpo_days` | Days payables outstanding | average payables ÷ purchases × days | party_ledger (payable) | Yes | Monthly | Up (within terms) |
| `advance_days` | Supplier advance days | average supplier advances ÷ purchases × days | party_ledger (payable, debit balances) | Yes | Monthly | Down |
| `ccc_days` | Cash conversion cycle | dio_days + dso_days + advance_days − dpo_days | above | Yes | Monthly | Down |
| `working_capital` | Working capital | inventory + receivables + supplier advances + cash and bank − payables − GST payable | above; cash book (F2) | Yes | Daily | — |
| `cash_tied_up` | Cash tied up | inventory + receivables + supplier advances | above | Yes | Daily | Down |
| `provision_doubtful` | Provision for doubtful debts | Σ overdue bucket × provision % (setting) | party_ledger; settings | Yes | Monthly | — |
| `rebate_accrual` | Rebate accrual | expected rebate on scheme progress | supplier_scheme; purchase_line | Yes | Monthly | — |
| `itc_at_risk` | ITC at risk | Σ ITC on bills "in books, not in 2B" | gstr2b_import; purchase | No (accountant) | Monthly | Down |
| `roce` | ROCE | EBIT ÷ capital employed | after F1 and a capital figure from the owner | Yes | Yearly | Up |

## 6. Finance milestones (recommended order)

Each milestone gets its own branch and PR, with tests first (hand-worked numbers in comments),
migration, docs and a ROADMAP, SPEC and CHANGELOG update.

| # | Milestone | Covers | Acceptance test |
| --- | --- | --- | --- |
| FM1 | Cash book and expenses (P0) | F1, F2, F6 | A shop-day with ₹1,80,000 cash sales, ₹2,000 loading labour paid in cash, ₹1,50,000 deposited to the bank closes with **zero difference**. The October P&L shows gross profit − opex = net profit. The counter user cannot read the P&L (403). Today shows net sales excl. GST |
| FM2 | Stock adjustments with reasons and approval (P0) | F3, F15 | A breakage of 2 bags cement (₹760) posts with reason "breakage". A ₹15,000 theft adjustment above the ₹10,000 limit is refused without the owner PIN, and is listed in "ITC to reverse" (₹15,000 × 18% cement GST = ₹2,700). The ledger row carries the reason; nothing is edited |
| FM3 | Labelled rate overrides (P0) | F4 | An owner override from ₹62/kg to ₹60/kg on 1,000 kg saves `rate_source = override` with a reason, and the bill PDF is unchanged. Without a reason: 409 `OVERRIDE_REASON` |
| FM4 | Tally export (P0) | F5 | October's day book exports as Tally XML; the accountant imports it into a test company; voucher totals equal GSTR-1 and the dues reports |
| FM5 | Working capital and receivables (P1) | F7, F8, F9, F28, KPI catalogue, Metrics explained page, GLOSSARY | Hand-worked month: inventory ₹1.2 crore, COGS ₹1.93 crore, receivables ₹45 lakh on ₹60 lakh credit sales, payables ₹20 lakh, advances ₹40 lakh on ₹1.95 crore purchases (30-day month) gives DIO 18.7, DSO 22.5, DPO 3.1, advance days 6.2, CCC 44.3 days. Overdue aging uses due dates. A write-off posts with no GST effect. `GET /kpis/definitions` drives the tooltips |
| FM6 | Inventory analytics and replenishment (P1) | F10, F11 (proxy), F12, F13, F14 | Seeded movements give the hand-worked ABC split, aging buckets, cover days and reorder point: 1.2 t/day × 7 days lead + 2.4 t safety = 10.8 t. NRV loss shows when the market rate is below WAC. With under 30 days of history it shows "Not enough data yet (needs 30 days)" |
| FM7 | Controls and exceptions (P1) | F16, F17, F18, F24 | A bank CSV with 10 rows matches 8 receipts and lists 2 unmatched. The exception report shows a round-number adjustment the day before a count, and a customer with 4 returns in 30 days. Period lock: a credit note dated in a locked month is refused (409 `PERIOD_LOCKED`) |
| FM8 | Profitability cuts and GST health (P1) | F19, F29 | Profit per ton by brand, shop and user equals hand totals; ITC at risk equals the "in books, not in 2B" ITC sum |
| FM9 | Forecast and accruals (P2) | F21, F23, F27 | 13-week forecast from due dates, GST dates and opex run-rate; rebate accrual on a 60%-progress scheme equals 60% of the expected rebate (if the accountant chooses accrual) |
| FM10 | Orders, lots and demand (P2) | F25, F26 | PO → GRN → bill three-way match within tolerance; cement issued oldest week first; fill rate from the lost-sales log |

## 7. Questions

**For the owner**

1. Real numbers to replace the planning model: monthly sales, average stock value, credit
   sales share, typical supplier advance and its days.
2. Monthly expenses by head (rent, salaries, power, loading labour, vehicle, interest), and who
   pays petty cash at each shop.
3. Is cash deposited to the bank daily, and by whom? Do you draw cash from the drawer?
4. Stock adjustment limit above which you want to approve (suggested ₹10,000 a document)?
5. Lead time per main supplier (order to delivery) and how many days of safety stock you want.
6. Does your cement supplier print the manufacturing week on the bag, and do customers ask for
   TMT heat numbers or MTCs?
7. Will counter staff log "asked for but out of stock"?
8. Which bank accounts receive UPI and transfers, and can you download statements as CSV?

**For the accountant**

1. Tally version and ledger names for sales, purchases, GST heads, parties and expenses (FM4).
2. Inventory valuation: lower of cost and NRV under AS 2 at month end? Write-down method?
3. ITC reversal on loss or theft (s.17(5)(h)): reverse in the month of loss? On what value?
4. Bad debts: write-off approval, and the provision % by overdue bucket (books vs tax).
5. Supplier rebates: accrue as volume builds, or book when earned? GST on the rebate (G29)?
6. Month or period lock: lock after GSTR-1 filing, or after 3B?

## 8. Skipped, and why

- **XYZ classification, EOQ (F22):** for a 2-shop distributor, truckload sizes and daily price
  moves decide order quantity. XYZ adds little to ABC + FSN at this item count.
- **Reserved and in-transit stock (F20):** no sales orders exist and shop–godown transfers
  finish the same day; revisit with sales orders.
- **Full double-entry GL (option b):** duplicates the accountant's Tally at go-live; revisit for
  the SaaS version.
