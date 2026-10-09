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
| `backend/` | FastAPI app: auth and roles, settings, locations, audit log, document numbering, business rules with tests |
| `frontend/` | React + TypeScript app: sign-in, keyboard-first shell, Today screen, module placeholders |
| `docs/` | [Spec](docs/SPEC.md) · [Roadmap](docs/ROADMAP.md) · [Gap analysis](docs/GAP_ANALYSIS.md) · [Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [Design](docs/DESIGN.md) · [Deployment](docs/DEPLOYMENT.md) · [Glossary](docs/GLOSSARY.md) · [Decisions](docs/adr/) |
| `.claude/` | Claude Code settings, `/milestone` command, `frontend-design` and `ui-ux-pro-max` skills |
| `scripts/` | Backup loop, restore, test database init |

## Status

Milestones 0–1 (foundation, auth and setup API) are in place. Next: Settings screens, then
Milestone 2 (items and parties). See [docs/ROADMAP.md](docs/ROADMAP.md).

## Working with Claude Code

Open the repo in Claude Code and run `/milestone 2` (or any number). Claude reads
`CLAUDE.md`, the spec and the roadmap, builds that milestone test-first, and stops to report.

## Production

Single machine with Docker Compose, HTTPS in front, nightly backups copied off the machine.
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
