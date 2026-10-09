# Design system

The UI is a work tool for a steel and cement counter: staff bill fast under pressure on a PC,
the owner checks numbers. Speed, legibility of figures and keyboard use come first.

Use the project skills for new screens: `frontend-design` (direction, restraint) and
`ui-ux-pro-max` (rules and checks, see `.claude/skills/README.md`). This file wins over generic
search results.

## Look

Apple-style (macOS / iOS): light grey grouped background, white rounded cards with soft shadows,
one blue accent, a frosted sidebar with icons, large bold page titles, segmented-control tabs,
pill buttons and rounded fields with a blue focus glow. Dark mode follows the operating system.

## Tokens (`frontend/src/styles/tokens.css`)

| Token | Light / dark | Use |
| --- | --- | --- |
| `--color-bg` | `#F5F5F7` / `#000000` | Page background |
| `--color-surface` | `#FFFFFF` / `#1C1C1E` | Cards, tables, forms |
| `--color-fill` | `#E8E8ED` / `#2C2C2E` | Segmented controls, grey buttons, pills |
| `--color-label` | `#1D1D1F` / `#F5F5F7` | Text |
| `--color-secondary` | `#6E6E73` / `#98989D` | Secondary text, labels |
| `--color-separator` | `#E5E5EA` / `#38383A` | Hairlines between rows |
| `--color-control-border` | `#8E8E93` / `#7C7C80` | Input borders (3:1 non-text floor) |
| `--color-accent` | `#0071E3` / `#0A84FF` | Primary actions, links, active nav item, selected row |
| `--color-hero` | `#1D1D1F` / `#2C2C2E` | **One place only:** the bill total card (white figure on dark, like an Apple Pay summary) |
| `--color-good` / `-warn` / `-critical` | Apple system green / orange / red | Status only, always with a word, never colour alone. `-soft` variants tint message boxes |
| `--color-chart-1..4` | blue, orange, purple, grey | Chart series |

**Type:** the system font (SF Pro on Apple devices), with Inter self-hosted as the fallback so
Windows counter PCs look the same offline. Titles use tight tracking. Numbers use tabular
figures (`.num`) and right alignment. Sentence case everywhere; no all-caps labels.

**Shape:** radius 8 (controls), 12 (cards), 18 (widgets, login); buttons are pills. Spacing on
a 4-px scale (4, 8, 12, 16, 24, 32). Icons are Lucide (`lucide-react`), 18 px, stroke 1.8.

## Principles

1. **Keyboard first.** Every flow works without a mouse: Alt+1–9 and Alt+0 modules, Enter to add a line,
   F-keys documented on screen. Visible focus rings always.
2. **Figures are the hero.** Totals large and tabular; the bill total sits on the dark hero card.
3. **Calm surfaces.** Content sits on rounded cards with hairline rows; no heavy borders,
   no decoration beyond the accent.
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
- **Phone:** below 768 px the sidebar becomes a scrolling strip at the top.
