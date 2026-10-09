# Roadmap

Build in vertical slices: each milestone ends with migration, API, tests, a working screen and a
short demo to the owner. Don't start a milestone until the previous one passes its tests.
Milestones 0–6 are the minimum for a shop that can bill and track stock; cut from the bottom
if time runs short. In Claude Code: `/milestone <n>`.

| # | Milestone | What gets built | Acceptance test | Status |
| --- | --- | --- | --- | --- |
| 0 | Foundation | Repo, Docker Compose, Postgres, FastAPI, React + TypeScript, Alembic, CI, seed, docs | `make up` starts the stack; CI green | **Done** (frontend installed and built, `package-lock.json` committed, CI uses `npm ci`) |
| 1 | Auth and setup | Users, roles, locations, settings, audit log, numbering, login screen | Counter user gets 403 on owner routes; writes are audited | **Done** (Settings, Users and Locations screens under `/settings`; role test for every route) |
| 2 | Items and parties | Item master (brand, HSN, GST, units, theoretical weight), parties, sites, Excel import | 50 items import from a sheet; bag ↔ ton conversions correct | **Done** (`feat/m2-items-parties`) |
| 3 | Opening balances | Wizard for opening stock, customer and supplier dues | Opening entries appear in ledgers and reports | **Done** (`feat/m3-opening-balances`; ADR 0006) |
| 4 | Purchase and stock | Purchase entry, cost components, supplier advance, stock ledger, transfers | Sample purchase gives the hand-calculated landed and average cost | **Done** (`feat/m4-purchase-stock`; ADR 0007) |
| 5 | Rates | Daily market rate screen, customer rates, margins (owner only) | Price resolves in order; staff API never returns cost | **Done** (`feat/m5-rates`) |
| 6 | Sales invoice | Billing screen, GST maths, sites, numbering, A4 PDF, B2C, idempotency | Totals match a manual calculation; numbers gapless under concurrent saves | |
| 7 | Credit and payments | Credit checks, owner PIN approvals, payments, allocation, ledgers, statements | Over-limit and overdue blocked; statement per site balances | |
| 8 | Returns and notes | 2-day returns, credit notes, purchase returns, debit notes | Return after 2 days needs owner approval | |
| 9 | Drop-ship and transport | Direct fulfilment, purchase link, vehicles, trips, freight | Drop-ship writes no stock rows and shows correct profit | |
| 10 | E-way bill (and IRN) | GSP integration, Part B update, cancel, manual fallback | 50 bills in a sandbox batch succeed | |
| 11 | Weight and schemes | Weight fail-check, attachments, supplier schemes | Variance above threshold is flagged and needs a note | |
| 12 | Closing and reports | Daily closing PDF per shop, day lock, cloud save, Today figures, dues, segment chart | One PDF per shop per day lands in storage | |
| 13 | GST exports | GSTR-1, 3B data, 2B matching, accountant views | Accountant opens the export without errors | |
| 14 | Hardening and go-live | Backups, restore drill, monitoring, training, parallel run on paper | Restore tested; owner signs off after a week in parallel | |

## Already in place (Milestones 0–1)

- Backend: FastAPI app factory, settings with production safety checks, JSON logs, request ids,
  security headers, error contract, SQLAlchemy 2 models, initial Alembic migration, audit
  listener (before/after diffs with redaction), gapless numbering service, auth with rotating
  refresh sessions and lockout, users/locations/settings/audit-log endpoints, seed script.
- Domain rules with unit tests: money, financial year and numbering, GST, units, landed cost,
  weighted-average stock, pricing, credit, weight check, compliance thresholds.
- Frontend: React + TypeScript + Vite, auth provider with in-memory token and silent refresh,
  keyboard-first app shell (Alt+1–9, phone nav strip), login and Today screens, owner-only
  Settings (shop details, users, shops and godown), role guard on every module route, API types
  generated from OpenAPI, placeholders for the modules still to build.
- Tests: `app/domain` at 100% coverage (enforced in CI); every API route has a role test.
- Tooling: Docker Compose (dev and simple production with nightly backups), Makefile, CI,
  pre-commit, Dependabot, Claude Code settings, `/milestone` command, two UI skills.
