# UI refactor plan: "Site navy"

Status: proposed (October 2026). Replaces the "Indigo works" look in `docs/DESIGN.md` once done.

Reference: the owner's mock-up of a compliance dashboard (navy sidebar, orange accent, KPI cards
with progress bars, a document table with status pills). We take its **look and layout**, not its
content: the ERP keeps its own screens, rules and data.

## 1. Direction

| In the reference | In the ERP |
| --- | --- |
| "BuildTrack" logo and "Compliance made simple" | The tenant's company name and initials tile (logo later, task T10); tagline from shop settings |
| Navy sidebar, white icons, active item on a lighter navy block | Same, for every module in `src/modules.ts`, keeping Alt+key shortcuts |
| "Alerts 3" orange count badge | Alerts entry with the count of out-of-stock items and waiting e-way bills |
| Footer "Less paperwork. More building." | Small tagline at the sidebar foot (text set per tenant, default "Bill fast. Close on time.") |
| Eyebrow + title + subtitle header | `PageHeader`: eyebrow = shop or section, title = screen name, subtitle = purpose from `modules.ts` |
| Bell with dot, avatar + name + role | Alerts bell, user avatar (initials), name, role ("Owner", "Counter", "Accountant"), menu with Sign out and theme |
| 4 KPI cards, icon top right, progress bar + % | KPI cards on Today and on report screens |
| Subcontractor table: avatar, name/trade, 3 document columns, status pill, chevron | Customer dues table on Today; the same table pattern for every list screen |
| Search box + "All statuses" filter above the table | Same toolbar on every list (search, status filter, date range where the screen has one) |

## 2. Rules that do not change

- Every rule in `CLAUDE.md` and `docs/DESIGN.md` principles 1–7: keyboard first, tabular figures,
  tokens only (no raw hex outside `tokens.css`), status always has a word, 4.5:1 text contrast,
  works at 1024 px and on a phone.
- Cost, margin and profit never reach counter users. The redesign changes CSS and markup, not what
  each role is sent. The customer dues table uses `GET /reports/receivables`, which is owner and
  accountant only: counter users do not get it.
- The printed bill (Tally-style layout, rendered by the backend) keeps its own layout and Arial.
  This refactor must not change it.
- The Duolink admin (`src/admin/`) keeps showing counts and statuses only (ADR 0012).
- Dark mode stays. Both themes are designed, not one inverted.
- Lucide icons and Plus Jakarta Sans (self-hosted) stay. The reference's typeface is close enough,
  and changing it would break offline use on counter PCs.

## 3. Proposed tokens

Starting values. Check every text and control pair with a contrast checker before merging.

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--color-bg` | `#F3F5F8` | `#0B1220` | Page canvas (cool grey) |
| `--color-surface` | `#FFFFFF` | `#131D2E` | Cards, tables, forms |
| `--color-sidebar` | `#0F1E33` | `#08111F` | Sidebar (navy in both themes) |
| `--color-sidebar-active` | `#1E3354` | `#18294A` | Active nav block |
| `--color-on-sidebar` | `#FFFFFF` | `#FFFFFF` | Sidebar text and icons |
| `--color-on-sidebar-muted` | `#A9B4C6` | `#94A3B8` | Sidebar tagline, section labels |
| `--color-label` | `#0F1E33` | `#E8EDF5` | Text |
| `--color-secondary` | `#5B6678` | `#9AA6B8` | Secondary text (≥4.5:1) |
| `--color-accent` | `#C2410C` | `#FB923C` | Primary buttons, links, active marks (white text on light, navy text on dark) |
| `--color-accent-bright` | `#F97316` | `#FB923C` | Decorative only: logo, alert dot, count badge with navy text |
| `--color-good` | `#15803D` | `#4ADE80` | "Paid", "In stock", "OK" |
| `--color-warn` | `#B45309` | `#FBBF24` | "Near limit", "Reorder", "Due soon" |
| `--color-critical` | `#B91C1C` | `#F87171` | "Overdue", "Over limit", "Out of stock" |
| `--color-neutral-pill` | `#64748B` | `#94A3B8` | "Cash customer", "Draft", "No data" |

Pills: solid fill with white text in light mode (the reference style), soft tint with coloured text
in dark mode. Radii: 8 (controls), 12 (cards), 999 (pills). Shadows: one soft card shadow, no
coloured glow. The indigo gradients are removed.

## 4. Prompt (paste into Claude Code, one task per session)

```text
We are refactoring the ERP UI to the "Site navy" look. Read docs/UI_REFACTOR_PLAN.md (the plan),
docs/DESIGN.md, CLAUDE.md, and the reference image I attach. Use the frontend-design and
ui-ux-pro-max skills.

Do task <T-number> only, on its own branch (style/ui-<short-name>). Follow its subtasks and meet
every acceptance criterion; list each criterion in your final report as met or not met, with
evidence (test name, screenshot path or command output).

Constraints:
- CSS Modules and tokens only; no raw hex outside frontend/src/styles/tokens.css.
- Do not change API responses, role checks or the printed bill.
- Keep every keyboard shortcut and focus behaviour that exists today; existing tests must pass
  unchanged unless the task says a test is updated, and say why.
- Light and dark themes, 1024 px and phone (390 px) widths.
- Update docs/DESIGN.md for anything you change, in the same commit.
- make test and make lint green before you finish. Do not push; tell me when it is ready.

If the plan is unclear or conflicts with the code, stop and ask me.
```

## 5. Tasks

Each task is one branch and one PR, in this order. T1 and T2 come before the rest; T5–T9 can then
go in any order.

### T0. Baseline

- T0.1 Branch `style/ui-baseline` from `main`.
- T0.2 Take light and dark screenshots of every screen in `src/modules.ts` at 1440 px, 1024 px
  and 390 px (Playwright script in `frontend/scripts/`, output in a git-ignored folder).
- T0.3 Add a "UI refresh" line to `docs/ROADMAP.md` with tasks T1–T11.

Acceptance:
- [ ] Screenshot script runs with one command and covers every module route for owner and counter.
- [ ] `make test` and `make lint` green on the branch.

### T1. Tokens and design doc

- T1.1 Replace the light and dark values in `frontend/src/styles/tokens.css` with section 3; keep
  the existing token names where the meaning is the same, add the new ones, delete the gradients.
- T1.2 Find components that use the removed tokens (`--gradient-*`, `--color-violet`, chart
  tokens) and move them to the new ones.
- T1.3 Rewrite the "Look" and "Tokens" sections of `docs/DESIGN.md`; record the contrast ratio of
  each text pair.
- T1.4 Update `public/favicon.svg` and the theme colour meta tag to navy/orange.

Acceptance:
- [ ] `grep` finds no hex colour outside `tokens.css` and no use of a deleted token.
- [ ] Every text-on-background pair in the table is ≥4.5:1; controls and progress bars ≥3:1.
- [ ] App still renders in both themes with no unstyled element (compare with T0 screenshots).

### T2. Shared components

- T2.1 `PageHeader`: eyebrow, title, subtitle, actions slot on the right.
- T2.2 `KpiCard`: label, big tabular value, icon top right with status tone, optional progress bar
  with a % label, optional link (whole card is one link, focusable). Replaces `Metric` where used.
- T2.3 `StatusPill`: tone (good, warn, critical, neutral, accent), icon + word, never colour alone.
- T2.4 `Avatar`: initials from a name, tone picked from the name (navy or orange), sizes 32/40.
- T2.5 `DataTable` (restyle `Ledger.module.css`): row height 64 px with avatar, two-line primary
  cell (name / sub-line), right-aligned tabular money, status column, chevron column; sticky
  header; Up/Down/Enter row navigation kept; empty, loading and error states.
- T2.6 `TableToolbar`: search input (debounced), status `<select>`, optional date range; filter
  values kept in the URL query so Back keeps them.
- T2.7 Restyle `Button` (primary orange, secondary outline, ghost), `Field` (8 px radius, label
  above, error under), segmented control and tabs.
- T2.8 Unit tests for each component (Vitest + Testing Library).

Acceptance:
- [ ] Each component has tests for its states, keyboard use and accessible names.
- [ ] `StatusPill` cannot be rendered without a text label (type-checked).
- [ ] `KpiCard` progress bar has `role="progressbar"` with `aria-valuenow`, `min`, `max`.
- [ ] Table keyboard navigation works exactly as in the current `Ledger` pattern (DESIGN.md
  "List + editor").
- [ ] No component uses a raw colour or pixel value that has a token.

### T3. App shell: sidebar and top bar

- T3.1 `AppShell`: navy sidebar 240 px; brand block (initials tile + tenant name from
  `GET /tenant`, tagline under it); nav items with Lucide icon, label and shortcut hint on hover;
  active item on `--color-sidebar-active` with an orange marker on the left edge.
- T3.2 Alerts as a nav item with an orange count badge (out-of-stock + waiting e-way bills); the
  count loads once and refreshes when the alerts panel opens.
- T3.3 Settings below a divider; sidebar foot with the tagline.
- T3.4 Collapse to icons only below 1200 px (tooltip shows the label); below 900 px keep the
  current scrolling pill strip, restyled navy.
- T3.5 `TopBar`: command search on the left (Ctrl+K and `/` kept); on the right the location pill,
  bell with orange dot when there are alerts, divider, avatar + name + role, chevron menu (theme,
  Sign out).
- T3.6 Admin app (`src/admin/AdminShell.tsx`) gets the same shell with the Duolink name.

Acceptance:
- [ ] Every module from `modulesFor(role)` appears for owner, counter and accountant, no more.
- [ ] Alt+1–9, Alt+0, Ctrl+K and `/` still work; focus ring visible on navy and white.
- [ ] Tenant name comes from the API; nothing says "BuildTrack" or any fixed company name.
- [ ] Alerts badge hides at 0 and says "3 alerts" to screen readers.
- [ ] Works at 1440, 1024 and 390 px in both themes.

### T4. Today dashboard

- T4.1 `PageHeader`: eyebrow = current shop name, title "Today", subtitle "Sales, dues and stock
  at a glance."
- T4.2 KPI row (4 cards, wrap to 2 at 1024 px, 1 on phone):
  - Owner: Net sales today (vs. same day last week as %), Customers owe (overdue share as bar),
    Profit today (owner only, as now), Out of stock (count; bar = share of items).
  - Accountant: same without Profit today; shows Overdue amount instead.
  - Counter: Net sales today (own shop), Bills today, Out of stock, Waiting e-way bills.
- T4.3 Customer dues table (owner and accountant), from `GET /reports/receivables`:
  avatar, name + phone or site, Owes (₹), Overdue (₹) with "N days late", Credit used (bar + %;
  "Cash customer" when no limit), Last payment, status pill, chevron to the party statement.
- T4.4 Status rules (from rule B8): **Over limit** (critical) when utilisation > 100%;
  **Overdue** (critical) when `days_late` > 0; **Near limit** (warn) when utilisation ≥ 80%
  (threshold to confirm, see section 7); **OK** (good) otherwise; **Cash** (neutral) when no
  credit limit. Put this in one tested function, not in JSX.
- T4.5 Toolbar: search by name, status filter (All, Overdue, Over limit, Near limit, OK), sorted
  by overdue then owes; top 8 rows with "View all dues" to the receivables report.
- T4.6 Keep the stock-levels card and monthly sales chart, restyled to the new tokens, below the
  table.

Acceptance:
- [ ] A counter user's Today never requests `/reports/receivables` or a profit figure (test with
  the mock API as a counter user).
- [ ] Status function has unit tests for each status and the boundaries (79.99%, 80%, 100%,
  100.01%, 0 and 1 day late, no limit).
- [ ] Money shown with `formatMoney`, tabular figures, right aligned; no float maths in the UI.
- [ ] Each KPI card and each row opens its detail screen by mouse and by keyboard.
- [ ] Empty state ("No customer owes money today") and error state with retry.

### T5. List screens

Apply `PageHeader`, `TableToolbar`, `DataTable` and `StatusPill` to:

- T5.1 Sales bills, quotations and proformas (`pages/sales/SalesPage.tsx`, `QuotesPage.tsx`):
  pills Paid / Part paid / Unpaid / Cancelled / E-way pending.
- T5.2 Purchases and orders (`pages/purchases/*Page.tsx`): pills Paid / Due / Advance adjusted;
  order match status.
- T5.3 Stock (`pages/stock/*Page.tsx`): In stock / Reorder / Out; transfers and counts.
- T5.4 Customers and suppliers (`pages/parties/PartiesPage.tsx`), items (`pages/items/ItemsPage.tsx`).
- T5.5 Payments and cash book (`pages/payments`, `pages/cash`).
- T5.6 Daily rates, transport (`pages/rates`, `pages/transport`).

Acceptance:
- [ ] Every list has search, a status filter where the data has a status, and URL-kept filters.
- [ ] List + editor screens keep Alt+N, Up/Down, Enter and Esc behaviour.
- [ ] No counter-visible list shows cost, margin or profit columns (existing role tests pass).
- [ ] Existing page tests pass; any changed selector is changed to a role/name query, not a class.

### T6. Entry forms

- T6.1 Bill entry (`BillEntryPage.tsx`): header card (customer, site, shop), lines table with the
  new field style, totals card on the right in navy with the grand total large and white.
- T6.2 Purchase entry (`PurchaseEntryPage.tsx`) with charges and landed cost in the same layout.
- T6.3 Returns, cancel bill, e-way panel, write-off, adjustments: dialogs and panels restyled.
- T6.4 Editors (party, item, settings pages): two-column form at ≥1100 px, one column below,
  section headings, sticky save bar.

Acceptance:
- [ ] Billing a 5-line bill by keyboard only takes no more keystrokes than today (write the
  sequence in the PR).
- [ ] Field errors sit under their field with `aria-describedby`; server field errors still map.
- [ ] Grand total is ≥4.5:1 on the navy card in both themes.
- [ ] All sales and purchase tests pass.

### T7. Reports and settings

- T7.1 Reports layout and each report page: `PageHeader`, KPI cards for the headline numbers,
  restyled tables and charts (chart colours from the new tokens).
- T7.2 Settings layout: left sub-nav restyled; "Rule B8" tags as neutral pills.

Acceptance:
- [ ] Owner-only reports stay hidden from counter users (existing tests).
- [ ] Charts have readable labels and a non-colour cue for the highlighted series.

### T8. Sign-in page

- T8.1 Split layout: navy panel with tenant name and tagline, white form card.
- T8.2 Admin sign-in uses the Duolink name.

Acceptance:
- [ ] Shows the tenant name from `GET /tenant` before sign-in; a suspended tenant still shows its
  message.
- [ ] Login tests pass; the form works with Enter only.

### T9. Polish and QA

- T9.1 Re-run the T0 screenshot script; compare every screen in both themes and three widths.
- T9.2 Keyboard pass on Today, bill entry, purchase entry and one list + editor screen.
- T9.3 Axe check (via Vitest or Playwright) on every module route.
- T9.4 Reduced motion: no animation besides the existing bar grow-in, which turns off.
- T9.5 Print a bill and a quotation; compare with the PDF from `main`.

Acceptance:
- [ ] No axe violations of serious or critical impact.
- [ ] Printed bill unchanged (same PDF layout as `main`).
- [ ] `docs/DESIGN.md` describes the shipped look; `docs/ROADMAP.md` marks the UI refresh done.

### T10. Tenant logo (optional, needs backend)

- T10.1 Migration adding a logo reference to the tenant settings (follow the attachments storage
  already used), owner uploads it in Shop settings (PNG/SVG, max 200 KB, square).
- T10.2 `GET /tenant` returns the logo URL; sidebar and sign-in show it, else the initials tile.

Acceptance:
- [ ] Owner-only upload; counter and accountant get 403.
- [ ] Logo never shown in the Duolink admin's company list contents beyond what ADR 0012 allows.
- [ ] Migration reviewed; `alembic check` clean; tests for upload size and type limits.

## 6. Definition of done (every task)

- `make test` and `make lint` green.
- Light and dark, 1440 / 1024 / 390 px checked; screenshots attached to the PR.
- No raw hex outside `tokens.css`; no change to API responses or role checks.
- `docs/DESIGN.md` updated in the same PR.

## 7. Open questions for the owner

1. "Near limit" threshold for the dues table: 80% of the credit limit? (Not in SPEC; rule B8
   only blocks over the limit.)
2. Sidebar tagline: fixed text, or set per shop in Shop settings?
3. Is the tenant logo (T10) needed for launch, or is the initials tile enough?
