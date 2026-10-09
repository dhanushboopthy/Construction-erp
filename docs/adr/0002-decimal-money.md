# ADR 0002: Decimal money and quantities

**Status:** Accepted, 2026-10-09

**Decision.** Money is `NUMERIC(14,2)`, quantity `NUMERIC(14,3)`, unit cost `NUMERIC(14,4)`, and
`Decimal` in Python. `app.domain.money` rejects floats. JSON carries decimals as strings.
Rounding is half-up: tax per line to paise, invoice total to the rupee with a round-off line.

**Consequences.** Totals match a calculator and the accountant's figures. The frontend must
format strings, not do arithmetic with JavaScript numbers; any client-side preview total is
display-only and the server recomputes.
