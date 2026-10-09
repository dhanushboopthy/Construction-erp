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
