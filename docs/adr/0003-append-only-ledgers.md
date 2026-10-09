# ADR 0003: Append-only ledgers and immutable documents

**Status:** Accepted, 2026-10-09

**Decision.** Stock and party balances are derived from append-only ledgers (`stock_ledger`,
payments and allocations), never stored as editable numbers. Issued invoices, notes and
receipts are never deleted or edited in place; corrections are credit or debit notes. Every
change to audited tables is written to `audit_log` in the same transaction. Document numbers
are gapless per location, type and financial year.

**Consequences.** Any figure can be traced to the documents behind it, which GST audits and the
owner's trust both need. Reports read through views; add indexes or snapshots if they slow down.
