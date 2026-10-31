# Construction ERP: Complete Guide

One document that explains the whole system: what each part is, who does what, how a request
travels through the server, and how to enter every kind of record, both on screen and through the
API.

For deeper detail, see [SPEC](SPEC.md) (every business rule), [API](API.md) (every endpoint),
[RUNBOOK](RUNBOOK.md) (operations), [GO_LIVE](GO_LIVE.md) (moving off paper) and
[GLOSSARY](GLOSSARY.md) (every term with a worked number).

---

## Contents

1. [What this ERP is](#1-what-this-erp-is)
2. [Who uses it: the three roles](#2-who-uses-it-the-three-roles)
3. [What is what: the building blocks](#3-what-is-what-the-building-blocks)
4. [How the system is built](#4-how-the-system-is-built)
5. [Starting the system and signing in](#5-starting-the-system-and-signing-in)
6. [One-time setup, in order (owner)](#6-one-time-setup-in-order-owner)
7. [Owner flow: day, week, month](#7-owner-flow-day-week-month)
8. [Counter flow: a working day](#8-counter-flow-a-working-day)
9. [Accountant flow](#9-accountant-flow)
10. [Execution flow inside the server](#10-execution-flow-inside-the-server)
11. [How to insert values: every document with examples](#11-how-to-insert-values-every-document-with-examples)
12. [Error codes and what to do](#12-error-codes-and-what-to-do)
13. [Database tables](#13-database-tables)
14. [Settings reference](#14-settings-reference)
15. [Common questions](#15-common-questions)

---

## 1. What this ERP is

A web application for a **construction-materials supplier** that sells TMT bars, MS square and
round pipes, cement, binding wire, angles and channels. The business has **shops** (one by default,
a second can be added) and **one godown** (warehouse).

What it does, end to end:

```text
 Supplier ──► Purchase order ──► Goods receipt ──► Supplier bill (purchase)
                                                        │ landed cost, stock IN
                                                        ▼
 Daily market rate ──► Sales bill (GST tax invoice) ◄── Stock (shop / godown / direct)
                            │ stock OUT, customer owes
                            ▼
              Payment received ──► Daily closing (cash count, day locked)
                            │
                            ▼
      Reports: Today, profit, P&L, dues, GST returns (GSTR-1, 3B, 2B), Tally export
```

Five promises the system keeps:

| Promise | What it means in practice |
| --- | --- |
| Issued documents are permanent | Bills, purchases, payments and notes cannot be edited or deleted (the database refuses). A mistake is fixed with a credit note, debit note or reversal. |
| Stock and balances are never typed in | They are worked out from append-only ledgers. You cannot "set stock to 50"; you record the document that moved it. |
| Counter staff never see cost or profit | The server removes those fields before answering, not just the screen. |
| Money is exact | All amounts are decimals (never floating point), sent as strings like `"1180.50"`. |

---

## 2. Who uses it: the three roles

| Role | Who | Main job |
| --- | --- | --- |
| **Owner** | The business owner | Sets everything up, sets daily rates, enters purchases, pays suppliers, approves exceptions with a PIN, reads profit and every report. |
| **Counter** | Staff at a shop counter, linked to **their own shop** | Makes bills, takes money, handles returns, records expenses, closes the day. |
| **Accountant** | The outside accountant | Reads books, GST returns, dues; uploads GSTR-2B and bank statements; exports to Tally. Cannot bill. |

### What each role can do

| Capability | Owner | Counter | Accountant |
| --- | --- | --- | --- |
| See selling price and stock | Yes | Yes | Yes |
| Create sales bill | Yes | Own shop | No |
| Enter purchase (supplier bill) | Yes | Own shop (if the setting allows) | No |
| See cost, margin, profit | Yes | **No** | No |
| Set daily rates, customer rates, margins | Yes | No | No |
| Discount, change price, sell below cost, give extra credit, back-date | Yes | Only with owner's PIN | No |
| Customer return after 2 days | Yes | Only with owner's PIN | No |
| Record money received | Yes | Own shop | No |
| Pay suppliers and transporters | Yes | No | No |
| Daily closing | All shops | Own shop | View |
| Supplier dues, advances, schemes | Yes | No | View |
| GST returns, Tally export, bank statements | Yes | No | Yes |
| Users, settings, audit log, period lock | Yes | No | No |

### Screens per role (left menu, Alt + key)

| Screen | Key | Owner | Counter | Accountant |
| --- | --- | --- | --- | --- |
| Today | Alt+1 | ✓ | ✓ (own shop sales) | ✓ |
| Sales bills | Alt+2 | ✓ | ✓ | ✓ (read) |
| Purchases | Alt+3 | ✓ | ✓ | ✓ (read) |
| Stock | Alt+4 | ✓ | ✓ | ✓ |
| Customers and suppliers | Alt+5 | ✓ | ✓ | ✓ |
| Payments | Alt+6 | ✓ | ✓ | ✓ |
| Daily rates | Alt+7 | ✓ | | |
| Reports | Alt+8 | ✓ | ✓ (closing) | ✓ |
| Settings | Alt+9 | ✓ | | |
| Items | Alt+0 | ✓ | ✓ (read) | ✓ (read) |
| Cash book | Alt+C | ✓ | ✓ | ✓ (read) |
| Transport | Alt+T | ✓ | | ✓ (read) |
| Metrics explained | Alt+M | ✓ | | |

---

## 3. What is what: the building blocks

### 3.1 Places, people and things (masters)

| Term | What it is | Example |
| --- | --- | --- |
| **Shop settings** | The business itself: legal name, GSTIN, state, bank details, every rule limit. One row. | "Demo Construction Materials", state 33 (Tamil Nadu) |
| **Location** | A shop or the godown. Its **code** (1–2 characters) is printed inside every document number and can never change. | `S1` Shop 1, `S2` Shop 2, `G1` Godown |
| **User** | A person who signs in, with one role. Counter users are linked to their shop(s). | `counter1` → `S1` |
| **Item** | One product: name, category, brand, HSN, GST rate, base unit, extra units. | "TMT 12mm Fe500", base unit `kg`, unit `ton` = 1000 kg |
| **Base unit** | The unit stock is counted in. Fixed once the item exists. | `kg` for steel, `bag` for cement |
| **Extra unit** | Another unit you can buy or sell in, with a factor to the base. | `ton` = 1000 kg; for cement `ton` = 20 bags |
| **Party** | A customer, a supplier, or both. Carries GSTIN, state, credit terms. | "Ravi Builders" (customer) |
| **Site** | A customer's construction site. Each bill can be for one site; statements are per site too. | "Ravi Builders – Anna Nagar site" |
| **Walk-in customer** | A party created at setup for counter sales to unknown buyers (B2C invoice). | |
| **Charge type** (cost component) | A cost added on a purchase line: unloading, loading, weighbridge, transport, commission, others. | Unloading ₹250 per ton |
| **Vehicle** | A hired (or own) truck. A hired vehicle's owner becomes a supplier account for freight. | TN09AB1234 |

### 3.2 Prices

| Term | What it is |
| --- | --- |
| **Market rate** | Today's selling rate per item, entered by the owner. The latest rate on or before the bill date applies. |
| **Customer rate** | A special rate for one customer and item, valid between two dates. Beats the market rate. |
| **Margin** | Owner-only profit target per item. The rate screen suggests *average cost + margin*. |
| **Rate resolution** | For each bill line: customer rate → else market rate → else the line is blocked ("no rate"). Counter staff never type a price. |
| **Rate override** | A price typed for one bill line (owner, or counter with PIN). Needs a reason and is reported. |

Rates are stored **per base unit, excluding GST**. The owner types them in the unit they quote
(per ton for steel, per bag for cement) and the system converts.

### 3.3 Documents (each one permanent and numbered)

Numbers look like `<location code><series>/<financial year>/<5 digits>` and are gapless per shop,
per document type, per financial year (April–March).

| Document | Series | Example number | What it does |
| --- | --- | --- | --- |
| Sales invoice | (none) | `S1/26-27/00042` | Stock out, customer owes |
| Purchase (supplier bill) | `P` | `S1P/26-27/00007` | Stock in at landed cost, we owe supplier |
| Payment / receipt | `R` | `S1R/26-27/00015` | Money in from a customer, or out to a supplier |
| Credit note (customer return) | `C` | `S1C/26-27/00003` | Stock back in, customer owes less |
| Debit note (return to supplier) | `D` | `S1D/26-27/00001` | Stock out, we owe supplier less |
| Stock transfer (delivery challan) | `DC` | `G1DC/26-27/00004` | Stock moves between places |
| Cash-book voucher | `V` | `S1V/26-27/00001` | Expense, bank deposit/withdrawal, owner drawing/capital |
| Stock adjustment | `A` | `S1A/26-27/00001` | Breakage, theft, damage, sample, weighbridge, count fix |
| Bad-debt write-off | `W` | `S1W/26-27/00001` | Give up a customer's debt |
| Stock write-down | `N` | `S1N/26-27/00001` | Lower stock value to market (no quantity moves) |
| Purchase order | `O` | `S1O/26-27/00001` | What we asked the supplier for |
| Goods receipt (GRN) | `G` | `S1G/26-27/00001` | What arrived against an order (moves no stock) |

### 3.4 Ledgers (where stock and balances come from)

| Ledger | One row per | What is derived from it |
| --- | --- | --- |
| **Stock ledger** | Every quantity moving in or out of a place | Stock per item per place, company-wide average cost, stock value |
| **Party ledger** | Every amount a customer or supplier owes or is owed | Customer dues, supplier payables, advances, statements, aging |

Both are **append-only**: rows are only ever added. A database trigger refuses edits and deletes.

### 3.5 Controls

| Term | What it is |
| --- | --- |
| **Owner PIN approval** | When the counter hits a rule only the owner may break (discount, below cost, credit, back-date, late return, large expense, large adjustment, order mismatch), the owner types their PIN on the counter's screen. The approval is good for **one document, for one customer, for 10 minutes**. |
| **Daily closing** | At day end the counter counts the drawer. The system compares it to *should be*; a difference needs a note. The day's PDF is saved, and that **shop-day is locked**. |
| **Day lock** | After closing, nothing can be dated on that shop-day until the owner reopens it (with a reason). |
| **Period lock** | After a GST return is filed, the owner locks the books through a date. Nothing can be dated on or before it. |
| **Audit log** | Every insert, update, login, approval and override is recorded with before/after values and who did it. |
| **Idempotency key** | A unique id sent with a bill or payment. If the network repeats the request, you get the first document back instead of a duplicate. |

---

## 4. How the system is built

```text
 Browser (owner / counter / accountant)
     │  HTTPS
     ▼
 nginx (web) ── serves the React app, forwards /api ──► FastAPI (backend)
                                                          │
                                                          ▼
                                    PostgreSQL ◄── nightly backup
 backend ──► GSP API (e-way bill, IRN)     backend ──► file storage (PDFs, weighbridge slips)
```

| Part | Technology | Folder |
| --- | --- | --- |
| Frontend | React 19 + TypeScript, Vite, TanStack Query | `frontend/src/` |
| API routes | FastAPI (thin: validate, check role, call service) | `backend/app/api/v1/` |
| Use cases | One function per action, one database transaction each | `backend/app/services/` |
| Business rules | Pure functions, no database: GST, landed cost, pricing, credit | `backend/app/domain/` |
| Tables | SQLAlchemy models | `backend/app/models/` |
| Request/response shapes | Pydantic schemas | `backend/app/schemas/` |
| Schema changes | Alembic migrations | `backend/alembic/versions/` |

**The rule between layers:** a layer only calls the layers below it.

```text
api/v1  ──►  services  ──►  domain  (pure maths)
                  │
                  └──►  models  ──►  PostgreSQL
```

---

## 5. Starting the system and signing in

### Development

```bash
cd construction-erp
make up      # starts db (:5432), API (:8000), web (:5173)
make seed    # creates shop settings, S1, G1, charge types, Walk-in customer, users
```

Open http://localhost:5173. The interactive API is at http://localhost:8000/api/docs.

| Username | Password (development only) | Role | Shop |
| --- | --- | --- | --- |
| `owner` | `owner-pass-123` | owner | all |
| `counter1` | `counter-pass-123` | counter | S1 |
| `accounts` | `accounts-pass-123` | accountant | all (read) |
| `counter2` | `counter-pass-123` | counter | S2 (only with `SEED_SHOPS=2`) |

In production, passwords come from `SEED_*_PASSWORD` in `.env`, or are generated and printed once.

### Calling the API directly

```bash
# 1. Sign in and keep the token (valid 30 minutes; the web app refreshes it automatically)
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"owner","password":"owner-pass-123"}' | jq -r .access_token)

# 2. Send it on every call
curl -s http://localhost:8000/api/v1/items -H "Authorization: Bearer $TOKEN"
```

Every example in section 11 assumes `-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json'`.

> **Never insert rows into the database by hand.** A bill is not one row: it is a header, lines,
> stock-ledger rows, a party-ledger row, a number from the sequence, and audit rows, all in one
> transaction. Inserting SQL directly breaks stock, balances and the integrity check. Always use
> the screens or the API.

---

## 6. One-time setup, in order (owner)

The order matters: each step needs the one before it.

```text
 ① Shop settings ─► ② Locations ─► ③ Users ─► ④ Approval PIN ─► ⑤ Charge types
        │
        ▼
 ⑥ Items ─► ⑦ Parties & sites ─► ⑧ Opening balances (post) ─► ⑨ Today's market rates ─► ready to bill
```

| Step | Screen | API | Notes |
| --- | --- | --- | --- |
| ① Shop settings | Settings → Shop | `PUT /settings` | Legal name, **GSTIN** (first 2 digits must equal state code), address, bank details, invoice terms, rule limits |
| ② Locations | Settings → Shops and godown | `POST /locations` | Code `S1`, `S2`, `G1`; cannot change later |
| ③ Users | Settings → Users | `POST /users` | One per person; link counter users to their shop |
| ④ Approval PIN | Settings → Approval PIN | `POST /auth/pin` | 4–12 digits; needs the owner's password |
| ⑤ Charge types | Settings → Charge types | `POST /cost-components` | Seeded with Unloading, Loading, Weighbridge, Transport rent, Commission, Others |
| ⑥ Items | Items (Alt+0) → New or Import | `POST /items`, `POST /items/import` | Check HSN, GST rate, units with the accountant |
| ⑦ Parties | Customers and suppliers (Alt+5) | `POST /parties` | Customers with credit terms and sites; suppliers with GSTIN |
| ⑧ Opening balances | Settings → Opening balances | `POST /opening`, then `POST /opening/post` | Stock per place at cost, customer and supplier dues. **Locked once posted.** |
| ⑨ Market rates | Daily rates (Alt+7) | `PUT /rates/market` | A bill line with no rate is blocked |

The exact JSON for each step is in [section 11](#11-how-to-insert-values-every-document-with-examples).

---

## 7. Owner flow: day, week, month

### 7.1 Owner's day

```text
 MORNING
  ├─ Settings → System ............ every row "Good"? (backup ran, yesterday's days closed)
  ├─ Today (Alt+1) ................ stock, customers owe, we owe, sales today, profit today
  └─ Daily rates (Alt+7) .......... enter today's rate per item (warns if below cost / margin)

 DURING THE DAY
  ├─ Purchases (Alt+3) ............ enter supplier bills with unloading, weighbridge, transport
  │                                 → see landed cost per kg/bag before saving (preview)
  ├─ Purchase orders .............. place orders; check goods received; three-way match
  ├─ Payments (Alt+6) ............. pay suppliers / transporters; receive from customers
  ├─ Counter asks for approval .... type PIN + reason on the counter's screen
  ├─ Transport (Alt+T) ............ record trips and freight; link direct-delivery sales
  ├─ Sales bills (Alt+2) .......... owner may bill too, with discount / override / back-date
  └─ Cash book (Alt+C) ............ rent, salaries, drawings, capital, bank deposits

 EVENING
  ├─ Reports → Daily closing ...... check each shop closed; reopen a day if a bill was missed
  └─ Reports → Profit ............. profit by item / customer / site
```

### 7.2 Owner's week

- **Reports → Dues**: oldest customer bills; send reminders.
- **Stock → Counts**: count the godown; **post** the count (owner only) so differences become
  count-correction adjustments at average cost.
- **Reports → Exceptions**: round-number adjustments, adjustments just before a count, many
  returns to one customer, back-dated entries, cash near the limit.
- **Stock → Analysis**: what to reorder (reorder point, cover days, ABC, fast/slow/non-moving).

### 7.3 Owner's month

| Task | Screen |
| --- | --- |
| Profit and loss, break-even | Reports → P&L |
| Profit per ton by brand, shop, user | Reports → Profit cuts |
| Working capital, cash cycle (DIO, DSO, DPO) | Reports → Working capital |
| Discount leakage, price overrides | Reports → Overrides |
| Bank reconciliation | Reports → Bank (upload the bank's CSV) |
| Write-down stock below market | Stock → Value |
| Lock the month after the accountant files GST | Settings → Period lock |
| Integrity check and restore drill | Settings → System; `make prod-verify FULL=1`, `make prod-drill` |

### 7.4 What only the owner can do

- Reopen a closed day (with a reason).
- Post a stock count; write off a bad debt; write down stock.
- Reverse a cash-book voucher.
- Cancel an e-way bill or e-invoice (within 24 hours).
- Make a debit note (return to supplier).
- Link a direct-delivery sale to its supplier purchase.
- Book a supplier scheme rebate.
- Change the period lock.

---

## 8. Counter flow: a working day

### 8.1 The day at a glance

```text
 Sign in (counter1) ─► Today: own shop's sales so far
        │
        ▼
 ┌──────────────── repeat for each customer ────────────────┐
 │  Sales bills → New bill                                    │
 │    customer (+ site) → item → quantity → Enter adds line   │
 │    system fills price, GST, stock left, problems           │
 │    money taken now (cash / UPI / bank)                     │
 │    Ctrl+Enter saves → print A4                             │
 │    "Needs the owner" → owner types PIN → save again         │
 └────────────────────────────────────────────────────────────┘
        │
        ├─ Payments: customer pays an old bill ─► receipt
        ├─ Return within 2 days ─► open bill → Return goods ─► credit note
        ├─ E-way bill for a delivery over the threshold
        ├─ Goods arrive against a purchase order ─► goods receipt
        ├─ Supplier bill arrives (if allowed) ─► purchase entry (no cost shown)
        ├─ Cash book: loading labour, tea, bank deposit (today only)
        ├─ Stock: breakage / damage adjustment (today only), transfer out, lost sale log
        ▼
 Reports → Daily closing: count the drawer → note if short/over → Close the day
```

### 8.2 Making a bill, step by step (screen)

1. **Alt+2** (Sales bills), then **New bill** (or Alt+N).
2. Pick the **customer**. For a buyer with no account use **Walk-in customer**. If the customer has
   sites, pick the **site** (decides ship-to and place of supply).
3. For each line: **item**, **quantity**, **unit** (kg, ton, bag, piece…), and **source**:
   - *Shop*: from this shop's stock (default).
   - *Godown*: from the godown's stock (pick which one).
   - *Direct*: the supplier delivers straight to the site; no stock moves.
4. Press **Enter** in Quantity to add the next line. As you type, the screen calls
   `/invoices/preview` and shows: rate, taxable value, GST, line total, **stock available and
   left after**, and any **problems** in red.
5. Optional: slip weight (weighbridge slip). If it differs from the billed weight by more than
   0.50%, a note is required.
6. **Money taken now**: one row per mode (cash, UPI, bank) with amount and reference. Whatever is
   not paid becomes credit and is checked against the customer's limit.
7. **Ctrl+Enter** saves. The bill gets its number and the A4 PDF opens for printing.

### 8.3 When the screen says "Needs the owner"

| Message | Why | What happens |
| --- | --- | --- |
| A discount or a different price needs the owner | Counter cannot change price | Owner PIN → `discount` approval |
| This price needs the owner to approve it | Price is below average cost | Owner PIN → `below_cost` |
| Only the owner can back-date a bill | Date is not today | Owner PIN → `backdate` |
| Not approved for credit / past credit limit / overdue bills | Credit rules (B8) | Take payment, or owner PIN → `credit_override` |
| Return window closed | Return after 2 days | Owner PIN → `late_return` |
| Expense / adjustment needs the owner | Above the shop limit | Owner PIN → `expense` / `stock_adjustment` |

The owner types the PIN and a reason in the prompt on the counter's screen. The approval:
- is for **this counter user**, **this customer**, **one document**, and **expires in 10 minutes**;
- is recorded in the audit log (who asked, who approved, why);
- locks for 15 minutes after **5 wrong PINs**.

### 8.4 Things the counter must never try

- Edit or delete a bill: not possible. Use **Return goods** (credit note) and make a new bill.
- Take more than ₹2,00,000 cash from one customer in a day: refused (income-tax rule). Take UPI or bank.
- Bill on a closed day: refused until the owner reopens it.

### 8.5 Closing the day

1. **Reports → Daily closing**, pick today.
2. The screen shows: bills (count, first and last number), sales, returns, receipts by mode, cash
   paid out, expenses, deposits, and **"Should be"** in the drawer:
   `opening cash + cash in − cash out`.
3. Count the drawer and type **counted cash**. If it differs, write a note (required).
4. **Close the day**. The PDF is saved to storage (`closing/S1/2026/10/2026-10-10.pdf`) and the
   shop-day is locked. If saving the PDF fails, the day is **not** closed.

The very first closing at a shop asks for the opening cash by hand; after that it is the last
closing's counted cash.

---

## 9. Accountant flow

| When | Task | Screen |
| --- | --- | --- |
| Any time | Read bills, notes, purchases, payments, dues | Sales bills, Purchases, Payments, Reports → Dues |
| Month end | Upload GSTR-2B (portal JSON or CSV) and clear mismatches | Reports → GST returns |
| Month end | Download GSTR-1 (Excel to review, JSON for the portal); check "Documents issued" shows no missing numbers | Reports → GST returns |
| Month end | Read GSTR-3B figures; ITC at risk; ITC to reverse | Reports → GST, ITC risk, ITC reversal |
| Month end | Upload the bank statement CSV, reconcile | Reports → Bank |
| Month end | Export the day book to Tally (XML) after checks pass | Reports → Tally |
| After filing | Ask the owner to lock the period | (owner: Settings → Period lock) |

---

## 10. Execution flow inside the server

### 10.1 Every request

```text
 Browser
   │ POST /api/v1/invoices   Authorization: Bearer <token>   Idempotency-Key: <uuid>
   ▼
 nginx ─────────────► FastAPI app (app/main.py)
                        │
                        ├─ middleware: request id (X-Request-ID), access log, security headers,
                        │              Cache-Control: no-store
                        ├─ Pydantic validates the body (422 VALIDATION_ERROR if wrong shape)
                        ├─ get_principal (api/deps.py): decode JWT, re-read the user from the DB
                        │   (role is never trusted from the token), set the audit actor
                        ├─ role check: OwnerOnly / OwnerOrCounter / OwnerOrAccountant (403 if not)
                        ├─ service function: one database transaction
                        │     ├─ domain/ functions do the maths
                        │     ├─ rows written; numbering; ledgers
                        │     └─ commit → audit listener writes audit_log rows in the same commit
                        └─ response model chosen by principal.sees_cost
                             owner → e.g. InvoiceOwnerOut (with cost, profit)
                             others → InvoiceOut (no cost fields at all)
```

Errors always have one shape:

```json
{ "code": "CREDIT_LIMIT_EXCEEDED", "message": "…", "field": "payments",
  "request_id": "9f2c…", "requires_owner_approval": true }
```

### 10.2 Saving a sales bill (`POST /invoices`, `services/sales.py`)

This is the most important flow in the system. The same pricing code runs for the live preview
and for the save, so what the counter sees is exactly what gets saved.

```text
 1. Idempotency: same key seen before?  → return that bill (different customer/shop → 409)
 2. Lock the items (advisory lock) and the customer
        so two counters cannot sell the last bag, or use the last of a credit limit, together
 3. Load approvals: each must be unused, unexpired, asked by this user, for this customer
 4. price_invoice():
      a. counter may only bill from their own shop           (403)
      b. location active; party is a customer; site belongs to the party
      c. date not in the future; day not closed; period not locked   (DAY_CLOSED / PERIOD_LOCKED)
      d. back-dated? needs owner or `backdate` approval
      e. place of supply = site's state, else shop's state
         same state as the business → CGST + SGST; else IGST
         customer has GSTIN → B2B, else B2C
      f. for each line:
           convert quantity to base unit (whole bags only, etc.)
           slip weight check (> 0.50% needs a note)
           price: customer rate → market rate → none = PRICE_NOT_SET
           override / discount only for owner or with `discount` approval, reason required
           stock: shop or godown must hold the quantity (direct lines skip this)
           GST per line, rounded to paise
           selling below average cost → BELOW_COST unless owner / approval
      g. totals, round-off to the rupee
      h. money taken now: not more than the total; cash limit per customer per day
      i. credit check on the unpaid part: credit allowed? limit? overdue bills?
 5. Any problem → 409 with the first problem's code (and requires_owner_approval)
 6. Next gapless number from document_sequence (atomic upsert, same transaction)
 7. Insert sales_invoice + sales_line rows; each line keeps the average cost at that moment
 8. For each non-direct line: stock_ledger row OUT at average cost; cement lots picked oldest first
    For direct lines with a purchase line: drop_ship_link (cost = supplier's landed cost)
 9. party_ledger row: customer DEBIT (receivable) = grand total
10. Money taken now → payment rows + party_ledger CREDIT rows against this bill
11. Mark approvals used; if the owner waived a credit rule, audit "override" event
12. COMMIT (all of the above, or nothing)
13. Response: owner gets cost and profit per line; counter does not
```

### 10.3 Saving a purchase (`POST /purchases`, `services/purchases.py`)

```text
 1. Counter: own shop only, and only if shop setting counter_can_enter_purchases is on
 2. Supplier is a supplier; day open; period open
 3. Supplier's bill number not already entered for this supplier (DUPLICATE_BILL)
 4. For each line:
      convert billed and received quantity to base unit
      charges priced by basis (per ton / per base unit / per trip / flat)
      landed cost per base unit = (goods value + charges) ÷ RECEIVED quantity
         (GST excluded unless include_gst_in_cost)
      weight check billed vs received; above 0.50% needs a note
 5. Cement lot week checks; three-way match against the purchase order if given
      (out of tolerance → MATCH_EXCEPTION for counter, owner may save)
 6. Next number S1P/26-27/00007
 7. Insert purchase, lines, costs
 8. Mode "stock": stock_ledger IN at landed cost (average cost recalculates)
    Mode "direct": no stock rows (goods went to a customer's site)
 9. party_ledger: supplier CREDIT (we owe) = goods + GST + charges on the supplier's bill
10. COMMIT
```

**Worked example (from the spec):** 10 tons TMT at ₹55,000/ton; unloading ₹250/ton, weighbridge
₹150 flat, transport ₹4,000 per trip.
Goods ₹5,50,000 + charges (2,500 + 150 + 4,000) ₹6,650 = ₹5,56,650 ÷ 10,000 kg = **₹55.665 per kg**.
If only 9,900 kg arrive, the same ₹5,56,650 is divided by 9,900, so the shortage raises the unit
cost instead of hiding in stock value.

### 10.4 Weighted-average cost

On every stock-in: `new average = (qty on hand × old average + qty in × cost in) ÷ (qty on hand + qty in)`.
One average per item for the whole business; quantity is tracked per place. Sales, transfers and
adjustments go out at the current average. A transfer never changes value.

### 10.5 Payment received (`POST /payments`, direction `received`)

```text
 1. Counter: own shop only. Mode cash / UPI / bank (no cheques)
 2. Cash: total cash from this customer today must stay below ₹2,00,000
 3. Number S1R/26-27/00015
 4. Allocation: bills the user ticked first, then oldest unpaid first;
    anything left over stays on the account as an advance
 5. party_ledger CREDIT rows, one per bill paid ("applies_to" that bill number)
 6. COMMIT
```

A payment **paid** to a supplier is the same in reverse (owner only). Advances to a supplier sit on
their account and are used against later bills.

### 10.6 Customer return (`POST /credit-notes`)

```text
 1. Within return_window_days (2) of the bill → counter at own shop may do it
    Later → owner, or counter with a `late_return` approval
 2. Quantity cannot exceed what is left on the line (RETURN_TOO_MUCH)
 3. Value pro rata to quantity; GST recalculated per line; round-off per note
 4. Stock back IN at the place it left, at the cost it left at (direct lines restock nothing)
 5. party_ledger CREDIT for the customer against that invoice number
 6. Number S1C/26-27/00003; A4 PDF
```

### 10.7 Daily closing (`POST /closings`)

```text
 1. Gather the day's figures for that shop (bills, notes, receipts, cash book)
 2. expected = opening cash + cash in − cash out
 3. counted ≠ expected and no note → CASH_NOTE_REQUIRED
 4. Render the PDF (no cost or profit on it), save to storage
    storage fails → nothing saved, day stays open
 5. Insert daily_closing → from now on ensure_day_open() refuses that shop-day
```

---

## 11. How to insert values: every document with examples

Conventions for every request:

- Money and quantities are **strings**: `"62000"`, `"10.5"`. Never send `62000.0` as a number.
- Dates are `YYYY-MM-DD`.
- IDs (`item_id`, `party_id`, `location_id`) come from the list endpoints (`GET /items`,
  `GET /parties`, `GET /locations`).
- Units are lower-case and must exist on the item (`kg`, `ton`, `bag`, `piece`…). Blank means the base unit.

### 11.1 Shop settings (owner) — `PUT /settings`

Screen: Settings → Shop.

```json
{
  "legal_name": "Sri Murugan Steels and Cements",
  "trade_name": "Murugan Steels",
  "state_code": "33",
  "gstin": "33ABCDE1234F1Z5",
  "pan": null,
  "cin": null,
  "address": "12, Main Road, Chennai 600040",
  "phone": "9840000000",
  "bank_name": "State Bank of India",
  "bank_account_no": "12345678901",
  "bank_ifsc": "SBIN0001234",
  "bank_branch": "Anna Nagar",
  "invoice_terms": "Goods once sold are taken back only within 2 days.",
  "jurisdiction": "Chennai",
  "return_window_days": 2,
  "weight_variance_pct": "0.50",
  "default_credit_limit": "10000",
  "default_credit_days": 7,
  "rates_include_gst": false,
  "include_gst_in_cost": false,
  "cash_receipt_limit": "200000",
  "counter_can_enter_purchases": true
}
```

The GSTIN is checked for format and check digit, and its first two digits must equal `state_code`.
`pan` is optional: left blank, the bill prints the PAN inside the GSTIN; if you give one it must
match characters 3 to 12 of the GSTIN. `cin` (a company's 21-character Corporate Identification
Number, for example `U45200TN2015PTC098765`) is optional and prints on the bill under the PAN.
The settings form sends every field, so it keeps these two. If Duolink corrects your GSTIN or
other bill details for you, the change appears in the audit log as done by "Duolink: <name>".
All other settings and their defaults are in [section 14](#14-settings-reference).

**A temporary password.** When Duolink onboards a company it can ask the owner to choose their own
password first. That owner signs in with the password Duolink gave, sees only "Choose a new
password", and enters it twice. After that they sign in again as normal. Until then no other
screen opens.

### 11.2 Location (owner) — `POST /locations`

```json
{ "code": "S2", "name": "Shop 2", "kind": "shop", "state_code": "33", "address": "Ambattur" }
```

`kind`: `shop` or `godown`. `code`: 1–2 upper-case letters/digits, permanent.

### 11.3 User (owner) — `POST /users`

```json
{
  "username": "counter2",
  "full_name": "Kumar (Shop 2 counter)",
  "role": "counter",
  "password": "a-long-password-here",
  "location_ids": [3]
}
```

`role`: `owner`, `counter`, `accountant`. Counter users need at least one location.
Switch someone off with `PATCH /users/{id}` `{ "is_active": false }`.

### 11.4 Owner approval PIN (owner) — `POST /auth/pin`

```json
{ "current_password": "owner-pass-123", "pin": "4826" }
```

### 11.5 Item (owner) — `POST /items`

TMT bar sold by kg, ton or piece:

```json
{
  "name": "TMT 12mm Fe500D",
  "category": "tmt",
  "brand": "Brand A",
  "hsn": "72142090",
  "gst_rate": "18",
  "base_unit": "kg",
  "size": "12mm",
  "grade": "Fe500D",
  "weight_per_piece_kg": "10.656",
  "min_margin": "1.00",
  "units": [ { "unit": "ton", "factor_to_base": "1000" } ],
  "lead_time_days": 7,
  "safety_days": 2
}
```

Cement counted in whole bags (20 bags of 50 kg = 1 ton):

```json
{
  "name": "Cement OPC 53 Grade",
  "category": "cement",
  "brand": "Brand C",
  "hsn": "25232930",
  "gst_rate": "18",
  "base_unit": "bag",
  "base_whole_only": true,
  "units": [ { "unit": "ton", "factor_to_base": "20" } ]
}
```

| Field | Meaning |
| --- | --- |
| `category` | `tmt`, `pipe`, `cement`, `wire`, `angle`, `channel`, `other` |
| `hsn` | 4–8 digits, printed on the bill |
| `gst_rate` | Percent, e.g. `"18"`. Confirm each rate with the accountant |
| `base_unit` | Unit stock is counted in. **Cannot change** once the item exists |
| `base_whole_only` | `true` for bags and pieces: 30.2 bags is refused |
| `units` | Extra units with their factor to the base. Do not list the base unit |
| `weight_per_piece_kg` | For kg items: makes the unit `piece` available automatically |
| `min_margin` | Owner only: minimum profit per base unit; selling below it warns |

GST rates above are examples; the accountant must confirm the current rate for each HSN.

**Importing many items from Excel** (Items → Import, or `POST /items/import?dry_run=true` with the
file as multipart `file`). Download the template from `GET /items/import/template`. One row per item:

| name | category | brand | hsn | gst_rate | base_unit | base_whole_only | size | grade | weight_per_piece_kg | min_margin | units |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TMT 12mm Fe500D | tmt | Brand A | 72142090 | 18 | kg | false | 12mm | Fe500D | 10.656 | 1 | ton:1000 |
| Cement OPC 53 | cement | Brand C | 25232930 | 18 | bag | true | | | | 5 | ton:20 |

`units` is `unit:factor[:whole]`, comma-separated (e.g. `ton:1000,bundle:50:whole`). The same
name updates the existing item. **One bad row refuses the whole file.** Run with `dry_run=true`
first; it checks without saving.

### 11.6 Customer with sites (owner or counter) — `POST /parties`

```json
{
  "name": "Ravi Builders",
  "type": "customer",
  "segment": "contractor",
  "gstin": "33AAACR1234K1Z2",
  "state_code": "33",
  "address": "45, 2nd Street, Anna Nagar, Chennai",
  "phone": "9876543210",
  "credit_allowed": true,
  "credit_limit": "100000",
  "credit_days": 15,
  "sites": [
    { "name": "Anna Nagar villa", "address": "Plot 7, Anna Nagar", "state_code": "33" },
    { "name": "Bengaluru project", "address": "Whitefield", "state_code": "29",
      "gstin": "29AAACR1234K1Z6" }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `type` | `customer`, `supplier`, `both` |
| `segment` | `retail`, `contractor`, `bulk` (for the segment chart) |
| `credit_allowed`, `credit_limit`, `credit_days` | **Owner only.** Blank limit/days = shop defaults (₹10,000, 7 days) |
| site `gstin` | Blank prints "URP" on e-way bills. A site in another state makes the bill IGST |

Add a site later: `POST /parties/{id}/sites`.

### 11.7 Supplier — `POST /parties`

```json
{
  "name": "ABC Steel Distributors",
  "type": "supplier",
  "gstin": "33AABCA1111B1Z9",
  "state_code": "33",
  "address": "Industrial Estate, Guindy",
  "phone": "9444000000",
  "lead_time_days": 5
}
```

A supplier has no sites, segment or credit.

### 11.8 Opening balances (owner) — `POST /opening`, then `POST /opening/post`

Enter these on the day before go-live, after the last paper bill. They are **drafts** until posted;
fix drafts with `PATCH /opening/{id}` or `DELETE /opening/{id}`. After posting they are locked.

```json
{ "kind": "stock", "as_of": "2026-10-31", "item_id": 1, "location_id": 1,
  "quantity": "8500", "unit_cost": "54.80" }
```
```json
{ "kind": "receivable", "as_of": "2026-10-31", "party_id": 5, "site_id": 2,
  "amount": "42000", "note": "Paper book page 112" }
```
```json
{ "kind": "payable", "as_of": "2026-10-31", "party_id": 9, "amount": "150000" }
```

| `kind` | Meaning | Fields |
| --- | --- | --- |
| `stock` | Stock on hand at a place | `item_id`, `location_id`, `quantity` (base unit), `unit_cost` |
| `receivable` | A customer owes us | `party_id`, `site_id` (optional), `amount` |
| `customer_advance` | We hold a customer's advance | `party_id`, `amount` |
| `payable` | We owe a supplier | `party_id`, `amount` |
| `supplier_advance` | A supplier holds our advance | `party_id`, `amount` |

Post them (check totals against the paper books first):

```json
{ "kinds": ["stock", "receivable", "customer_advance", "payable", "supplier_advance"] }
```

### 11.9 Daily market rates (owner) — `PUT /rates/market`

```json
{
  "effective_date": "2026-11-01",
  "rates": [
    { "item_id": 1, "rate": "62000", "unit": "ton" },
    { "item_id": 2, "rate": "380",   "unit": "bag" }
  ]
}
```

Stored per base unit excluding GST (₹62,000/ton → ₹62/kg). One rate per item per day; entering
the day again overwrites it. The answer lists `warnings` for items below cost or below minimum margin.

**Customer rate** — `POST /customer-rates`:

```json
{ "party_id": 5, "item_id": 1, "rate": "61000", "unit": "ton",
  "valid_from": "2026-11-01", "valid_to": "2026-11-30" }
```

**Margin** — `PUT /margins`: `[{ "item_id": 1, "margin": "1200", "unit": "ton" }]`

### 11.10 Purchase (supplier bill) — `POST /purchases`

Preview the landed cost first with the same body on `POST /purchases/preview` (owner).

```json
{
  "supplier_id": 9,
  "location_id": 2,
  "bill_no": "ABC/2026/1189",
  "bill_date": "2026-11-01",
  "due_date": null,
  "mode": "stock",
  "note": "Lorry TN09AB1234",
  "lines": [
    {
      "item_id": 1,
      "unit": "ton",
      "quantity": "10",
      "received_quantity": "9.94",
      "rate": "55000",
      "weight_note": "Weighbridge 9,940 kg; supplier informed",
      "charges": [
        { "component_id": 1, "amount": "250" },
        { "component_id": 3, "amount": "150" },
        { "component_id": 4, "amount": "4000", "on_supplier_bill": true }
      ]
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `mode` | `stock` = goods into our place; `direct` = supplier delivered to a customer's site (no stock) |
| `quantity` / `rate` | As on the supplier's bill, in the line's `unit` |
| `received_quantity` | Weighbridge figure (same unit). Blank = same as billed. Divides the cost |
| `gst_rate` | Blank = the item's rate |
| `charges[].component_id` | A charge type; or give `name` + `basis` instead |
| `charges[].amount` | Per the charge's basis: per ton, per base unit, per trip, or flat |
| `on_supplier_bill` | `true` if the supplier billed this charge (added to what we owe them) |
| `weight_note` | Required when billed vs received differs by more than `weight_variance_pct` |
| `purchase_order_id` | Optional: checks the bill against the order and goods received |
| `mfg_week`, `mfg_year` | Cement only: the week printed on the bag (lots sold oldest first) |

### 11.11 Sales bill — `POST /invoices`

Send a fresh `Idempotency-Key` header (any UUID). Try the same body on `POST /invoices/preview`
first: it returns prices, tax, stock and `problems` without saving.

```bash
curl -X POST http://localhost:8000/api/v1/invoices \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(uuidgen)" -d @bill.json
```

`bill.json`:

```json
{
  "location_id": 1,
  "party_id": 5,
  "site_id": 2,
  "vehicle_no": "TN09AB1234",
  "remark": "Deliver before 10 am",
  "lines": [
    { "item_id": 1, "quantity": "1", "unit": "ton", "source": "shop" },
    { "item_id": 2, "quantity": "10", "unit": "bag", "source": "godown", "source_location_id": 2 }
  ],
  "payments": [
    { "mode": "upi", "amount": "50000", "reference": "UPI 612345678901" }
  ],
  "approval_ids": []
}
```

With the rates above (₹62/kg TMT, ₹380/bag cement, both 18%, same state):

| Line | Taxable | CGST 9% | SGST 9% | Total |
| --- | --- | --- | --- | --- |
| TMT 1 ton = 1,000 kg × ₹62 | 62,000.00 | 5,580.00 | 5,580.00 | 73,160.00 |
| Cement 10 bags × ₹380 | 3,800.00 | 342.00 | 342.00 | 4,484.00 |
| **Bill** | **65,800.00** | **5,922.00** | **5,922.00** | **77,644.00** |

Paid now ₹50,000 → balance ₹27,644 goes on credit and is checked against Ravi Builders' ₹1,00,000 limit.

| Line field | Meaning |
| --- | --- |
| `invoice_date` | Blank = today. Another date needs the owner |
| `source` | `shop` (default), `godown` (+ `source_location_id`), `direct` (+ optional `purchase_line_id`) |
| `rate_override` + `rate_override_reason` | Owner (or `discount` approval): a typed price per `unit` |
| `discount` + `discount_reason` | Owner (or approval): rupees off the line |
| `slip_weight` + `weight_note` | Weighbridge slip weight; note needed above the variance limit |

**With an owner approval (counter):** when the save answers 409 with
`requires_owner_approval: true`, get an approval and resend with its id:

```json
POST /approvals
{ "pin": "4826", "action": "credit_override", "reason": "Old customer, pays on Friday", "party_id": 5 }
→ { "id": 31, "action": "credit_override", "expires_at": "…", "approved_by_name": "Shop Owner" }
```

Then send the bill again with `"approval_ids": [31]`. Actions: `credit_override`, `below_cost`,
`discount`, `backdate`, `late_return`, `expense`, `stock_adjustment`, `po_mismatch`.

### 11.12 Payment — `POST /payments` (with `Idempotency-Key`)

Customer pays an old bill:

```json
{
  "direction": "received",
  "party_id": 5,
  "site_id": 2,
  "location_id": 1,
  "amount": "27644",
  "mode": "bank",
  "reference": "NEFT N123456789",
  "payment_date": "2026-11-03",
  "allocations": [ { "bill_no": "S1/26-27/00042", "amount": "27644" } ]
}
```

Leave `allocations` empty to pay oldest bills first; extra money becomes an advance.

Paying a supplier (owner): same shape with `"direction": "paid"` and the supplier's `party_id`.
Paying a transporter's freight: allocate to `TRIP-<trip id>`.

`mode`: `cash`, `upi`, `bank`. No cheques.

### 11.13 Customer return — `POST /credit-notes`

```json
{
  "invoice_id": 42,
  "reason": "2 bags damaged in delivery",
  "lines": [ { "line_id": 118, "quantity": "2" } ],
  "approval_ids": []
}
```

`line_id` is the sales line; `quantity` is in that line's unit. After 2 days add a `late_return` approval.

### 11.14 Return to supplier (owner) — `POST /debit-notes`

```json
{ "purchase_id": 7, "reason": "Rusted bars returned", "lines": [ { "line_id": 21, "quantity": "0.5" } ] }
```

### 11.15 Stock transfer — `POST /transfers`

```json
{
  "from_location_id": 2,
  "to_location_id": 1,
  "note": "Godown to Shop 1",
  "lines": [ { "item_id": 1, "quantity": "2", "unit": "ton" } ]
}
```

Counter can only transfer **out of** their own shop. The origin must hold the quantity.

### 11.16 Stock count — three calls

```text
POST /stock-counts               { "location_id": 2, "item_ids": [1, 2] }     → count id 4 (draft)
PUT  /stock-counts/4/lines       { "lines": [ { "item_id": 1, "counted_qty": "8420" },
                                              { "item_id": 2, "counted_qty": "295" } ] }
POST /stock-counts/4/post        (owner only) → differences become count corrections
```

Leave `item_ids` out to count every item with stock at that place.

### 11.17 Stock adjustment — `POST /stock-adjustments`

```json
{
  "location_id": 1,
  "reason": "breakage",
  "note": "Bags torn while unloading",
  "lines": [ { "item_id": 2, "quantity": "3", "unit": "bag" } ],
  "approval_ids": []
}
```

| `reason` | Direction |
| --- | --- |
| `breakage`, `damage`, `theft`, `free_sample`, `weighbridge_loss` | out |
| `weighbridge_gain` | in |
| `count_correction` | either: set `"direction": "in"` or `"out"` per line |

Counter: own shop, today only; above ₹10,000 needs a `stock_adjustment` approval.

### 11.18 Cash book — `POST /cash-book`

```json
{ "location_id": 1, "kind": "expense", "mode": "cash", "amount": "2000",
  "category_id": 4, "paid_to": "Loading labour", "note": "Unloading 2 lorries" }
```
```json
{ "location_id": 1, "kind": "bank_deposit", "mode": "cash", "amount": "150000", "reference": "SBI slip 4471" }
```

`kind`: `expense` (needs `category_id`), `bank_deposit`, `bank_withdrawal` (both always cash),
`owner_drawing`, `owner_capital`. Counter: expenses and bank deposits at own shop, today only;
expenses above ₹5,000 need an `expense` approval. Undo (owner): `POST /cash-book/{id}/reverse`
`{ "reason": "Entered twice" }`.

Expense heads: `GET /expense-categories`; owner adds `POST /expense-categories`
`{ "name": "Generator diesel", "nature": "variable" }` (`fixed`, `variable`, `interest`).

### 11.19 Daily closing — `POST /closings`

```json
{ "location_id": 1, "closing_date": "2026-11-03", "counted_cash": "48250",
  "note": "₹50 short, change given to walk-in" }
```

Look first with `GET /closings/preview?location_id=1&closing_date=2026-11-03`. For the first
closing at a shop add `"opening_cash": "5000"`. Owner reopens: `POST /closings/{id}/reopen`
`{ "reason": "Bill S1/26-27/00051 was missed" }`.

### 11.20 E-way bill — `POST /invoices/{id}/eway-bill`

```json
{ "distance_km": 18, "from_pincode": "600040", "to_pincode": "600101", "vehicle_no": "TN09AB1234" }
```

Add or change the vehicle later: `POST /invoices/{id}/eway-bill/vehicle`. If the provider is down,
make it on the portal and record it: `POST /invoices/{id}/eway-bill/manual`
`{ "number": "331000000123", "vehicle_no": "TN09AB1234" }`. Many at once: `POST /eway-bills/batch`.
Bills that still need one: `GET /eway-bills/pending`.

### 11.21 Transport (owner)

```json
POST /vehicles  { "number": "TN 09 AB 1234", "owner_name": "Selvam", "phone": "9000000000", "is_own": false }
POST /trips     { "vehicle_id": 1, "location_id": 1, "invoice_id": 42,
                  "from_place": "Shop 1", "to_place": "Anna Nagar site", "freight_amount": "1500" }
```

A hired vehicle gets a supplier account "Transport: Selvam (TN09AB1234)". Freight is owed to it as
`TRIP-<id>` and paid through Payments. A trip is for a sale or a purchase, not both.

### 11.22 Purchase order and goods receipt

```json
POST /purchase-orders  (owner)
{ "supplier_id": 9, "location_id": 2, "expected_date": "2026-11-08",
  "lines": [ { "item_id": 1, "unit": "ton", "quantity": "10", "rate": "55000" } ] }

POST /purchase-orders/{id}/receipts  (owner, or counter at that shop, today)
{ "note": "Lorry 1 of 1", "lines": [ { "order_line_id": 11, "quantity": "9.8" } ] }
```

A goods receipt moves no stock. Stock enters when the supplier's bill is entered with
`"purchase_order_id"`. Tolerances: quantity 1%, rate 0.5% (settings).

### 11.23 Other entries

| What | Call | Body |
| --- | --- | --- |
| Lost sale (asked, not in stock) | `POST /lost-sales` | `{ "location_id": 1, "item_id": 2, "quantity": "10", "unit": "bag", "note": "Wanted PPC" }` |
| Attachment (slip, delivery proof) | `POST /attachments` (multipart) | `ref_type` = `purchase` / `sales_invoice` / `trip`, `ref_id`, `kind` = `weighbridge` / `delivery` / `other`, `file` (JPEG, PNG, WebP, PDF ≤ 8 MB) |
| Supplier scheme | `POST /schemes` | target in the base unit, period, rebate rule; owner books the rebate with `POST /schemes/{id}/book-rebate` |
| Bad-debt write-off (owner) | `POST /write-offs` | `{ "location_id": 1, "party_id": 5, "amount": "4500", "reason": "Customer closed business" }` |
| Write-down to market (owner) | `POST /inventory/writedowns` | `{ "location_id": 1, "item_ids": [1], "note": "TMT market fell" }` |
| Period lock (owner) | `PUT /period-lock` | `{ "locked_through": "2026-10-31", "reason": "October GSTR-1 filed" }` |
| GSTR-2B upload | `POST /gst/gstr2b` (multipart) | `period=2026-10`, `file` (portal JSON or CSV) |
| Bank statement | `POST /bank/statements` (multipart) | `bank_account_id`, `file` (bank's CSV) |
| Tally export | `GET /tally/export?date_from=2026-10-01&date_to=2026-10-31&masters=true` | (download) |

---

## 12. Error codes and what to do

| Code | Status | Means | Do this |
| --- | --- | --- | --- |
| `NOT_AUTHENTICATED` | 401 | Token missing or expired | Sign in again (the app refreshes automatically once) |
| `ACCOUNT_LOCKED` | 423 | 5 wrong passwords | Wait, or owner resets the password |
| `PERMISSION_DENIED` | 403 | Role or shop not allowed | Use the right user, or your own shop |
| `VALIDATION_ERROR` | 422 | Wrong field shape; `field` names it | Fix that field |
| `PRICE_NOT_SET` | 409 | No market or customer rate for the item | Owner enters today's rate |
| `INSUFFICIENT_STOCK` | 409 | Place does not hold the quantity | Pick godown, transfer stock, or reduce quantity |
| `UNKNOWN_UNIT` / `UNIT_NOT_WHOLE` | 409 | Unit not on the item / fraction of a bag | Use a listed unit / a whole number |
| `DISCOUNT_NEEDS_OWNER` | 409 | Counter changed price or gave discount | Owner PIN (`discount`) |
| `BELOW_COST` | 409 | Price below average cost | Owner PIN (`below_cost`) |
| `BACKDATE_NEEDS_OWNER` | 409 | Date is not today | Owner PIN (`backdate`) |
| `CREDIT_NOT_ALLOWED` / `CREDIT_LIMIT_EXCEEDED` / `OVERDUE_INVOICES` | 409 | Credit rules | Take payment now, or owner PIN (`credit_override`) |
| `CASH_LIMIT_REACHED` | 409 | ₹2,00,000 cash from one customer today | Take UPI or bank |
| `OVERRIDE_REASON` / `DISCOUNT_REASON` | 409 | Missing reason | Type a reason |
| `WEIGHT_NOTE_REQUIRED` | 409 | Weight differs above 0.50% | Write a note on that line |
| `RETURN_WINDOW_CLOSED` | 409 | Return after 2 days | Owner PIN (`late_return`) |
| `RETURN_TOO_MUCH` | 422 | More than left on the bill line | Reduce quantity |
| `DAY_CLOSED` | 409 | Shop-day already closed | Owner reopens the day |
| `PERIOD_LOCKED` | 409 | Date on or before the books lock | Owner changes the lock (with reason) |
| `DUPLICATE_BILL` | 409 | Supplier bill number already entered | Check the earlier purchase |
| `CASH_NOTE_REQUIRED` | 409 | Drawer differs from "should be" | Write a note |
| `MATCH_EXCEPTION` | 409 | Supplier bill differs from order/receipt | Owner PIN (`po_mismatch`) or correct the bill |
| `APPROVAL_INVALID` | 409 | Approval used, expired, or for another customer | Ask the owner again |
| `IDEMPOTENCY_CONFLICT` | 409 | Same key reused for another bill | Use a new key |
| `GSP_TIMEOUT`, `GSP_DOWN`… | 502 | E-way provider failed; nothing saved | Retry, or record a portal-made number |

---

## 13. Database tables

All tables carry `id`, `tenant_id`, `created_at`, `updated_at`, `created_by`, `updated_by`.
Money is `NUMERIC(14,2)`, quantity `NUMERIC(14,3)`, unit cost `NUMERIC(14,4)`.

| Area | Tables |
| --- | --- |
| Setup | `shop_settings`, `location`, `app_user`, `user_location`, `auth_session`, `audit_log`, `document_sequence` |
| Masters | `item`, `item_unit`, `party`, `site`, `cost_component`, `vehicle`, `expense_category` |
| Prices | `market_rate`, `customer_rate`, `item_margin` |
| Opening | `opening_balance` |
| Ledgers (append-only) | `stock_ledger`, `party_ledger` |
| Purchasing | `purchase_order`, `purchase_order_line`, `goods_receipt`, `goods_receipt_line`, `purchase`, `purchase_line`, `purchase_cost`, `supplier_scheme` |
| Sales | `sales_invoice`, `sales_line`, `sales_line_lot`, `lost_sale`, `drop_ship_link` |
| Money | `payment`, `approval`, `cash_entry`, `bad_debt_writeoff` |
| Returns | `credit_note`, `credit_note_line`, `debit_note`, `debit_note_line` |
| Stock operations | `stock_transfer`, `stock_transfer_line`, `stock_count`, `stock_count_line`, `stock_adjustment`, `stock_adjustment_line`, `stock_writedown`, `stock_writedown_line` |
| Transport | `trip` |
| Compliance | `eway_bill`, `einvoice`, `gstr2b_import`, `tally_ledger` |
| Banking | `bank_account`, `bank_statement`, `bank_statement_line` |
| Documents | `attachment`, `daily_closing` |

What writes to the ledgers:

| Document | `stock_ledger` | `party_ledger` |
| --- | --- | --- |
| Opening balance | IN (stock) | debit/credit (dues, advances) |
| Purchase (mode stock) | IN at landed cost | supplier credit |
| Purchase (mode direct) | none | supplier credit |
| Sales bill | OUT at average cost (not direct lines) | customer debit |
| Payment received / paid | none | customer credit / supplier debit |
| Credit note | IN at original cost | customer credit |
| Debit note | OUT at landed cost | supplier debit |
| Transfer | OUT at origin, IN at destination | none |
| Stock count post / adjustment | IN or OUT at average cost, with reason | none |
| Write-down | OUT at old average, IN at market value | none |
| Trip freight | none | transporter credit |
| Write-off | none | customer credit |

---

## 14. Settings reference

Owner edits these in Settings → Shop (`PUT /settings`). The "confirm" column says who must agree
before go-live (see [GO_LIVE](GO_LIVE.md)).

| Setting | Default | Controls | Confirm |
| --- | --- | --- | --- |
| `return_window_days` | 2 | Returns without approval | Owner |
| `weight_variance_pct` | 0.50 | Weight difference that needs a note | Owner |
| `default_credit_limit` / `default_credit_days` | ₹10,000 / 7 | Credit for approved customers without their own terms | Owner |
| `include_gst_in_cost` | off | GST counted in landed cost | Accountant |
| `rates_include_gst` | off | Rates typed with GST included | Owner |
| `cash_receipt_limit` | ₹2,00,000 | Cash from one customer per day | Accountant |
| `eway_threshold_interstate` / `_intrastate` | ₹50,000 / ₹1,00,000 | When an e-way bill is required | Accountant |
| `einvoice_enabled` | off | IRN for B2B bills | Accountant |
| `counter_can_enter_purchases` | on | Counter enters supplier bills | Owner |
| `expense_approval_limit` | ₹5,000 | Counter expense needing PIN | Owner |
| `adjustment_approval_limit` | ₹10,000 | Counter stock adjustment needing PIN | Owner |
| `itc_reverse_shortages` | on | Shortages in "ITC to reverse" | Accountant |
| `provision_pct_*` | 0 / 1 / 2 / 10 / 50 % | Doubtful-debt provision per aging bucket | Accountant |
| `default_lead_time_days` / `default_safety_days` | 7 / 2 | Reorder point | Owner |
| `nrv_selling_cost_pct`, `nrv_writedown_enabled` | 0, on | Stock value at market | Accountant |
| `po_qty_tolerance_pct` / `po_rate_tolerance_pct` | 1 / 0.5 | Three-way match | Owner |
| `bank_match_days` | 3 | Bank line ↔ entry matching window | Accountant |
| `exception_*` | various | Exception report thresholds (0 switches a rule off) | Owner |

Server settings (`.env`): `APP_ENV`, `JWT_SECRET`, `GSP_PROVIDER` (`fake` only in development),
`STORAGE_PROVIDER` (`local` or `s3`), `MAX_UPLOAD_MB`, `SEED_*`. See `.env.example` and
[DEPLOYMENT](DEPLOYMENT.md).

---

## 15. Common questions

**A bill has a mistake. How do I change it?**
You cannot edit it. Make a credit note for the wrong part (Sales bills → open the bill → Return
goods) and a new correct bill. For a supplier bill, the owner makes a debit note.

**How do I set stock to the right number?**
Do a stock count (Stock → Counts) and the owner posts it; or make a stock adjustment with a reason.
Stock is never typed in directly.

**Why can't the counter see the profit?**
By design (rule B4). The server leaves cost fields out of every answer to non-owners.

**The bill says "no rate".**
The owner has not entered a market rate for that item on or before today. Daily rates (Alt+7).

**A day was closed but a bill was forgotten.**
Owner: Reports → Daily closing → Reopen, with a reason. Make the bill, then close the day again.

**Where are PDFs saved?**
Closing PDFs under `closing/<shop>/<yyyy>/<mm>/<date>.pdf` in the storage folder or S3 bucket.
Bills and notes are generated on demand (`GET /invoices/{id}/pdf`). Outside production every PDF
carries a TEST watermark.

**How do I know the books are right?**
Settings → System → check the books, or `make prod-verify FULL=1`. It checks number gaps, totals,
ledgers against documents, stock replay and every stored file.

**Can I add a second shop later?**
Yes: Settings → Shops and godown → add `S2`, then a counter user for it. Shop pickers appear on
every screen once there are two shops.
