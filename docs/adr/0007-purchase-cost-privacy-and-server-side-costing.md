# ADR 0007: Purchases are entered by staff but costed only by the server for the owner

**Status:** Accepted, Milestone 4

**Context.** Counter staff may enter purchases for their own shop (SPEC section 2) but must never
see cost, margin or profit (B4), and a supplier's rate is the start of cost.

**Decision.**

- The landed-cost maths runs only on the server, in `domain/landed_cost.py`. The screen asks
  `POST /purchases/preview` (owner only) and shows the answer; it never computes money itself
  (ADR 0002).
- Purchase responses are split: `PurchaseOwnerOut` carries rates, charges, landed cost per
  unit and what we owe; `PurchaseOut` (counter staff and accountant) carries quantities only.
  The counter user types the supplier's bill, but nothing monetary comes back.
- Whether counter staff may enter purchases at all is a setting
  (`shop_settings.counter_can_enter_purchases`, default on) because the owner may prefer to key
  bills himself. Open question G28 asks him.
- **What we owe the supplier** (goods + GST + charges the supplier put on its own bill) is kept
  apart from **cost** (goods + all charges, GST only if `include_gst_in_cost`). Labour and
  vehicle charges we pay to others raise cost but are not supplier payable.
- A purchase is saved posted, never as a draft, and is never edited; the same supplier bill
  number cannot be entered twice. Corrections are purchase returns and debit notes (Milestone 8).
- Supplier payments and advances reuse the `payment` table that Milestone 7 extends to customer
  receipts. An `Idempotency-Key` makes a repeated request return the first payment (G19).

**Consequences.** Counter staff can do their job without a path to cost data. The server is the
single place where cost is computed, so reports and the screen cannot disagree.
