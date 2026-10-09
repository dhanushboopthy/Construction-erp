# Architecture

A modular monolith: one FastAPI backend and one PostgreSQL database behind nginx, serving a
React + TypeScript single-page app. Runs on one machine with Docker Compose (ADR 0001).

```text
 Browsers (owner, counter staff, accountant)
        │ HTTPS
        ▼
 ┌───────────────────── one machine, Docker Compose ─────────────────────┐
 │  web: nginx ── serves React build, proxies /api ──► backend: FastAPI  │
 │                                                       │               │
 │                                                       ▼               │
 │                          backup: nightly pg_dump ◄── db: PostgreSQL   │
 └───────────────────────────────────────────────────────────────────────┘
        backend ──► GSP API (e-way bill, IRN)      backend ──► files volume or S3 bucket (PDFs, slips)
```

## Backend layers

```text
api/v1/      HTTP: validate input, check role, call a service, shape the response
   │
services/    use cases: load rows, call domain rules, write rows, commit (one transaction)
   │
domain/      pure business rules: GST, landed cost, pricing, credit, stock, numbering format
models/      SQLAlchemy tables          core/   config, db, security, errors, logging
```

Rules: a layer calls only layers below it. `domain/` never imports SQLAlchemy, FastAPI or the
clock (pass `today` in). Anything that touches money is in `domain/` and unit-tested.

## Key mechanisms

| Concern | How | Where |
| --- | --- | --- |
| Auth | Argon2 passwords; 30-min JWT access token in memory; 12-h refresh token in an httpOnly SameSite=Strict cookie, stored hashed, rotated on use, reuse revokes all sessions; lockout after 5 failures | `services/auth.py`, `api/v1/auth.py` |
| Permissions | `Principal` from the token + fresh DB read; `OwnerOnly` etc. dependencies; `Principal.sees_cost` for owner-only fields; `can_access_location` for counter staff | `api/deps.py` |
| Audit | SQLAlchemy `after_flush` listener writes insert/update/delete diffs for `Audited` models in the same transaction; secrets redacted; actor from `Session.info` | `services/audit.py` |
| Numbering | Atomic upsert on `document_sequence` inside the document's transaction: gapless, no duplicates | `services/numbering.py` |
| Money | `Decimal` end to end; floats rejected; `NUMERIC` columns; sent as strings in JSON | `domain/money.py` |
| Errors | One JSON shape `{code, message, field, request_id}`; business blocks are 409 | `core/errors.py` |
| Observability | Request id per request (header `X-Request-ID`), access log with user and duration, JSON logs in production, `/api/v1/health` and `/health/ready` | `core/middleware.py`, `core/logging.py` |
| Tenancy | `tenant_id` on every table, `TENANT_ID = 1` constant for now | `core/tenancy.py`, ADR 0004 |

## Frontend

React 19 + TypeScript (strict) + Vite. React Router for pages, TanStack Query for server state,
CSS Modules with design tokens (`src/styles/tokens.css`, see DESIGN.md). The API client keeps
the access token in memory and refreshes once on 401. Navigation and role visibility come from
`src/modules.ts`; Alt+1–9 switches modules. API types are generated from the backend's
OpenAPI spec into `src/api/schema.d.ts` (`make gen-api`, or `npm run gen:api` with the API on
:8000); `src/api/types.ts` only gives them short names. Regenerate after every API change.

## Decisions

See [adr/](adr/). Change a decision by adding a new ADR that supersedes the old one.

## Reliability (Milestone 14)

| Concern | How | Where |
| --- | --- | --- |
| Issued documents | Database triggers refuse DELETE on issued documents and UPDATE of their figures; ledgers are append-only (ADR 0003, 0010) | migrations 0003 and 0014 |
| Proof the books add up | Read-only integrity check: version, guards, number gaps, totals, accounts against documents, stock replay, stored files | `services/verify.py`, `python -m app.scripts.verify`, Settings, System |
| Backups | Nightly dump (read back before it is kept) and files archive; off-site copy; monthly restore drill into a scratch copy | `scripts/backup-loop.sh`, `offsite-sync.sh`, `restore-drill.sh`, `restore.sh` |
| Files | `Storage` interface: a folder (volume) or an S3-compatible bucket; keys are generated, content type is read from the bytes, checksum checked on read | `services/storage.py`, `services/attachments.py` |
| Outside services | GSP behind `GspClient`: pretend (never in production) or HTTP adapter; the call happens before anything is saved, so a failure leaves nothing behind | `services/gsp/` |
| Day lock | A closed shop-day refuses new documents until the owner reopens it (audited) | `services/closing.py` |
| Authentication on every route | A test walks the OpenAPI description and fails if any route answers without a sign-in | `tests/integration/test_security.py` |
