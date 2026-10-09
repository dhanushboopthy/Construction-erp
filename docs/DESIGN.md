# Design system

The UI is a work tool for a steel and cement counter: staff bill fast under pressure on a PC,
the owner checks numbers. Speed, legibility of figures and keyboard use come first.

Use the project skills for new screens: `frontend-design` (direction, restraint) and
`ui-ux-pro-max` (rules and checks, see `.claude/skills/README.md`). This file wins over generic
search results.

## Tokens (`frontend/src/styles/tokens.css`)

| Token | Value | Use |
| --- | --- | --- |
| `--color-slab` | `#F3F4F2` | Page background (concrete slab grey) |
| `--color-surface` | `#FFFFFF` | Tables, forms |
| `--color-ink` | `#1C2321` | Text, sidebar |
| `--color-steel` | `#5B6661` | Secondary text, labels |
| `--color-rule` | `#D5D9D6` | Borders, dividers |
| `--color-oxide` | `#2F5D50` | Primary actions (painted structural steel) |
| `--color-tag` | `#F2C230` | **One place only:** bill total band, active row and nav marker (bundle-tag yellow). Text on it is ink. |
| `--color-good` / `-warn` / `-critical` | `#2E7D4F` / `#A16207` / `#B42318` | Status only, always with a word, never colour alone |

**Type:** IBM Plex Sans, self-hosted (works offline). Numbers use tabular figures (`.num`) and
right alignment. Sizes 12 / 14 / 16 / 20 / 28, figures 36. Sentence case everywhere; no
all-caps labels.

**Spacing:** dense 4-px scale (4, 8, 12, 16, 24, 32). Radius 4–6 px.

## Principles

1. **Keyboard first.** Every flow works without a mouse: Alt+1–9 modules, Enter to add a line,
   F-keys documented on screen. Visible focus rings always.
2. **Figures are the hero.** Totals large and tabular; the bill total sits on the tag-yellow band.
3. **Structure carries meaning.** Ledgers and dividers, not decorative cards and shadows.
4. **Say what happens.** Buttons name the action ("Save bill", "Approve with PIN"); errors say
   what is wrong and what to do; empty screens say how to start.
5. **Owner-only data looks the same** but never reaches staff screens (enforced by the API).
6. **Accessibility floor:** contrast 4.5:1, labels on every input, status not by colour alone,
   reduced motion respected, works at 1024 px and on a phone for the owner.
7. **Tamil labels later:** keep strings in one place per screen so translation can be added.
