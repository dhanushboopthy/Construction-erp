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

**Frame.** Navy sidebar: brand tile (bright orange, navy icon), nav with icons (the active item sits
on a lighter navy block with an orange marker on the sidebar's inner edge), Settings set apart below
a divider, and the signed-in user on a lighter navy card with Sign out. Top bar: a search box that
is also the command palette (Ctrl+K or `/`; arrows and Enter), the location pill with a live dot,
the alerts bell (out-of-stock items and waiting e-way bills, loaded when opened), quick actions,
and the light/dark toggle. The sidebar and top bar are rebuilt in task T3 of the plan.

**Today.** KPI cards (each opens its detail screen) with a tinted corner disc and a status badge;
the stock-levels card with orange bars and a reorder tip; the monthly sales chart (owner and
accountant) whose bars grow in once on load, the current month in orange and the other months in
slate, values on hover or focus. Counter staff see only their figures and the stock card.

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

**Colour outside `tokens.css`.** Components use tokens only. The two places a CSS variable cannot
reach hold the same navy and orange by hand: `index.html` (`theme-color`, the browser bar) and
`public/favicon.svg`. Change them together with the tokens.

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

## Patterns

- **List + editor.** Setup lists (users, locations, later items and parties) are a ledger table
  with an editor panel beside it (stacked below 1100 px). The row being edited carries the
  accent tint and marker bar. Alt+N opens a new record, Up/Down move between rows, Enter opens, Esc
  closes and returns focus to the row.
- **Settings say which rule they change.** A setting that controls a business rule shows a
  small "Rule B8" tag next to its label, so the owner can find it in docs/SPEC.md.
- **Errors sit under the field** they belong to (`aria-describedby`); server errors with a
  `field` are shown there too, others above the save button.
- **Phone:** below 900 px the sidebar becomes a scrolling strip of pills at the top and Sign
  out moves to the top bar.
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
