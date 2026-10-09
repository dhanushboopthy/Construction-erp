# Project skills

Claude Code loads these automatically for this repo. Both are copied unchanged from upstream;
to update, copy the folder again from the source and keep the license file.

| Skill | Use it for | Source | License |
| --- | --- | --- | --- |
| `frontend-design` | Visual direction, typography and avoiding templated UI | [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/frontend-design) (commit `9d63080`, 2026-10-09) | `frontend-design/LICENSE.txt` |
| `ui-ux-pro-max` | Searchable UX rules, palettes, fonts, accessibility checks, stack guidance | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/main/.claude/skills/ui-ux-pro-max) (commit `50d8a7d`, 2026-10-08) | MIT, `ui-ux-pro-max/LICENSE` |
| `impeccable` | Design commands (`/impeccable init`, `polish`, `typeset`, `adapt`…) and an anti-pattern detector | [pbakaus/impeccable](https://github.com/pbakaus/impeccable), installed with `npx impeccable install --project --providers=claude` (v4.5.2) | Apache 2.0 |

## Running the ui-ux-pro-max search here

Its SKILL.md shows paths under `${CLAUDE_PLUGIN_ROOT}`. In this repo, run it from the repo
root instead (Python 3, no dependencies):

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "data table keyboard" --stack react
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "form error near field" --domain ux
```

The project's own design decisions live in `docs/DESIGN.md` and win over generic search
results. Do not run `--persist`; record decisions in `docs/DESIGN.md` instead.

## Impeccable

Installed with `npx impeccable install`. It adds `.claude/skills/impeccable/` and four agents in
`.claude/agents/`. Its engine binary is not committed: the launcher downloads it on first use.
The design-check hooks live in each developer's `.claude/settings.local.json` (not shared); run
`npx impeccable install --project --providers=claude -y` once on a new machine to add them, and
`/impeccable hooks off` to turn them off. Start with `/impeccable init` to record the design
context (it should follow `docs/DESIGN.md`).
