# ADR 0006: One stock ledger, one party ledger, and opening balances as drafts

**Status:** Accepted, Milestone 3

**Context.** Stock and balances must come from append-only ledgers (ADR 0003). Opening figures
have to appear in the same ledgers as everything that follows, so reports never need a special
case for "before go-live".

**Decision.**

- `stock_ledger` holds every movement of an item at a location (quantity in or out, cost per
  base unit, what created it). Quantity per location is the sum; the single company-wide average
  cost is rebuilt by replaying the rows in date order with `domain.stock_valuation.replay` (G6).
- `party_ledger` holds money between us and a party, in two accounts: `receivable` (customers;
  bills are debits) and `payable` (suppliers; bills are credits). Balances, open items and aging
  come from `domain.ledger`: payments clear the oldest bill first and extra money stays as an
  advance (SPEC section 5.6, G21). `v_party_ledger` in the first spec is this table plus those
  functions rather than a database view, so the rules stay in tested Python.
- Both tables have a database trigger that rejects UPDATE and DELETE, so append-only holds even
  against a bug or a manual query. A correction is a new row (stock count, credit or debit note).
- `opening_balance` rows are **drafts** the owner can edit or remove. Posting writes the ledger
  rows in one transaction and locks the drafts. One opening figure is allowed per item and
  location, and per party, site and kind.
- Stock cost and value are cost data: `/stock` has an owner model with `avg_cost` and `value`
  and a staff model with quantities only (rule B4).

**Consequences.** Every later milestone appends rows with `services.ledgers.add_stock_move`
and `add_party_entry` in the same transaction as its document. Reading all moves of an item is
fine at the expected volume (a few hundred thousand rows); if it slows, add periodic snapshots
as a new ADR without changing the rows.
