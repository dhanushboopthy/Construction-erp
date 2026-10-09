---
description: Build one milestone from docs/ROADMAP.md, test-first, then stop and report
argument-hint: <milestone number, e.g. 2>
---

Build Milestone $ARGUMENTS only.

1. Read CLAUDE.md, docs/ROADMAP.md (Milestone $ARGUMENTS and its acceptance test), and the
   sections of docs/SPEC.md it cites. Check docs/GAP_ANALYSIS.md for open questions that
   touch this milestone; if one blocks you, ask instead of guessing.
2. Write unit tests first for any new business rule in `backend/app/domain/`, using the
   worked numbers in the spec. Then implement.
3. Add models, an Alembic migration (`alembic revision --autogenerate`, then review it),
   services, API routes with role checks, and the screens in `frontend/src/`.
4. For any screen, follow docs/DESIGN.md and use the frontend-design and ui-ux-pro-max skills.
5. Run `make lint` and `make test` (or the uv/npm equivalents) until green.
6. Tick the milestone in docs/ROADMAP.md, update docs/SPEC.md if a rule changed, and commit
   with a conventional message (`feat(m$ARGUMENTS): ...`).
7. Stop. Summarise what you built, how to try it, and anything ambiguous you found.
