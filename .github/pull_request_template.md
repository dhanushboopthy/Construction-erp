## What and why

<!-- Which milestone (docs/ROADMAP.md) and which business rules (B1-B18, G1-G24 in docs/SPEC.md)? -->

## Checklist

- [ ] Tests added for new business rules (domain functions have unit tests)
- [ ] `make lint` and `make test` pass
- [ ] Migration added and reviewed (`alembic check` passes)
- [ ] Cost, margin and profit are hidden from non-owner roles in the API
- [ ] Money and quantities use Decimal / NUMERIC, never float
- [ ] Docs updated (SPEC, ROADMAP status, ADR if a decision changed)
