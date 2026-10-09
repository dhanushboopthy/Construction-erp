# Changelog

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
