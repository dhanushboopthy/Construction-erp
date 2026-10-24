# ADR 0004: Single tenant first, multi-tenant ready

**Status:** Superseded by [ADR 0011](0011-multi-tenant-saas-by-subdomain.md) (Milestone 15).
Accepted 2026-10-09.

**Decision.** Build for one shop now. Every table has `tenant_id` (default 1) and every query
filters on `TENANT_ID` from `app/core/tenancy.py`. No tenant sign-up, switching or isolation
logic yet. Shop-specific values live in `shop_settings`, never in code.

**Later.** Read the tenant from the signed-in user, add PostgreSQL row-level security on
`tenant_id`, and a tenant admin. Until then, a second client can run as its own Compose stack.
