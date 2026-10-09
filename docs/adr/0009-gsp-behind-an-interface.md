# ADR 0009: The GSP sits behind an interface, with a fake that never runs in production

**Status:** Accepted, Milestone 10

**Context.** E-way bills and IRNs come from the government portal through a GSP (GST Suvidha
Provider) that the owner has not chosen yet (GAP_ANALYSIS). Each GSP words its API differently,
sandbox keys are needed to test, and ADR 0005 forbids documents that exist only inside our system
while looking real.

**Decision.**

- `services/gsp` defines `GspClient` (generate, update vehicle and cancel an e-way bill;
  generate and cancel an IRN). Three adapters: `FakeGsp` (development and tests), and
  `SandboxGsp`, one HTTP adapter for a real provider's sandbox or live API, chosen by
  `GSP_PROVIDER` (`fake`, `sandbox`, `live`). Keys are environment variables (`GSP_*`), never
  committed or logged.
- In production `GSP_PROVIDER=fake` is refused (`GSP_NOT_CONFIGURED`, answered as 502): a pretend
  e-way bill must never reach a truck.
- All provider field naming lives in `sandbox.py` (`_eway_body`-style helpers); switching to the
  chosen GSP's exact format changes that file only. The mapping is written against a plain JSON
  shape and is **not yet checked against any real provider**: do that with the sandbox keys.
- A call to the provider happens before anything is saved; on failure nothing is stored and the
  answer is 502 with a retryable hint, so retrying is always safe. A partial unique index allows
  one live e-way bill per invoice, and an advisory lock stops two counters making two at once.
  Every call's raw answer is kept on the row (G12).
- Manual fallback: the owner can type a number made on the portal by hand; such a bill is only
  recorded, never updated or cancelled through the GSP.
- Cancellation windows (24 hours) are enforced here as well as at the portal.

**Consequences.** Development and the test suite run offline. Going live is configuration plus
one adapter check against the provider's documentation. Credit and debit notes do not carry an
IRN yet (open question for the accountant: needed once e-invoicing is switched on).
