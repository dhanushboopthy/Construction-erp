# ADR 0010: Issued documents are permanent in the database, and the books can be proved

**Status:** Accepted, Milestone 14

**Context.** The rules say issued documents are never deleted or edited (B16) and that records are
kept for 72 months (G15). Until now only the application behaved that way. A script, a console
session or a bad restore could still change a bill, and nobody could show that the books were
whole after a restore.

**Decision.**

- Database triggers refuse `DELETE` on every issued-document table (bills, credit and debit notes,
  purchases, payments, transfers, e-way bills, e-invoices, closings, attachments, 2B imports) and
  refuse `UPDATE` of their figures. Only `updated_at` and `updated_by` may change. The two
  ledgers were already append-only. The status of an e-way bill or an e-invoice, and a closing's
  open or reopened state, may still change; they are never deleted.
- `python -m app.scripts.verify` (and Settings, System) re-adds the books from scratch: database
  version, the guards above are all present, document numbers have no gaps in any series,
  every bill and note adds up to its lines, party accounts match the documents behind them, stock
  replayed from the ledger is never negative, and every stored file and closing PDF exists (with
  `--full`, its checksum matches).
- Backups hold the database and the uploaded files together. A monthly **restore drill** restores
  the newest backup into a scratch database and folder, runs the check on it, and records the
  result. A backup that has not been drilled is not trusted.
- Every API route requires a sign-in except sign-in itself and the health checks; a test fails the
  build if a new route forgets this. API answers carry `Cache-Control: no-store`.

**Consequences.** A correction is always a new document. A mistaken script fails loudly instead of
quietly changing money. Migrations that must change an issued table have to drop the trigger
inside the migration, which makes such a change visible in review. Restore is boring and proven.
