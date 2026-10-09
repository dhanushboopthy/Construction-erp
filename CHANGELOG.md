# Changelog

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
