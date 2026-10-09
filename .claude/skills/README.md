# Project skills

Claude Code loads these automatically for this repo. Both are copied unchanged from upstream;
to update, copy the folder again from the source and keep the license file.

| Skill | Use it for | Source | License |
| --- | --- | --- | --- |
| `frontend-design` | Visual direction, typography and avoiding templated UI | [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/frontend-design) (commit `9d63080`, 2026-10-09) | `frontend-design/LICENSE.txt` |
| `ui-ux-pro-max` | Searchable UX rules, palettes, fonts, accessibility checks, stack guidance | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/main/.claude/skills/ui-ux-pro-max) (commit `50d8a7d`, 2026-10-08) | MIT, `ui-ux-pro-max/LICENSE` |

## Running the ui-ux-pro-max search here

Its SKILL.md shows paths under `${CLAUDE_PLUGIN_ROOT}`. In this repo, run it from the repo
root instead (Python 3, no dependencies):

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "data table keyboard" --stack react
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "form error near field" --domain ux
```

The project's own design decisions live in `docs/DESIGN.md` and win over generic search
results. Do not run `--persist`; record decisions in `docs/DESIGN.md` instead.
