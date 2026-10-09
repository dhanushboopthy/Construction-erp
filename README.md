# Construction ERP

Purchase, stock, GST billing and credit control for a construction-materials supplier
(TMT bars, pipes, cement, binding wire, angles and channels). Built first for one business with
two shops and a godown; designed to become a multi-tenant SaaS.

**Stack:** FastAPI · PostgreSQL · React + TypeScript · Docker Compose

## Quick start

```bash
make up      # web http://localhost:5173 · API http://localhost:8000/api/docs
make seed    # sign in as owner / owner-pass-123 (development only)
make test
```

Requirements: Docker with Compose. To run without Docker, see
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## What's here

| Path | Contents |
| --- | --- |
| `backend/` | FastAPI app: auth and roles, items and parties, purchase and landed cost, stock, GST sales invoices, credit and payments, returns and notes, drop-ship and transport, e-way bill and IRN (behind a GSP interface), weight checks and supplier schemes, daily closing, GST returns, integrity checks. Business rules in `domain/` with tests |
| `frontend/` | React + TypeScript app: keyboard-first screens for every module above |
| `docs/` | [Spec](docs/SPEC.md) · [Roadmap](docs/ROADMAP.md) · [Gap analysis](docs/GAP_ANALYSIS.md) · [Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [Design](docs/DESIGN.md) · [Deployment](docs/DEPLOYMENT.md) · [Runbook](docs/RUNBOOK.md) · [Go-live plan](docs/GO_LIVE.md) · [Glossary](docs/GLOSSARY.md) · [Decisions](docs/adr/) |
| `.claude/` | Claude Code settings, `/milestone` command, `frontend-design` and `ui-ux-pro-max` skills |
| `scripts/` | Backup loop, restore, restore drill, off-site copy, test database init |

## Status

All fifteen milestones (0 to 14) are built. What remains is on the real machine and with real
people, listed in [docs/GO_LIVE.md](docs/GO_LIVE.md): choose and test the e-way bill provider
(sandbox keys), choose cloud storage, have the accountant confirm the open GST decisions and check
a real month's GSTR-1, run the restore drill and the off-site copy, train staff, and run a week in
parallel with the paper book. See [docs/ROADMAP.md](docs/ROADMAP.md) for each milestone.

## Working with Claude Code

Open the repo in Claude Code and run `/milestone 2` (or any number). Claude reads
`CLAUDE.md`, the spec and the roadmap, builds that milestone test-first, and stops to report.

## Production

Single machine with Docker Compose, HTTPS in front, nightly backups copied off the machine.
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
