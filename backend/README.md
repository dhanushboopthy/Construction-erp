# Backend (FastAPI)

Layers, top to bottom. A layer may only call the ones below it.

| Folder | Holds | Rules |
| --- | --- | --- |
| `app/api/v1/` | HTTP routes, request/response schemas, role checks | Thin. No business maths. |
| `app/services/` | Use cases: load data, call domain rules, save, commit | One transaction per use case. |
| `app/domain/` | Pure business rules (GST, landed cost, pricing, credit, stock) | No DB, no HTTP, no clock. 100% unit-tested. |
| `app/models/` | SQLAlchemy tables | Every table has `tenant_id`. Money is `NUMERIC`. |
| `app/core/` | Config, DB session, security, errors, logging, middleware | |

## Commands (from `backend/`)

```bash
uv sync                                   # install
uv run uvicorn app.main:app --reload      # run (needs DATABASE_URL)
uv run alembic upgrade head               # migrate
uv run alembic revision --autogenerate -m "add item master"   # new migration
uv run alembic check                      # fails if models and migrations differ
uv run python -m app.scripts.seed         # seed shops and users
uv run pytest tests/unit                  # fast tests, no database
uv run pytest                             # all tests (needs TEST_DATABASE_URL)
uv run ruff check . && uv run ruff format --check . && uv run mypy app
```

Development logins after seeding: `owner / owner-pass-123`, `counter1 / counter-pass-123`,
`counter2 / counter-pass-123`, `accounts / accounts-pass-123`. Production seeding generates
random passwords unless `SEED_<USERNAME>_PASSWORD` is set.
