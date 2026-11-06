"""M26: the catalogue of deletable company data against `pg_constraint`.

A new table with `tenant_id` cannot be forgotten: it must be in the catalogue or on the preserved
list. Every declared blocker is a real foreign key, the order is a valid order, nothing outside
the catalogue cascades from inside it, and nothing preserved is in it.
"""

import pytest
from sqlalchemy import text

from app.domain import data_management as rules
from app.models.enums import PartyRef, StockRef
from app.services.platform.data_catalogue import (
    CATALOGUE,
    KINDS,
    ORDER,
    PRESERVED,
    TABLES,
)

pytestmark = pytest.mark.integration

KIND_OF = {t: k.key for k in CATALOGUE for t in k.tables}


@pytest.fixture
def foreign_keys(seeded):
    rows = seeded.execute(
        text(
            "SELECT c.conrelid::regclass::text, c.confrelid::regclass::text, c.confdeltype "
            "FROM pg_constraint c WHERE c.contype = 'f' "
            "AND c.connamespace = 'public'::regnamespace"
        )
    ).all()
    return [(child, parent, kind) for child, parent, kind in rows]


def test_every_table_with_a_tenant_is_in_the_catalogue_or_preserved(seeded):
    tenant_tables = set(
        seeded.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'tenant_id'"
            )
        ).scalars()
    )
    assert tenant_tables, "no tenant tables found"
    forgotten = tenant_tables - TABLES - PRESERVED
    assert forgotten == set(), f"classify these tables in data_catalogue.py: {sorted(forgotten)}"
    assert not (TABLES & PRESERVED)
    assert tenant_tables | {"tenant"} >= TABLES | PRESERVED, "a listed table does not exist"


def test_nothing_on_the_preserved_list_is_in_the_catalogue():
    never = {
        "app_user",
        "location",
        "shop_settings",
        "document_sequence",
        "subscription",
        "subscription_payment",
        "support_ticket",
        "support_message",
        "audit_log",
        "platform_audit_log",
        "auth_session",
    }
    assert never <= PRESERVED
    assert not (never & TABLES)
    assert all(not t.startswith("platform_") for t in TABLES)


def test_a_table_belongs_to_one_kind_only():
    seen = [t for k in CATALOGUE for t in k.tables]
    assert len(seen) == len(set(seen))
    assert len({k.key for k in CATALOGUE}) == len(CATALOGUE)


def test_every_declared_blocker_is_a_real_foreign_key(foreign_keys):
    real = {
        (KIND_OF[child], KIND_OF[parent])
        for child, parent, _ in foreign_keys
        if child in KIND_OF and parent in KIND_OF and KIND_OF[child] != KIND_OF[parent]
    }
    declared = {(by, k.key) for k in CATALOGUE for by in k.blocked_by}
    assert declared <= real, f"declared but not a foreign key: {sorted(declared - real)}"


def test_every_real_foreign_key_between_kinds_is_declared(foreign_keys):
    real = {
        (KIND_OF[child], KIND_OF[parent])
        for child, parent, _ in foreign_keys
        if child in KIND_OF and parent in KIND_OF and KIND_OF[child] != KIND_OF[parent]
    }
    declared = {(by, k.key) for k in CATALOGUE for by in k.blocked_by}
    assert real <= declared, f"a foreign key the catalogue does not know: {sorted(real - declared)}"


def test_the_order_is_a_valid_topological_order(foreign_keys):
    blocked_by = {k.key: set(k.blocked_by) | set(k.posted_by) for k in CATALOGUE}
    assert rules.order_is_valid(list(ORDER), blocked_by)
    kind_position = {k: i for i, k in enumerate(ORDER)}
    for child, parent, _ in foreign_keys:
        if child in KIND_OF and parent in KIND_OF:
            a, b = KIND_OF[child], KIND_OF[parent]
            if a != b:
                assert kind_position[a] < kind_position[b], f"{child} must go before {parent}"
            elif child != parent:
                tables = KINDS[a].tables
                assert tables.index(child) < tables.index(parent), f"{child} before {parent}"


def test_nothing_outside_the_catalogue_cascades_from_inside_it(foreign_keys):
    outside = [
        (child, parent, action)
        for child, parent, action in foreign_keys
        if child not in TABLES and parent in TABLES
    ]
    assert outside == [], f"a table outside the catalogue points into it: {outside}"
    cascades = [
        (child, parent)
        for child, parent, action in foreign_keys
        if parent in TABLES and action == "c" and child not in TABLES
    ]
    assert cascades == []


def test_every_ledger_posting_is_claimed_by_a_kind_or_left_to_the_ledgers():
    stock = {r for k in CATALOGUE for r in k.stock_refs}
    party = {r for k in CATALOGUE for r in k.party_refs}
    assert stock <= {r.value for r in StockRef} and party <= {r.value for r in PartyRef}
    assert {r.value for r in StockRef} - stock == set()
    assert {r.value for r in PartyRef} - party == {"rebate"}  # left to the ledgers kind
    posting = {k.key for k in CATALOGUE if k.stock_refs or k.party_refs}
    assert set(KINDS["ledgers"].posted_by) == posting


def test_the_files_a_kind_names_are_real_columns(seeded):
    for kind in CATALOGUE:
        for table, column in kind.files:
            found = seeded.execute(
                text(
                    "SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
                    "AND table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": column},
            ).first()
            assert found, f"{table}.{column}"
