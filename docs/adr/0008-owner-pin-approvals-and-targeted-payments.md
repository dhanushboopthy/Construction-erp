# ADR 0008: Owner PIN approvals, and payments that can aim at a bill

**Status:** Accepted, Milestone 7

**Context.** Counter staff must not give credit, discounts, lower prices or back-dated bills
(SPEC section 2), yet the owner is often at the counter and wants to approve in seconds (G18).
Customers also pay specific bills, not only "the oldest" (SPEC 5.6).

**Decision.**

- The owner sets a PIN (hashed like a password, `app_user.pin_hash`). At the counter the owner
  types it on the staff screen with a reason. The server creates an `approval` row (who asked,
  who approved, what, why, which customer), good for **one bill within ten minutes**, and writes
  an audit `override` event. An approval cannot be used by another user, for another customer,
  twice, or after it expires. Five wrong PINs lock the requester out for 15 minutes.
- Four actions: `credit_override`, `below_cost`, `discount`, `backdate`. The invoice request
  carries `approval_ids`; the same checks that block a counter user are skipped for exactly the
  approved action. The owner needs no approval, but when the owner waives a credit rule the
  bill gets an audit `override` event naming the rule.
- The 409 for a blocked bill says `requires_owner_approval` and never contains cost figures.
- Payments write ledger rows with an optional `applies_to` bill number. `domain.ledger.open_items`
  applies a targeted payment to that bill first and anything extra oldest-first; money beyond
  all bills stays as an advance (G21). The balance and aging therefore always come from the
  ledger alone, with no separate allocation table that could disagree with it.
- Cash from one customer in one day at or above `cash_receipt_limit` is refused (G14). Cash taken
  with a bill counts. This cannot be waived by anyone, because it is a legal limit.
- Credit is checked on the unpaid part of a bill only, after money taken with it (B8), under an
  advisory lock on the customer so two counters cannot both spend the last of a limit.

**Consequences.** The counter flow never needs the owner to log in. Every override leaves a
trail. Explicit allocation costs nothing extra to store.
