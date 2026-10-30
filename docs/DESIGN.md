# Design system

The UI is a work tool for a steel and cement counter: staff bill fast under pressure on a PC,
the owner checks numbers. Speed, legibility of figures and keyboard use come first.

Use the project skills for new screens: `frontend-design` (direction, restraint) and
`ui-ux-pro-max` (rules and checks, see `.claude/skills/README.md`). This file wins over generic
search results.

## Look

"Site navy" (from the owner's reference, October 2026; plan in
[UI_REFACTOR_PLAN](UI_REFACTOR_PLAN.md)): a cool-grey canvas, white cards with radius 12 and one
soft shadow, a navy sidebar in both themes, and a single orange accent for actions, links and the
active marker. Status uses green, amber and red, always with a word. There are no gradients and no
coloured glow. Small labels are uppercase with wide tracking; figures are large and extra-bold.

**Frame.** Navy sidebar, 240 px wide. Brand block: an orange tile with the business's initials, the
business name from `GET /tenant` (the product name "Construction ERP" stands in until it arrives)
and "Construction ERP" under it. Nav: a Lucide icon and label per module the role may open (the
list comes from `modulesFor(role)`, nothing else), the shortcut (`Alt 2`) shown on hover and
focus and in the tooltip; the current screen sits on a lighter navy block with an orange marker on
the sidebar's left edge. After the modules comes **Alerts**, a button (not a screen) with an orange
count badge of out-of-stock items plus e-way bills still to be made; the badge is hidden at zero
and read out as "3 alerts". Settings sits below a divider (owner only), and the tagline closes
the sidebar ("Bill fast. Close on time." until shops can set their own).

Top bar: the search box that is also the command palette (Ctrl+K or `/`; arrows and Enter) on the
left; on the right the location pill with a live dot, the alerts bell with an orange dot when
there is something to look at, quick actions, a divider, and the signed-in user (avatar, name,
role) whose chevron menu holds the light/dark switch and Sign out. The bell and the sidebar's
Alerts item open the same panel; the count loads with the screen and is fetched again each time
the panel opens.

**Narrow screens.** Below 1200 px the sidebar shrinks to 72 px of icons: the label becomes the
tooltip (and stays for screen readers) and the badge moves onto the icon. Below 900 px it becomes
a scrolling strip of pills at the top, the current one in bright orange; the top bar keeps the
avatar and chevron (name and role are hidden). On screens shorter than 820 px the nav rows are
tighter so Settings stays in view.

**Today.** `PageHeader` (the shop name as eyebrow, the date and "Sales, dues and stock at a
glance." as subtitle), then a row of `KpiCard`s (four across at 1280 px and up, two across below
that, one on a phone), each one link to its detail screen: Net sales today, Profit today (owner),
Customers owe (with the share that is overdue as a bar), We owe suppliers, Cash tied up (owner),
Items in stock (with the share that is out of stock as a bar). The accountant gets an Overdue card
instead of profit. Counter staff get Net sales today, Items in stock and Waiting e-way bills, and
nothing else: their screen never requests the receivables report or a profit figure.

Below the cards (owner and accountant) the **Customer dues** table: top 8 customers who owe money,
most overdue first, then most owed. Columns: customer (avatar, name, oldest bill due), owes,
overdue with "N days late", credit used (bar and %, "Cash customer" when there is no limit), last
payment, status pill, chevron. Search and the status filter live in the URL (`?q=&status=`); a row
opens that customer (`/parties?party=ID`). Status comes from one tested function,
`dueStatus` in `src/lib/dues.ts`, in this order: **Over limit** (credit used above 100%), **Overdue**
(a bill is at least one day past its due date), **Near limit** (80% or more of the limit; the 80%
is a proposal to confirm with the owner, constant `NEAR_LIMIT_PCT`), then **OK**, or **Cash**
(neutral) when the customer has no credit limit. Under the table: the stock-levels card with
orange bars and a reorder tip, and the monthly sales chart (owner and accountant) whose bars grow
in once on load, the current month in orange and the other months in slate, values on hover or
focus.

**Light and dark.** A sun/moon button switches and remembers the choice per computer; until
someone picks, the app follows the operating system (`public/theme-init.js` applies it before
paint). Both themes are designed: dark is not the light theme inverted. In dark the accent turns
light orange (`#FB923C`) and the text on it navy, and status pills become tinted instead of solid.

**Focus.** Every focusable element gets a solid 3 px orange ring (`--color-focus`, at least 3:1
on white, the canvas and dark surfaces). Inside the sidebar the ring switches to the bright orange
so it shows on navy.

## Tokens (`frontend/src/styles/tokens.css`)

| Token | Light / dark | Use |
| --- | --- | --- |
| `--color-bg` | `#F3F5F8` / `#0B1220` | Page canvas (cool grey) |
| `--color-surface` | `#FFFFFF` / `#131D2E` | Cards, tables, forms |
| `--color-surface-raised` | `#FFFFFF` / `#1A2639` | Menus, dialogs |
| `--color-fill` | `#EEF1F6` / `#1D2A3F` | Tracks, segmented controls, grey buttons |
| `--color-hover` | navy 4% / white 5% | Row and menu hover on content |
| `--color-label` | `#0F1E33` / `#E8EDF5` | Text (navy) |
| `--color-secondary` | `#5B6678` / `#9AA6B8` | Labels, secondary text |
| `--color-separator` | `#E1E6EE` / `#243247` | Hairlines |
| `--color-control-border` | `#76839A` / `#6B7A91` | Input borders, quiet chart bars (3:1 non-text floor) |
| `--color-sidebar`, `-active` | `#0F1E33`, `#1E3354` / `#08111F`, `#18294A` | Sidebar and its active block (navy in both themes) |
| `--color-on-sidebar`, `-muted` | `#FFFFFF`, `#A9B4C6` / `#FFFFFF`, `#94A3B8` | Sidebar text and icons; tagline, section labels |
| `--color-sidebar-hover`, `-line` | white 7% / 12% | Sidebar hover and dividers |
| `--color-accent` | `#C2410C` / `#FB923C` | Primary buttons, links, active marks |
| `--color-accent-strong` | `#9A3412` / `#FDBA74` | Hover on accent |
| `--color-on-accent` | `#FFFFFF` / `#0B1220` | Text on accent: white on light, navy on dark |
| `--color-accent-bright` | `#F97316` / `#FB923C` | Decorative: brand tile, alert dot, count badge, sidebar marker; text on it is navy (`--color-on-accent-bright`) |
| `--color-hero` | `#0F1E33` / `#1E3354` | The bill total card (white text) |
| `--color-good` / `-warn` / `-critical` | `#15803D` `#B45309` `#B91C1C` / `#4ADE80` `#FBBF24` `#F87171` | Status, always with a word; `-soft` tints badges and alerts |
| `--color-neutral-pill` | `#64748B` / `#94A3B8` | "Cash customer", "Draft", "No data" |
| `--pill-{good,warn,critical,neutral,accent}-bg` / `-fg` | solid + white / tint + status colour | Status pills (component in T2): solid in light, tinted in dark |
| `--color-series-1..4` | orange, navy, slate, light slate / orange, steel blue, slate, dark slate | Chart series (sales by segment); replaces the old `--color-chart-*` |
| `--sidebar-width` | 240 px; 72 px below 1200 px | Sidebar column |
| `--shadow-card`, `--shadow-raised` | soft navy shadow / ring + black | Cards; menus and dialogs. No glow |

**Contrast (light / dark).** Measured from the token values (WCAG 2.x); the test
`src/styles/tokens.test.ts` fails if any pair drops below its floor, so this table cannot drift.

| Pair | Ratio | Floor |
| --- | --- | --- |
| label on canvas / on card | 15.3 / 15.9 and 16.7 / 14.4 | 4.5 |
| secondary on canvas / card / fill | 5.3 / 7.6, 5.8 / 6.9, 5.1 / 5.9 | 4.5 |
| accent (link, text) on card / canvas | 5.2 / 7.5 and 4.7 / 8.3 | 4.5 |
| accent on its soft tint | 4.6 / 5.7 | 4.5 |
| `on-accent` on accent / accent-strong (button, hover) | 5.2 / 8.3 and 7.3 / 11.1 | 4.5 |
| navy on bright orange (brand tile, badge) | 6.0 / 7.4 | 4.5 |
| good, warn, critical on card | 5.0 / 9.7, 5.0 / 10.1, 6.5 / 6.1 | 4.5 |
| good, warn, critical on their `-soft` tint | 4.5 / 7.2, 4.6 / 7.5, 5.7 / 5.0 | 4.5 |
| pill text: good, warn, critical, neutral | 5.0 / 7.2, 5.0 / 7.5, 6.5 / 5.0, 4.8 / 5.0 | 4.5 |
| white on sidebar / active block | 16.7 / 18.9 and 12.7 / 14.4 | 4.5 |
| muted sidebar text on sidebar / active block | 8.0 / 7.4 and 6.1 / 5.6 | 4.5 |
| white on the bill total card | 16.7 / 12.7 | 4.5 |
| control border on card / canvas / fill | 3.8 / 3.9, 3.5 / 4.3, 3.4 / 3.3 | 3 |
| focus ring on card / canvas | 5.2 / 7.5 | 3 |
| bright orange on sidebar (marker, focus) | 6.0 / 8.4 | 3 |
| status colours, accent and series 1–3 as graphics on card | 4.8 or more | 3 |

**Type:** Plus Jakarta Sans (variable), self-hosted so counter PCs work offline; one family for
everything. Titles 800 weight with tight tracking; small labels 700, uppercase, +0.08em. Numbers
use tabular figures (`.num`).

**Shape:** radius 8 (controls), 12 (cards, menus, dialogs), 999 (pills). `--radius-lg` equals
`--radius-md` for now so existing rules keep working. Spacing on a 4-px scale. Icons are Lucide
(`lucide-react`), 18–20 px, stroke ~1.9. Motion 150–250 ms, ease-out; the only entrance animation
is the chart bars and stock bars growing in; reduced motion turns it off.

**Colour outside `tokens.css`.** Components use tokens only. The three places a CSS variable cannot
reach hold a colour by hand: `index.html` (`theme-color`, the browser bar), `public/favicon.svg`
(navy and orange), and the select chevron in `Field.module.css` (a data URI, slate `#76839A`, the
control-border grey). Change them together with the tokens.

**Sizes.** `--row-height` (64 px table rows), `--icon-tile` (40 px KPI icon tile), `--avatar-sm` and
`--avatar-md` (32 and 40 px), `--bar-height` (8 px progress bars).

## Principles

1. **Keyboard first.** Every flow works without a mouse: Alt+1–9 and Alt+0 modules, Enter to add a line,
   F-keys documented on screen. Visible focus rings always.
2. **Figures are the hero.** Totals large and tabular; the bill total sits on the navy card.
3. **Colour means something.** Orange marks what to do or where you are; status colours always
   come with a word. Cards carry content, never other cards.
4. **Say what happens.** Buttons name the action ("Save bill", "Approve with PIN"); errors say
   what is wrong and what to do; empty screens say how to start.
5. **Owner-only data looks the same** but never reaches staff screens (enforced by the API).
6. **Accessibility floor:** contrast 4.5:1, labels on every input, status not by colour alone,
   reduced motion respected, works at 1024 px and on a phone for the owner.
7. **Tamil labels later:** keep strings in one place per screen so translation can be added.

## Components (`frontend/src/components/`)

Build screens from these; each has tests for its states, keyboard use and accessible names.

| Component | What it is | Rules |
| --- | --- | --- |
| `PageHeader` | Eyebrow (shop or section), title (`<h1>`), subtitle, actions slot on the right | One per screen. The title is the only `<h1>` |
| `KpiCard` | Label, big tabular value, icon tile coloured by tone, optional note, optional progress bar, optional link | With `href` the whole card is one link. The bar is `role="progressbar"` with `aria-valuenow/min/max` and the percentage written beside it. The value shrinks with the card so a long amount fits |
| `StatusPill` | Icon and word on a tone: good, warn, critical, neutral, accent | `label` is required (a pill without text does not type-check). Solid in light, tinted in dark |
| `Avatar` | Initials in a circle, navy or orange picked from the name, 32 or 40 px | Decorative next to a name; give `label` when it stands alone |
| `ProgressBar` | A bar with its percentage beside it, `role="progressbar"` | Used by `KpiCard` and the credit-used column |
| `DataTable` | The list pattern: 64 px rows, two-line first cell (`PrimaryCell`), right-aligned tabular figures, status column, chevron, sticky header | With `onOpen`: Up/Down between rows, Enter opens, click opens, the selected row has the accent marker. Draws loading, error (with retry) and empty states |
| `TableToolbar` + `useTableFilters` | Search (waits for a pause in typing; `/` focuses it), status `<select>`, optional date range | Filters live in the URL (`?q=&status=&from=&to=`), so Back, reload and a pasted link keep them |
| `Button` | `primary` (orange, one per screen), `secondary` (outlined), `ghost` (text only) | Radius 8; always `type="button"` unless it submits |
| `Field` family | Label above, hint and error under, 8 px radius, 3 px focus ring | Error and hint are linked with `aria-describedby`; a field error turns the border red |
| `Segmented` | One choice out of a few, always visible | A radio group: one tab stop, arrows, Home and End |
| Tabs (`styles.tabs` in `Ledger.module.css`) | Route tabs as a segmented strip | Used by the Reports, Stock, Rates, Transport and Settings layouts |

`Metric` (the KPI-catalogue figure with a formula tooltip) stays on the report screens until T7
moves them to `KpiCard`. `Ledger.module.css` keeps the dense editable tables (bill lines, setup
lists); `DataTable` is for read-and-open lists and is adopted screen by screen in T4 and T5.

## Patterns

- **Lists.** Every list screen is a `PageHeader`, a `TableToolbar` and a `DataTable`. Search is
  always there; a status filter is there where the rows have a status (Sales bills: e-way bill
  pending or posted; Stock: in or out of stock; Payments: received or paid out; Trips: paid or
  unpaid; Purchases: stock or customer's site; Items: category; Parties: customers or
  suppliers). The filters live in the URL (`?q=&status=`, and `place` on Stock), so Back, reload
  and a pasted link keep them, and opening a bill or a row keeps them too. `/` jumps to the
  search box. Not lists, so not converted: the cash book and the daily rate board (entry grids for
  one day) and the stock counts picker.
- **Entry screens (bill, purchase).** A white header card (customer, delivery, shop, date), one
  white card per line with the Field style (label above, error under the field), and the totals on
  the right in a navy card: line figures in white, the grand total large and white (`--color-on-hero`
  on `--color-hero`, 12.7:1 or better), problems in `--color-on-hero-critical`. Below 1100 px the
  totals card moves under the lines. The order of the fields is part of the design: from a line's
  item, two Tabs reach Quantity and Enter adds the next line; `BillKeys.test.tsx` fails if a
  5-line bill ever needs more keys than the 26 it takes today.
- **Forms.** Settings and other full-page forms are sections (heading and purpose on the left),
  two columns of fields from 1100 px and one below, with a sticky save bar. Editors beside a list
  (item, customer) stay one column in their side panel. Errors sit under their field.
- **List + editor.** Setup lists (users, locations, later items and parties) are a ledger table
  with an editor panel beside it (stacked below 1100 px). The row being edited carries the
  accent tint and marker bar. Alt+N opens a new record, Up/Down move between rows, Enter opens, Esc
  closes and returns focus to the row.
- **Settings say which rule they change.** A setting that controls a business rule shows a
  small "Rule B8" tag next to its label, so the owner can find it in docs/SPEC.md.
- **Errors sit under the field** they belong to (`aria-describedby`); server errors with a
  `field` are shown there too, others above the save button.
- **Phone:** below 900 px the sidebar becomes a scrolling strip of pills at the top; Sign out is
  in the user menu at the right of the top bar.
- **Command palette.** Every screen and common action is reachable from the search box; new
  actions go in `frontend/src/actions.ts` with the module they belong to (roles follow it).

## Checking the look

`npm run shots` (in `frontend/`, with the dev stack up and seeded) signs in as the owner, counter
and accountant seed users and saves a PNG of every routed screen in light and dark at 1440, 1024
and 390 px, plus the sign-in page, to `frontend/screenshots/baseline/<role>/<theme>-<width>/`
(git-ignored). Options: `--out <folder>`, `--roles owner,counter`, `--only sales,reports`. It
writes `manifest.json` and exits non-zero if a screen redirects. The screen list is in
`frontend/scripts/screenshots.ts`; it checks itself against `src/modules.ts`, so a new module
fails the run until it is added. Take a set before a UI change and another after, and compare.
Use development seed data only, never production. The UI refresh in
[UI_REFACTOR_PLAN](UI_REFACTOR_PLAN.md) uses this as its baseline.
