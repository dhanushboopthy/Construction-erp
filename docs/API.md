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
