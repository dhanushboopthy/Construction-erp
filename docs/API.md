# API conventions

Base path `/api/v1`. Interactive docs at `/api/docs` in development (off in production).

## Requests and responses

- JSON in and out. Money and quantities are **decimal strings** (`"1180.50"`), never floats.
- Dates `YYYY-MM-DD`; timestamps ISO 8601 in UTC. The UI shows Asia/Kolkata.
- Lists: `?limit=50&offset=0` (max 200) → `{items, total, limit, offset}`.
- Writes that touch several tables run in one transaction.
- Invoice and payment creation take an `Idempotency-Key` header (Milestone 6, G19).

## Errors

Every error has the same body:

```json
{ "code": "CREDIT_LIMIT_EXCEEDED", "message": "…", "field": null, "request_id": "9f2c…",
  "requires_owner_approval": true }
```

| Status | Code examples | Meaning |
| --- | --- | --- |
| 401 | `NOT_AUTHENTICATED` | Missing, expired or invalid token. The client refreshes once. |
| 403 | `PERMISSION_DENIED` | Role not allowed. |
| 404 | `NOT_FOUND` | |
| 409 | `USERNAME_TAKEN`, `LAST_OWNER`, `CREDIT_LIMIT_EXCEEDED`, `BELOW_COST`, `RETURN_WINDOW_CLOSED` | Business rule. With `requires_owner_approval: true` the UI offers the owner PIN prompt. |
| 422 | `VALIDATION_ERROR` | `field` names the first bad field; `errors` lists all. |
| 423 | `ACCOUNT_LOCKED` | Too many wrong passwords. |

## Auth flow

1. `POST /auth/login {username, password}` → `{access_token, expires_in, user}` + refresh cookie.
2. Send `Authorization: Bearer <access_token>`.
3. On 401, `POST /auth/refresh` (cookie only) → new token + new cookie; retry once.
4. `POST /auth/logout` revokes the session and clears the cookie.

## Role-shaped responses

Endpoints that return cost, margin or profit use separate response models for owners and
staff (for example `ItemOwnerOut` and `ItemOut`). Choose the model with `principal.sees_cost`;
never rely on the UI to hide fields. Test each such endpoint as a counter user.

## Endpoints (FM2: stock adjustments, ITC to reverse)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/stock-adjustments?location_id=&date_from=&date_to=` (this month by default) | all roles (counter: own shop); values, totals by reason and ITC only for the owner |
| GET | `/stock-adjustments/{id}` | as above |
| POST | `/stock-adjustments` (`reason`, `lines[{item_id, quantity, unit, direction}]`, `approval_ids`) | owner (any place, may back-date); counter: own shop, today; above `adjustment_approval_limit` needs a `stock_adjustment` approval (409 `ADJUSTMENT_NEEDS_OWNER`) |
| GET | `/reports/itc-reversal?period=2026-10` | owner, accountant |

Reasons: `breakage`, `damage`, `theft`, `free_sample`, `weighbridge_loss` (out only),
`weighbridge_gain` (in only), `count_correction` (either; `direction` required). Errors:
`WRONG_DIRECTION`, `DIRECTION_REQUIRED`, `DUPLICATE_ITEM`, `INSUFFICIENT_STOCK`,
`UNIT_NOT_WHOLE`, `UNKNOWN_UNIT`, `BACKDATE_NEEDS_OWNER`, `FUTURE_DATE`, `DAY_CLOSED`. The P&L
gains `stock_loss` (adjustments and counts, net), taken off gross profit and contribution.
Settings gain `adjustment_approval_limit` (₹10,000) and `itc_reverse_shortages` (true).

## Endpoints (FM1: cash book, expenses, profit and loss)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/expense-categories` (`include_inactive` for the owner) | all roles |
| POST · PATCH | `/expense-categories` · `/expense-categories/{id}` | owner |
| GET | `/cash-book?location_id=&date_from=&date_to=` (today by default) | owner, accountant; counter: own shop |
| POST | `/cash-book` | owner; counter: expenses and bank deposits at own shop, today only; expenses above `expense_approval_limit` need an `expense` approval (409 `EXPENSE_NEEDS_OWNER`) |
| POST | `/cash-book/{id}/reverse` (`reason`) | owner |
| GET | `/reports/pnl?period=2026-10&location_id=` | owner |
| GET | `/kpis/definitions` | all roles (owner-only metrics only for the owner) |

Errors: `CASH_ONLY` (deposit or withdrawal not in cash), `CATEGORY_REQUIRED`,
`CATEGORY_NOT_ALLOWED`, `CATEGORY_INACTIVE`, `BACKDATE_NEEDS_OWNER`, `FUTURE_DATE`, `DAY_CLOSED`,
`ALREADY_REVERSED`, `IS_REVERSAL`, `BAD_PERIOD`, `FUTURE_PERIOD`. `/reports/today` gains
`net_sales_today` (excl. GST, net of returns); closing figures gain the cash-book lines
(`cash_expenses`, `bank_deposits`, `bank_withdrawals`, `owner_drawings`, `owner_capital`,
`paid_to_parties`, `cash_in`, `cash_out`).

## Endpoints (Milestone 14)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/system/status` | owner |
| POST | `/system/verify?full=true\|false` | owner |

Every other route needs a sign-in; the only open ones are `/health`, `/health/ready`,
`/auth/login`, `/auth/refresh` and `/auth/logout`. All `/api` answers are `Cache-Control: no-store`.

## Endpoints (Milestone 13)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/gst/gstr1?period=2026-10` | owner, accountant |
| GET | `/gst/gstr1/export?period=&format=json\|xlsx` | owner, accountant |
| GET | `/gst/gstr3b?period=` | owner, accountant |
| POST | `/gst/gstr2b` (multipart: `period`, `file`) | owner, accountant |
| GET | `/gst/gstr2b?period=` | owner, accountant |

Codes: `BAD_PERIOD`, `GSTR2B_UNREADABLE`, `GSTR2B_EMPTY`.

## Endpoints (Milestone 12)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/reports/today` | all roles; payables not for counter, profit owner only |
| GET | `/closings/preview?location_id=&closing_date=` | owner, accountant; counter: own shop. `profit` for the owner only |
| POST | `/closings` `{location_id, closing_date, counted_cash, opening_cash?, note?}` | owner, counter (own shop) |
| POST | `/closings/{id}/reopen` `{reason}` | owner |
| GET | `/closings` · `/closings/{id}/pdf` | owner, accountant; counter: own shop |
| GET | `/reports/profit?group=item\|customer\|site&date_from=&date_to=` | owner |
| GET | `/reports/sales-by-segment?start_year=` | owner, accountant |

New codes: `DAY_CLOSED`, `ALREADY_CLOSED`, `NOT_CLOSED`, `CASH_NOTE_REQUIRED`, `STORAGE_FAILED`,
`BAD_RANGE`, `RANGE_TOO_LONG`.

## Endpoints (Milestone 11)

| Method | Path | Who |
| --- | --- | --- |
| POST | `/attachments` (multipart: `ref_type`, `ref_id`, `kind`, `note?`, `file`) | owner; counter: own shop's purchases and bills |
| GET | `/attachments?ref_type=&ref_id=` · `/attachments/{id}/file` | owner, accountant; counter: own shop (not trips) |
| GET | `/schemes` (`party_id`, `alerts_only`) | owner, accountant |
| POST/PATCH | `/schemes` · `/schemes/{id}` | owner |
| POST | `/schemes/{id}/book-rebate` | owner |

Purchase lines accept `weight_note`; bill lines accept `slip_weight` and `weight_note`; both come
back with `weight_variance_pct`, `weight_flagged`, `weight_note`. Codes: `WEIGHT_NOTE_REQUIRED`,
`FILE_TYPE_NOT_ALLOWED` (400), `FILE_TOO_LARGE` (413), `FILE_EMPTY`, `TOO_MANY_FILES`,
`FILE_CORRUPT`, `TARGET_NOT_MET`, `REBATE_BOOKED`, `REBATE_ZERO`.

## Endpoints (Milestone 10)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/invoices/{id}/eway-bill` · `/invoices/{id}/einvoice` | owner, accountant; counter: own shop |
| POST | `/invoices/{id}/eway-bill` `{distance_km, from_pincode, to_pincode, vehicle_no?}` | owner, counter (own shop) |
| POST | `/invoices/{id}/eway-bill/manual` `{number, vehicle_no?, valid_until?}` · `/eway-bill/vehicle` | owner, counter (own shop) |
| POST | `/invoices/{id}/eway-bill/cancel` `{reason}` · `/invoices/{id}/einvoice/cancel` | owner |
| POST | `/invoices/{id}/einvoice` `{from_pincode, to_pincode}` | owner, counter (own shop) |
| GET | `/eway-bills/pending` | owner, accountant, counter (own shop) |
| POST | `/eway-bills/batch` `{items:[{invoice_id, ...}]}` | owner, counter (own shop) |

The invoice PDF prints the live e-way bill number, and the IRN with its QR. Codes:
`EWAY_EXISTS`, `EWAY_NUMBER_USED`, `EWAY_CANCEL_WINDOW_CLOSED`, `EINVOICE_NOT_REQUIRED`,
`EINVOICE_EXISTS`, `EINVOICE_CANCEL_WINDOW_CLOSED`, `SELLER_GSTIN_MISSING`, `VEHICLE_INVALID`.
A provider failure is 502 (`GSP_TIMEOUT`, `GSP_DOWN`, `GSP_REFUSED`, `GSP_NOT_CONFIGURED`...).

## Endpoints (Milestone 9)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/vehicles` (`include_inactive`) | owner, accountant |
| POST/PATCH | `/vehicles` · `/vehicles/{id}` | owner |
| GET | `/trips` (`invoice_id`, `vehicle_id`) | owner, accountant |
| POST | `/trips` `{vehicle_id, location_id, invoice_id?, purchase_id?, from_place, to_place, freight_amount}` | owner |
| GET | `/drop-ship/open-purchases?item_id=` (quantities only, no cost) | owner, counter |
| POST | `/drop-ship/links` `{sales_line_id, purchase_line_id}` | owner |
| GET | `/reports/drop-ship` | owner |

Invoice lines accept `purchase_line_id` for direct lines. The owner's invoice adds
`drop_ship_purchase` per line and `freight` (profit is after freight). `POST /payments` answers
with `warnings` (cash above the daily limit to one person). New codes: `LINK_*`,
`DIRECT_LINK_INVALID`, `LINK_NEEDS_DIRECT`, `VEHICLE_EXISTS`, `VEHICLE_INACTIVE`,
`TRIP_ONE_DOCUMENT`, `OWN_VEHICLE_FREIGHT`.

## Endpoints (Milestone 8)

| Method | Path | Who |
| --- | --- | --- |
| POST | `/credit-notes` `{invoice_id, reason, lines:[{line_id, quantity}], approval_ids}` | owner, counter (own shop); after the return window: owner or a `late_return` approval |
| GET | `/credit-notes` (`invoice_id`, `party_id`) · `/credit-notes/{id}` · `/credit-notes/{id}/pdf` | owner, accountant; counter: own shop |
| POST | `/debit-notes` `{purchase_id, reason, lines:[{line_id, quantity}]}` | owner |
| GET | `/debit-notes` (`purchase_id`, `party_id`) · `/debit-notes/{id}` · `/debit-notes/{id}/pdf` | owner, accountant |

Invoice lines now carry `returned_qty` (base units taken back so far). `quantity` in a return is
in the unit of the bill line. New error codes: `RETURN_WINDOW_CLOSED`, `RETURN_TOO_MUCH`,
`RETURN_LINE_REPEATED`.

## Endpoints (Milestone 7)

| Method | Path | Who |
| --- | --- | --- |
| POST | `/auth/pin` | owner (sets their approval PIN; needs their password) |
| POST | `/approvals` `{pin, action, reason, party_id}` | owner, counter |
| POST | `/payments` (`direction` received or paid, `allocations`, `Idempotency-Key`) | received: owner, counter at own shop; paid: owner |
| GET | `/payments` | owner, accountant; counter: own shop's receipts only |
| GET | `/parties/{id}/open-bills?account=` | signed in; payable side not for counter |
| POST | `/invoices` and `/invoices/preview` now take `payments` and `approval_ids` | owner, counter |

## Endpoints (Milestone 6)

| Method | Path | Who |
| --- | --- | --- |
| POST | `/invoices/preview` | owner, counter (own shop): prices, tax, stock and problems; nothing saved |
| POST | `/invoices` (`Idempotency-Key`) | owner, counter (own shop) |
| GET | `/invoices` (`q`, `party_id`, `date_from`, `date_to`) · `/invoices/{id}` · `/invoices/{id}/pdf` | owner, accountant; counter: own shop. Cost and profit: owner only |

## Endpoints (Milestone 5)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/rates/market?on=` · `/rates/market/{item_id}/history` · `/rates/resolve?item_id=&party_id=&on=` | signed in; cost, margin and suggestion for the owner only |
| PUT | `/rates/market` (`{effective_date, rates:[{item_id, rate, unit}]}`) | owner |
| GET/POST/PATCH | `/customer-rates` | owner |
| GET/PUT | `/margins` | owner |

## Endpoints (Milestone 4)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/cost-components` · POST/PATCH (owner) | owner, counter read |
| POST | `/purchases/preview` | owner (landed cost, nothing saved) |
| POST/GET | `/purchases` · GET `/purchases/{id}` | enter: owner, counter (own shop, if allowed); read: all, counter's own shop only; money fields owner only |
| POST/GET | `/payments` (`Idempotency-Key` header) | create: owner; read: owner, accountant |
| POST/GET | `/transfers` · GET `/transfers/{id}` | owner, counter (out of own shop) |
| POST/GET | `/stock-counts` · GET `/{id}` · PUT `/{id}/lines` | owner, counter (own shop); rupee variance owner only |
| POST | `/stock-counts/{id}/post` | owner |

## Endpoints (Milestone 3)

| Method | Path | Who |
| --- | --- | --- |
| GET/POST | `/opening` · PATCH/DELETE `/opening/{id}` (drafts only) | owner |
| POST | `/opening/post` `{kinds: [...]}` | owner |
| GET | `/stock` (`location_id`, `q`, `include_zero`) | signed in; `avg_cost` and `value` for the owner only |
| GET | `/parties/{id}/statement?site_id=` | signed in; supplier payable side hidden from counter staff |
| GET | `/reports/dues?account=receivable\|payable` | receivable: all roles; payable: owner and accountant |

## Endpoints (Milestone 2)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/items` (`q`, `category`, `include_inactive`) · `/items/{id}` | signed in; owner gets `min_margin` |
| POST/PATCH | `/items`, `/items/{id}` | owner |
| GET | `/items/{id}/convert?quantity=&from_unit=&to_unit=` | signed in |
| GET | `/items/import/template` · POST `/items/import?dry_run=true` (multipart `file`) | owner |
| GET | `/parties` (`q`, `kind=customer\|supplier`) · `/parties/{id}` | signed in |
| POST/PATCH | `/parties`, `/parties/{id}` | owner, counter (credit fields: owner only) |
| POST | `/parties/{id}/sites` · PATCH `/sites/{id}` | owner, counter |

## Endpoints (Milestone 1)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/health`, `/health/ready` | anyone |
| POST | `/auth/login`, `/auth/refresh`, `/auth/logout` | anyone |
| GET | `/auth/me` · POST `/auth/change-password` | signed in |
| GET/POST | `/users` · GET/PATCH `/users/{id}` · POST `/users/{id}/reset-password` | owner |
| GET | `/locations` | signed in |
| POST/PATCH | `/locations`, `/locations/{id}` | owner |
| GET | `/settings` | signed in |
| PUT | `/settings` | owner |
| GET | `/audit-log` | owner |
