# Contributing

1. Pick the next milestone in [docs/ROADMAP.md](docs/ROADMAP.md); branch `feat/m<n>-<topic>`.
2. Read the rules it touches in [docs/SPEC.md](docs/SPEC.md). Unclear or marked Owner/Accountant
   in [docs/GAP_ANALYSIS.md](docs/GAP_ANALYSIS.md)? Ask before building.
3. Tests first for business rules (`backend/tests/unit`), then code.
4. `make lint && make test` must pass. CI runs the same checks plus `alembic check` and image builds.
5. Update the roadmap status and spec in the same pull request; add an ADR for any new decision.
6. Conventional commits: `feat(m4): …`, `fix: …`, `docs: …`, `test: …`, `chore: …`.

Setup and commands: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Pre-commit hooks:
`pip install pre-commit && pre-commit install`.
