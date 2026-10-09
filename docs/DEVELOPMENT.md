# Development

## With Docker (recommended)

```bash
make up        # db :5432, API :8000, web :5173 (creates .env from .env.example)
make seed      # shops S1, S2, godown G1, users owner / counter1 / counter2 / accounts
open http://localhost:5173      # owner / owner-pass-123
make test      # backend (unit + integration) and frontend tests
make lint      # ruff, mypy, alembic check, eslint, tsc, prettier
make help      # everything else
```

## Without Docker

Needs Python 3.13 + [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16+.

```bash
# backend
cd backend
uv sync
export DATABASE_URL=postgresql+psycopg://erp:erp@localhost:5432/erp
export TEST_DATABASE_URL=postgresql+psycopg://erp:erp@localhost:5432/erp_test
uv run alembic upgrade head && uv run python -m app.scripts.seed
uv run uvicorn app.main:app --reload
uv run pytest

# frontend (another terminal)
cd frontend
npm install
npm run dev     # proxies /api to :8000
```

## Workflow

- One branch and pull request per milestone (`feat/m4-purchase`). CI must pass.
- Conventional commits: `feat(m4): landed cost on purchase entry`, `fix:`, `docs:`, `test:`.
- Schema changes only through Alembic: change models → `make migration m="..."` → read the
  generated file → `make migrate`. `alembic check` in CI fails if they drift.
- New business rule: write the test in `backend/tests/unit/` first, with numbers worked out by
  hand, then the function in `backend/app/domain/`.
- Money: `Decimal` and `NUMERIC` only. Passing a float to `domain.money` raises.
- Keep `docs/SPEC.md` and `docs/ROADMAP.md` current in the same pull request.

## Tests

| Kind | Where | Needs |
| --- | --- | --- |
| Domain unit tests | `backend/tests/unit/` | nothing |
| API integration tests | `backend/tests/integration/` | PostgreSQL (`TEST_DATABASE_URL`); schema built by migrations; each test rolled back |
| Frontend | `frontend/src/**/*.test.tsx` | nothing (jsdom) |

Use the owner's real recent bills as fixtures for landed cost and invoice totals.
