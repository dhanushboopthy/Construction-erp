# Gap analysis (spec v1.0 → v1.1)

Gaps found while turning the v1.0 spec into code, and the decision taken for each.
**Status:** `Decided` (built or specified) · `Owner` (confirm with the shop owner) ·
`Accountant` (confirm with the CA/accountant before go-live) · `Open` (no decision yet).

Compliance figures were checked on 2026-10-09 against secondary sources listed at the end.
They change; keep them in settings, not code.

| ID | Gap in v1.0 | Decision in v1.1 | Status |
| --- | --- | --- | --- |
| G1 | Landed cost added CGST + SGST to cost. A GST-registered shop claims that tax back as input tax credit and charges GST again on the sale, so cost and margin were overstated. | GST is excluded from cost by default; `include_gst_in_cost` setting for shops that cannot claim it. Cash-flow view can still show the gross amount paid. | Decided (Accountant to confirm ITC eligibility) |
| G2 | Not stated whether market rates include GST. | Rates are stored excluding GST; `rates_include_gst` setting backs out the tax if the owner quotes inclusive rates. | Owner |
| G3 | No rounding rule. | Tax per line rounded to paise, half-up; invoice total rounded to the nearest rupee with a round-off line. | Accountant |
| G4 | `S1/2026-27/00042` would break the 16-character limit for invoice numbers (CGST Rules, rule 46) once a series suffix is added. | `S1/26-27/00042`; location codes 1–2 characters; suffix per document type (C credit note, D debit note, DC challan, P purchase, R receipt). Enforced in `domain/fiscal.py`. | Decided |
| G5 | No rule for CGST+SGST vs IGST. | Place of supply = ship-to site state (delivery) or shop state (counter pickup); same state → CGST+SGST, else IGST. | Decided |
| G6 | Average cost per location or per business? | One weighted average per item for the business; quantity tracked per location. Transfers never change value. | Decided |
| G7 | TMT, pipes, angles and channels are sold by piece or bundle but priced by weight. | Item variant stores theoretical kg per piece; billing can enter pieces and convert, and the weighbridge weight overrides when available. | Owner (supply weights per size) |
| G8 | Cement and TMT prices differ by brand. | `brand` on the item; rates and margins are per item, so per brand. | Decided |
| G9 | No purchase returns or debit notes. | Purchase return → debit note → stock-out at cost, supplier balance reduced. | Decided (Milestone 8) |
| G10 | "Owner only" discounts, but not how. | Line discount reduces taxable value before tax; owner only; reason required. | Decided |
| G11 | Transport charged to the customer on the same bill: how is it taxed? | Treated as part of a composite supply, taxed at the goods' rate, as a separate line. | Accountant |
| G12 | E-invoicing (IRN) not mentioned. At ~50 e-way bills a day, turnover may pass ₹5 crore, after which B2B invoices need an IRN. | Choose a GSP that does both e-way bills and IRN; `einvoice_enabled` setting; `einvoice` table planned. | Accountant (track turnover) |
| G13 | E-way threshold and drop-ship details. | Inter-state ₹50,000; intra-state set per state (Tamil Nadu ₹1,00,000 per the source below) in settings. Sites store GSTIN or "URP" for bill-to/ship-to; a GSTN advisory (21 May 2026) proposed making Ship-To GSTIN mandatory, on hold as of 29 July 2026. | Accountant |
| G14 | Cash payments had no limit. Income-tax law bars receiving ₹2,00,000 or more in cash from one person in a day (section 221 of the Income-tax Act, 2025, formerly 269ST); cash expenses above ₹10,000 a day per person (₹35,000 for transporters) are not deductible. | Block cash receipts at the limit (`cash_receipt_limit`) and ask for UPI/bank; warn on large cash freight payments. | Accountant |
| G15 | No retention rule. | Keep records at least 72 months (CGST Act, section 36); no hard deletes; backups kept. | Decided |
| G16 | HSN digits on invoices depend on turnover (4 digits up to ₹5 crore, 6 above). | Store 8-digit HSN; print digits per a setting. | Accountant |
| G17 | Entries could be back-dated after daily closing. | After a shop-day is closed, its documents are locked; owner can reopen (audited). | Owner |
| G18 | "Needs owner" approvals had no mechanism. | Owner enters a PIN on the counter screen; `approval` row stores who, what and why; audit log entry. | Decided (Milestone 7) |
| G19 | Double-click or retry could create two invoices or payments. | `Idempotency-Key` header on invoice and payment creation; unique per key. | Decided (Milestone 6) |
| G20 | Weight variance threshold not given. | Default 0.50%, editable in settings. | Owner |
| G21 | Overpayments and customer advances. | Unallocated payment stays as an advance on the customer account and is used on the next bill. | Accountant |
| G22 | Sites had no state or GSTIN. | Each site has address, state code and optional GSTIN. | Decided |
| G23 | Authentication details missing. | Argon2 passwords, 30-minute access token, 12-hour rotating refresh cookie with reuse detection, lockout after 5 failures, sessions revoked on password change or deactivation. | Decided (built) |
| G24 | Backups not specified. | Nightly `pg_dump` kept 30 days + off-machine copy; monthly restore drill. | Decided (built) |
| G25 | Free market-rate API assumed. | None reliable found; manual daily rate screen with history; provider interface later. | Decided |
| G26 | Internet reliability at the shops unknown. | If unreliable, host on a server inside a shop (LAN) with off-site backups; otherwise a small VPS. | Open (Owner) |
| G28 | Counter staff may enter purchases (SPEC section 2) yet must not see cost. The supplier's rate is the start of cost. | Counter staff key in the bill but every purchase response to them omits rates, charges, landed cost and payable; the owner can switch counter entry off (`counter_can_enter_purchases`). See ADR 0007. | Owner (confirm who should enter purchases) |
| G27 | "Dummy" bills. | Dropped. Test data only in dev/staging, watermarked `TEST`, separate series; no hidden modes. | Decided (ADR 0005) |

## Still open from the owner interview

- Delivery date (decides how much of Milestones 7–13 fits before go-live).
- Printer at the counter: A4, thermal or dot matrix.
- Exact units, sizes and theoretical weights per item (G7).
- GSP for e-way bills and IRN: price per bill and sandbox access.
- Cloud storage for closing PDFs and slips: Google Drive, S3 or other.
- Accountant's import format for GSTR-1/3B data (ask for a sample file).

## Sources (checked 2026-10-09)

- [E-invoice turnover limit 2026 (InCorpX)](https://www.incorpx.io/blog/gst-e-invoice-turnover-limit-2026)
- [E-way bill limit 2026, state-wise (LegalDev)](https://legaldev.in/blog/e-way-bill-limit)
- [E-way bill changes 2026 (ClearTax)](https://cleartax.in/s/e-way-bill-changes-june-2026)
- [Cash transaction limits from April 2026 (InCorpX)](https://www.incorpx.io/blog/cash-transaction-limits-small-business-2026)
