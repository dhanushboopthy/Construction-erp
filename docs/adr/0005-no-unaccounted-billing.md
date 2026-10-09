# ADR 0005: Only real tax invoices; test data stays out of production

**Status:** Accepted, 2026-10-09

**Decision.** The system issues only real GST documents. There is no hidden, password-protected
or "dummy" billing mode, and no fake e-way bills. Customers without a GSTIN get a normal B2C
tax invoice. Quotations, if added, are clearly labelled estimates with their own series.

Test and demo data exist only in development or staging databases, carry a visible `TEST`
watermark, and use a separate numbering series. Production has no test switch.

**Consequences.** Protects the shop and the product in GST audits. Any request to add a hidden
mode is declined; point to this ADR.
