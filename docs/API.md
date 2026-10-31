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

0. The address picks the company (ADR 0011): `acme.<BASE_DOMAIN>` is the company `acme`.
   `GET /tenant` → `{slug, name, status}` for the sign-in page. An unknown address answers 404
   `TENANT_NOT_FOUND`. A suspended or closed company answers 403 `TENANT_SUSPENDED` /
   `TENANT_CANCELLED` on every route.
1. `POST /auth/login {username, password}` → `{access_token, expires_in, user}` + refresh cookie.
   The username is looked up in the address's company only.
2. Send `Authorization: Bearer <access_token>`.
3. On 401, `POST /auth/refresh` (cookie only) → new token + new cookie; retry once.
4. `POST /auth/logout` revokes the session and clears the cookie.

## Role-shaped responses

Endpoints that return cost, margin or profit use separate response models for owners and
staff (for example `ItemOwnerOut` and `ItemOut`). Choose the model with `principal.sees_cost`;
never rely on the UI to hide fields. Test each such endpoint as a counter user.

## Endpoints (Milestone 16: Duolink admin, ADR 0012)

Only at `admin.<BASE_DOMAIN>` (404 elsewhere), under `/admin`, with a Duolink admin's token (type
`platform`; a company user's token answers 401). Answers carry counts and statuses, never amounts.

| Method | Path | What |
| --- | --- | --- |
| POST | `/admin/auth/login {email, password}`, `/admin/auth/refresh`, `/admin/auth/logout` | Admin sign-in; cookie `duolink_admin_refresh` on `/api/v1/admin/auth` |
| GET | `/admin/auth/me` · POST `/admin/auth/change-password` | The signed-in admin |
| GET | `/admin/overview` | Companies by status, new this month, active users, open sessions, sign-ins and wrong passwords (24 h, 7 d), trials ending in 7 days |
| GET | `/admin/tenants?q&status&plan` | Companies with users and shops against their limits, bills in 30 days, last sign-in |
| POST | `/admin/tenants {name, slug, plan, state_code, owner_username, owner_full_name, owner_password}` | New company with starter data and its first owner. 409 `SLUG_TAKEN` / `SLUG_INVALID` |
| GET / PATCH | `/admin/tenants/{id}` `{name?, plan?, max_users?, max_locations?, trial_ends_at?}` | Detail; null limits return to the plan's |
| POST | `/admin/tenants/{id}/suspend {reason}`, `/admin/tenants/{id}/reactivate` | Suspend ends every session and blocks sign-in |
| GET | `/admin/users?tenant_id&q&role&state=active\|inactive\|locked` | Users of every company |
| POST | `/admin/users/{id}/deactivate`, `/activate`, `/unlock`, `/sign-out` | Support actions (409 `LAST_OWNER`, `PLAN_USER_LIMIT`) |
| POST | `/admin/users/{id}/reset-password` | `{temporary_password}`, shown once |
| GET | `/admin/activity?tenant_id&action` · `/admin/audit?tenant_id&action` | Sign-ins at companies · what admins did |

## Endpoints (Milestone 17: Duolink staff and roles, ADR 0013)

Same address and token as Milestone 16. **Support** can read (`GET`) everything in `/admin`; every
other method below needs a **Super Admin** and answers 403 `PERMISSION_DENIED` to Support. That
includes the Milestone 16 writes (company create, update, suspend, reactivate; user deactivate,
activate, unlock, reset password, sign out). The sign-in routes need no role.

| Method | Path | Role | What |
| --- | --- | --- | --- |
| GET | `/admin/staff` | any admin | Staff with role, active, locked, must-change-password, open sessions |
| POST | `/admin/staff {full_name, email, mobile?, password, role = support}` | Super Admin | New member with a temporary password. 409 `EMAIL_TAKEN`; 422 on a bad email, mobile or short password |
| PATCH | `/admin/staff/{id} {full_name?, mobile?, role?, is_active?, reason?}` | Super Admin | Send only what changes; `mobile: null` clears it. 409 `LAST_SUPER_ADMIN`, `SELF_CHANGE`; 404 |
| POST | `/admin/staff/{id}/reset-password` | Super Admin | `{temporary_password}`, shown once; their sessions end and they must change it |
| POST | `/admin/staff/{id}/unlock`, `/admin/staff/{id}/sign-out` | Super Admin | Clear a lockout · end every session |
| GET | `/admin/auth/me` | any admin, even before the change | Now also `mobile`, `role`, `must_change_password` |
| POST | `/admin/auth/change-password {current_password, new_password}` | any admin, even before the change | 204; signs the admin out everywhere. 401 wrong current password; 409 `PASSWORD_UNCHANGED` |
| GET | `/admin/audit` | any admin | Rows now also carry `target_admin_email` |

Until a member has changed a temporary password, every other admin call answers 403
`PASSWORD_CHANGE_REQUIRED` (only `/auth/me`, `/auth/change-password` and `/auth/logout` work).

## Endpoints (Milestone 18: company profile and onboarding)

Same address and token as Milestone 16. Writes need a **Super Admin**; Support reads (403
`PERMISSION_DENIED` otherwise).

| Method | Path | Role | What |
| --- | --- | --- | --- |
| GET | `/admin/tenants?q&status&plan&trial&expiring&sort&order&limit&offset` | any admin | `q` matches name, code, owner name or email, GSTIN. `trial` = `running\|ending\|ended\|none`; `expiring=true` = trial ends within 30 days; `sort` = `name\|created\|last_activity\|users`; `order` = `asc\|desc`. Rows carry `owner_name`, `city`, `state_code`, `last_activity_at` |
| POST | `/admin/tenants {name, slug, plan, trial_days?, start_active?, state_code, city?, legal_name?, registration_no?, shop_name = "Shop 1", shop_code = "S1", owner_username, owner_full_name, owner_email?, owner_mobile?, owner_password, require_owner_password_change = false}` | Super Admin | The whole onboarding form in one transaction. 201 with the company and `sign_in_url`. 409 `SLUG_TAKEN`, `SLUG_INVALID`, `TRIAL_CONFLICT`, `TRIAL_ON_PAID_PLAN`, `TRIAL_DAYS`; 422 for a bad GSTIN (check digit, or first digits not the state), shop code, email or mobile |
| GET / PATCH | `/admin/tenants/{id}` `{name?, plan?, max_users?, max_locations?, trial_ends_at?, owner_name?, owner_email?, owner_mobile?, city?, state_code?, notes?}` | read: any · write: Super Admin | Detail now also has the contact record, internal `notes`, `cancelled_at`, `cancelled_reason`. A blank contact field is cleared |
| GET | `/admin/tenants/{id}/usage` | any admin | `{users, shops, bills_7d, bills_30d, bills_90d, purchases_30d, attachments, attachment_bytes}`; counts only |
| GET | `/admin/tenants/{id}/seller-details` | any admin | `{legal_name, registration_no, pan, cin, address, state_code}`; `registration_no` is the GSTIN |
| PATCH | `/admin/tenants/{id}/seller-details {legal_name?, registration_no?, pan?, cin?, address?, state_code?, reason}` | Super Admin | Send only what changes; null clears `registration_no`, `pan`, `cin`. `reason` required. Validated as the company's Settings form (422 `VALIDATION_ERROR`, `field` names the bad one). Written to the company's audit log as `Duolink: <admin>` and to ours with old and new values |
| POST / DELETE | `/admin/tenants/{id}/logo` (multipart `file`) | Super Admin | As the owner's own upload: square PNG or plain SVG, up to 200 KB. 4xx `LOGO_NOT_SQUARE`, `LOGO_SVG_UNSAFE`, `FILE_TYPE_NOT_ALLOWED`, `FILE_TOO_LARGE` |
| POST | `/admin/tenants/{id}/cancel {reason}` | Super Admin | Close the company: sessions end, sign-in answers 403 `TENANT_CANCELLED`, data kept. 409 `ALREADY_CANCELLED` |
| POST | `/admin/tenants/{id}/reactivate {reason?}` | Super Admin | Undo a suspension, or reopen a cancelled company (reason required: 409 `REASON_REQUIRED`). 409 `NOT_SUSPENDED` |
| POST | `/admin/tenants/{id}/suspend {reason}` | Super Admin | As before; 409 `ALREADY_SUSPENDED`, or `ALREADY_CANCELLED` for a closed company |

Company side: `GET /auth/me` and the sign-in answer now carry `must_change_password`. While it is
true, every call except `/auth/me`, `/auth/change-password` and `/auth/logout` answers 403
`PASSWORD_CHANGE_REQUIRED`; `POST /auth/change-password` answers 409 `PASSWORD_UNCHANGED` for the
same password. `PUT /settings` and `GET /settings` carry optional `pan` and `cin` (422 if invalid,
or if the PAN is not characters 3 to 12 of the GSTIN).

Company side: `GET /tenant/plan` (owner) → `{plan, status, trial_ends_at, users, max_users,
locations, max_locations}`. Adding a user or a shop beyond the plan answers 409
`PLAN_USER_LIMIT` / `PLAN_LOCATION_LIMIT`.

## Endpoints (FM10: orders, receipts, match report, lost sales)

| Method | Path | Who |
| --- | --- | --- |
| POST | `/purchase-orders` (`supplier_id`, `location_id`, `order_date`, `expected_date`, `lines[item_id, unit, quantity, rate]`) | owner only |
| GET | `/purchase-orders?supplier_id=&open_only=` | owner (rates, value); counter (own shop) and accountant (quantities only) |
| GET | `/purchase-orders/{id}` | same |
| POST | `/purchase-orders/{id}/receipts` (`receipt_date`, `note`, `lines[order_line_id, quantity]`) | owner, counter (own shop, today) |
| GET | `/reports/match-exceptions?date_from=&date_to=&all_lines=` (30 days by default) | owner only |
| POST | `/lost-sales` (`location_id`, `item_id`, `quantity`, `unit`, `note`, `entry_date`) | owner, counter (own shop, today) |
| GET | `/lost-sales?date_from=&date_to=` (7 days by default) | owner (with `value`), counter (own shop, quantities) |
| GET | `/reports/fill-rate?period=2026-10` | owner (with `lost_value`), counter (own shop, quantities) |

`POST /purchases` gains `purchase_order_id` and `approval_ids` (an approval with action
`po_mismatch`), and each line gains optional `mfg_week` and `mfg_year` (cement only). The purchase
answer gains `purchase_order_id`, `purchase_order_number`, `match_approved` and per-line lots.
Invoice lines gain `lots` (label, week, year, quantity taken). Errors: `MATCH_EXCEPTION` (409,
`requires_owner_approval`; the message names quantities and rates in words, never a rupee value),
`APPROVAL_INVALID`, `ORDER_SUPPLIER_MISMATCH`, `ORDER_PLACE_MISMATCH`, `LOT_ONLY_CEMENT`,
`BAD_LOT`, `LINE_REPEATED`, `BAD_DATES`, `BACKDATE_NEEDS_OWNER`, `FUTURE_DATE`, `UNKNOWN_UNIT`,
`UNIT_NOT_WHOLE`, `FUTURE_PERIOD`. Settings gain `po_qty_tolerance_pct` and
`po_rate_tolerance_pct`. The accountant gets 403 on receipts, lost sales, fill rate and the match
report.

## Endpoints (FM8: profit cuts, ITC at risk)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/reports/profitability?by=brand\|shop\|user\|item\|customer&period=2026-10&location_id=` | owner only |
| GET | `/gst/itc-at-risk?period=2026-10` | owner, accountant |

Counter staff get 403 on both; the accountant gets 403 on the profit cuts. Errors: `BAD_PERIOD`,
`FUTURE_PERIOD`, 422 for an unknown `by`. Profit cuts: each row has `net_sales`, `cogs`, `freight`,
`gross_profit`, `margin_pct`, `share_pct`, `tons` (items whose base unit is kg), `units` and
`unit_label` (everything else), `profit_per_ton`, `profit_per_unit` and `margin_per_base_unit`
(only when every line is in one base unit); a figure with nothing to divide by is `null`, never 0.
The report foot has `gross_profit_before_loss` (the rows added up), `stock_lost` and `gross_profit`
(equal to `/reports/pnl` for the same month and `location_id`), `profit_per_ton`, and
`contribution_per_ton`, which is `null` when any sale was by the bag or piece. ITC at risk:
`has_2b: false` with a `note` and `null` figures when no GSTR-2B is imported for the month;
otherwise `missing` (in books, not in 2B), `mismatches` (supplier reported less), `at_risk_total`,
`no_gstin_itc`, `payable_estimate`, `payable_if_unclaimed`, `payable_to_date` and `due_date`.

## Endpoints (FM7: period lock, bank statements, exceptions)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/period-lock` | owner, accountant |
| PUT | `/period-lock` (`locked_through` or null, `reason`) | owner only |
| GET | `/period-lock/checklist?period=2026-10` | owner, accountant |
| GET | `/bank/accounts` | owner, accountant |
| POST | `/bank/accounts` (`name`, `account_no_last4`) | owner only |
| PATCH | `/bank/accounts/{id}` (`name`, `is_active`) | owner only |
| GET | `/bank/statements` | owner, accountant |
| POST | `/bank/statements` (multipart: `bank_account_id`, `file`) | owner, accountant |
| GET | `/bank/reconciliation?date_from=&date_to=&bank_account_id=` (30 days by default) | owner, accountant |
| GET | `/reports/exceptions?date_from=&date_to=` (30 days by default) | owner only |

Counter staff get 403 on all of them; the accountant gets 403 on the exception report and on every
write except the statement upload. Errors: `PERIOD_LOCKED` (409, from any route that dates a
document), `LOCK_IN_FUTURE`, `LOCK_UNCHANGED`, `STATEMENT_IMPORTED` (the same file twice),
`STATEMENT_UNREADABLE` (the message names the first bad lines; nothing is imported),
`STATEMENT_EMPTY`, `ACCOUNT_INACTIVE`, `DUPLICATE_NAME`, `BAD_RANGE`, `RANGE_TOO_LONG`. Settings
gain `bank_match_days`, `exception_round_amount`, `exception_count_days`,
`exception_returns_count`, `exception_returns_days`, `exception_cash_near_pct` and
`exception_shortage_count` (zero switches a rule off); `locked_through` is read-only there.
The audit log gains the entity `period_lock` (action `override`; changes: `from`, `to`, `reason`,
`reopens`).

## Endpoints (FM6: inventory analytics, stock value, shortages)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/inventory/analytics` | owner |
| GET | `/inventory/fifo-age` | owner |
| GET | `/inventory/nrv` | owner, accountant |
| GET | `/inventory/writedowns?date_from=&date_to=` | owner, accountant |
| POST | `/inventory/writedowns` (`location_id`, `item_ids`, `note`) | owner only |
| GET | `/inventory/shrinkage?date_from=&date_to=` (90 days by default) | owner, accountant |

Counter staff get 403 on all of them. Errors: `NO_MARKET_RATE`, `NOTHING_TO_WRITE_DOWN`,
`WRITEDOWN_DISABLED`, `DUPLICATE_ITEM` (409), `BAD_RANGE`. Analytics fields are `null` with
`enough_data: false` (fewer than 30 days of history). Items gain `lead_time_days` and
`safety_days`, parties `lead_time_days` (all optional); settings gain `default_lead_time_days`,
`default_safety_days`, `fsn_fast_min_days`, `nrv_selling_cost_pct`, `nrv_writedown_enabled`. The
P&L gains `write_downs`, taken off `net_profit`.

## Endpoints (FM5: working capital, receivables, write-offs)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/reports/working-capital?period=2026-09&trend=true` | owner |
| GET | `/reports/receivables` | owner (with `provision`, `provision_pct`), accountant (without); counter 403 |
| GET | `/write-offs?party_id=&date_from=&date_to=` | owner, accountant |
| POST | `/write-offs` (`location_id`, `party_id`, `amount`, `reason`) | owner only |

Errors: `BAD_PERIOD`, `FUTURE_PERIOD`, `WRITEOFF_TOO_MUCH` (409, more than the customer owes),
`NOT_A_CUSTOMER` (409). Working capital day counts are `null` when there is nothing to divide by
and `enough_data` is false with fewer than 7 days of bills ("Not enough data yet"). The P&L gains
`bad_debts`, taken off `net_profit`. Settings gain `provision_pct_current`, `provision_pct_1_15`,
`provision_pct_16_30`, `provision_pct_31_60`, `provision_pct_over_60`.

## Endpoints (FM4: Tally export)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/tally/ledgers` | owner, accountant |
| PUT | `/tally/ledgers` (`company`, `names{purpose: name}`) | owner, accountant |
| GET | `/tally/preview?date_from=&date_to=` | owner, accountant |
| GET | `/tally/export?date_from=&date_to=&masters=true` (XML download) | owner, accountant (403 for counter) |

The preview returns voucher counts and debit totals per type and the checks (`receivable`,
`payable`, and for whole months `gstr1_taxable`, `gstr1_cgst`, `gstr1_sgst`, `gstr1_igst`,
`itc_cgst`, `itc_sgst`, `itc_igst`), each with `vouchers`, `report` and `ok`. Errors: `BAD_RANGE`,
`RANGE_TOO_LONG`, `EXPORT_MISMATCH` (a check failed; nothing is exported), `UNKNOWN_LEDGER`,
`DUPLICATE_LEDGER_NAME`.

## Endpoints (FM3: labelled rate overrides)

| Method | Path | Who |
| --- | --- | --- |
| POST | `/invoices` and `/invoices/preview`: line field `rate_override` (price per `unit`) now needs `rate_override_reason` | owner; counter only with a `discount` approval |
| GET | `/reports/rate-overrides?period=2026-10&location_id=` | owner (403 for counter and accountant) |

The saved line returns `rate_source: "override"` and `rate_override_reason`. Errors:
`OVERRIDE_REASON` (409, no reason), `DISCOUNT_NEEDS_OWNER` (409, counter without approval),
`BAD_PERIOD`, `FUTURE_PERIOD`. The report returns `lines`, `unpriced`, `cut`, `raised`, `net`,
`discounts`, `leakage`, `realisation_pct` (null with no hand-priced bills), `by_user` and `rows`.

## Endpoints (FM2: stock adjustments, ITC to reverse)

| Method | Path | Who |
| --- | --- | --- |
| GET | `/stock/dashboard`: items in stock by place and category, out of stock, to reorder | all roles; stock value, dead stock and values per place and category only for the owner |
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
| GET | `/cash-book?location_id=&date_from=&date_to=` (today by default) or `?all_time=true`; returns totals and `months` | owner, accountant; counter: own shop |
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

Every other route needs a sign-in; the only open ones are `/health`, `/health/ready`, `/tenant`,
`/auth/login`, `/auth/refresh` and `/auth/logout`, and at the admin address `/admin/auth/login`,
`/admin/auth/refresh` and `/admin/auth/logout`. All `/api` answers are `Cache-Control: no-store`.
A token is good only at its own company's address.

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
| POST | `/invoices/{id}/cancel` `{reason}`: a full credit note with `cancels_invoice`; the bill shows `cancelled_by` | owner |
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
| POST | `/quotes/preview` · `/quotes` `{kind: quotation\|proforma, location_id, party_id, site_id?, valid_until?, remark?, lines, approval_ids}` | owner, counter (own shop) |
| GET | `/quotes` (`kind`, `q`) · `/quotes/{id}` · `/quotes/{id}/pdf` | owner, accountant; counter: own shop |
| POST | `/invoices` with `quote_id` bills that quotation once | owner, counter (own shop) |

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
| GET | `/tenant` | open, no sign-in: the business name (trade name, else legal name), tagline and `logo_url` (null without a logo), for the sign-in page and the app shell; nothing else from the settings is ever added |
| GET | `/tenant/logo` | open, no sign-in: the logo image; 404 without one. Served `nosniff` with `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox` |
| PUT | `/tenant/logo` | owner: multipart `file`, a square PNG (32–2048 px) or plain SVG, up to 200 KB (413 over; 400 for another type or an unsafe SVG; 409 for a file that is empty, not square or the wrong size). Returns the tenant |
| DELETE | `/tenant/logo` | owner: back to the initials tile. Returns the tenant |
| GET | `/audit-log` | owner |
