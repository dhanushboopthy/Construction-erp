"""Single tenant for now (ADR 0004).

Every table has tenant_id and every query filters on it, so going multi-tenant later means
reading the tenant from the signed-in user and adding row-level security, not a rewrite.
"""

TENANT_ID = 1
