# Design system

The UI is a work tool for a steel and cement counter: staff bill fast under pressure on a PC,
the owner checks numbers. Speed, legibility of figures and keyboard use come first.

Use the project skills for new screens: `frontend-design` (direction, restraint) and
`ui-ux-pro-max` (rules and checks, see `.claude/skills/README.md`). This file wins over generic
search results.

## Look

"Indigo works" (from the owner's reference, October 2026): a lavender-tinted canvas, white cards
with large radii and soft indigo-tinted shadows, and an indigo-to-violet gradient kept for the few
things that matter most: the brand tile, the active nav marker, primary buttons, the bill total,
the user card and the current month's bar. Status uses emerald, amber and rose, always with a
word. Small labels are uppercase with wide tracking; figures are large and extra-bold.

**Frame.** White sidebar: brand tile, nav with icons (active item has a soft gradient wash and a
marker on the sidebar's inner edge), Settings set apart below a divider, and the signed-in user on
a gradient card with Sign out. Top bar: a search box that is also the command palette (Ctrl+K or
`/`; arrows and Enter), the location pill with a live dot, the alerts bell (out-of-stock items and
waiting e-way bills, loaded when opened), quick actions, and the light/dark toggle.

**Today.** KPI cards (each opens its detail screen) with a tinted corner disc and a status badge;
the stock-levels card with gradient bars and a reorder tip; the monthly sales chart (owner and
accountant) whose bars grow in once on load, the current month highlighted, values on hover or
focus. Counter staff see only their figures and the stock card.

**Light and dark.** A sun/moon button switches and remembers the choice per computer; until
someone picks, the app follows the operating system (`public/theme-init.js` applies it before
paint).

## Tokens (`frontend/src/styles/tokens.css`)

| Token | Light / dark | Use |
| --- | --- | --- |
| `--color-bg` | `#F4F5FB` / `#0B0C1A` | Page canvas (lavender tint) |
| `--color-surface` | `#FFFFFF` / `#14162B` | Cards, tables, forms, sidebar |
| `--color-fill` | `#EEF0F8` / `#22254A` | Tracks, segmented controls, grey buttons |
| `--color-label` | `#1B1D3A` / `#ECEDFB` | Text (deep navy) |
| `--color-secondary` | `#5F6488` / `#A3A7CF` | Labels, secondary text (≥4.5:1) |
| `--color-separator` | `#E8EAF4` / `#262A4D` | Hairlines |
| `--color-control-border` | `#8C91B5` / `#6E73A6` | Input borders (3:1 non-text floor) |
| `--color-accent` | `#4F46E5` / `#8B8CF8` | Links, active states, icons |
| `--gradient-action` | `#4F46E5 → #7C3AED` | Primary buttons, bill total, user card (white text passes 4.5:1 at both ends) |
| `--gradient-brand` | `#6366F1 → #A855F7` | Decorative fills only: brand tile, progress bars |
| `--color-good` / `-warn` / `-critical` | emerald / amber / rose | Status with a word; `-soft` tints badges and alerts |
| `--color-chart-1..4` | indigo, amber, violet, grey | Chart series |

**Type:** Plus Jakarta Sans (variable), self-hosted so counter PCs work offline; one family for
everything. Titles 800 weight with tight tracking; small labels 700, uppercase, +0.08em. Numbers
use tabular figures (`.num`).

**Shape:** radius 10 (controls), 16 (menus), 24 (cards); buttons 12. Spacing on a 4-px scale.
Icons are Lucide (`lucide-react`), 18–20 px, stroke ~1.9. Motion 150–250 ms, ease-out; the only
entrance animation is the chart bars and stock bars growing in; reduced motion turns it off.

## Principles

1. **Keyboard first.** Every flow works without a mouse: Alt+1–9 and Alt+0 modules, Enter to add a line,
   F-keys documented on screen. Visible focus rings always.
2. **Figures are the hero.** Totals large and tabular; the bill total sits on the gradient card.
3. **Colour means something.** The gradient marks what matters most; status colours always
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
