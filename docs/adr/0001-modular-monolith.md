# ADR 0001: Modular monolith on one machine

**Status:** Accepted, 2026-10-09

**Context.** One shop client, a fixed delivery date, one developer working with Claude Code.

**Decision.** One FastAPI service, one PostgreSQL database, one React + TypeScript app, run with
Docker Compose on a single machine. Modules are folders inside the backend (`api`, `services`,
`domain`, `models`), not separate services.

**Consequences.** Simple to run, test and back up. Transactions span modules freely (invoice +
stock + numbering in one commit). Scaling beyond one machine is not needed for years; if SaaS
grows, split later along module lines.
