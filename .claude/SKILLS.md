# Project skills

Claude Code loads every folder in `.claude/skills/` for anyone working in this repo.
All skills are vendored copies from public repositories, pinned to the commits below.
They were read before adding. Licence texts are in `.claude/skills-licenses/`.

| Folder | Source (commit) | Licence | Use in NEXORA |
|---|---|---|---|
| `brainstorming`, `writing-plans`, `executing-plans`, `subagent-driven-development`, `test-driven-development`, `systematic-debugging`, `verification-before-completion`, `requesting-code-review`, `receiving-code-review`, `using-git-worktrees`, `finishing-a-development-branch`, `using-superpowers` | [obra/superpowers](https://github.com/obra/superpowers) (`22f0b46`) | MIT, © 2025 Jesse Vincent | Brainstorm → plan → build → verify → review workflow |
| `vercel-react-best-practices`, `vercel-composition-patterns`, `vercel-web-design-guidelines` | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) (`1a2c79d`), folders renamed with a `vercel-` prefix | MIT (stated in the upstream README; no LICENSE file upstream) | Next.js / React performance, component patterns, UI audits for the portal |
| `ui-ux-pro-max` | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) (`6ae86f6`) | MIT, © 2024 Next Level Builder | Design system, palettes, UX rules for the portal |
| `tob-sharp-edges`, `tob-differential-review`, `tob-supply-chain-risk-auditor`, `tob-semgrep`, `tob-modern-python`, `tob-property-based-testing` | [trailofbits/skills](https://github.com/trailofbits/skills) (`149d7b2`), folders renamed with a `tob-` prefix, `agents/openai.yaml` files removed | CC BY-SA 4.0, © Trail of Bits. Changes to these folders must stay under CC BY-SA 4.0 | Security review of auth, RBAC, tenant isolation, dependencies; Python backend conventions |
| `planning-with-files` | [OthmanAdi/planning-with-files](https://github.com/OthmanAdi/planning-with-files) (`51bf62d`), `evals/` removed | MIT, © 2026 Ahmad Adi | Plans and progress kept in files across long sessions |

## Notes from the review
- **planning-with-files** registers hooks (prompt submit, before/after tool use, stop,
  compact) that run local shell scripts in its folder. They read and write planning files
  in the project. No network access found. `session-catchup.py` can read local Claude
  session records of this project when asked to.
- **brainstorming** (Superpowers) can start a local browser companion that loads a logo
  from primeradiant.com. `.claude/settings.json` sets `SUPERPOWERS_DISABLE_TELEMETRY=1`
  to turn that off.
- **tob-supply-chain-risk-auditor** queries public package registries to score
  dependencies. That is its purpose.
- Skipped on purpose: Superpowers `writing-skills` and `diagnosing-superpowers`, Vercel
  deploy/CLI/React Native skills, UI UX Pro Max slide/banner/brand skills, Trail of Bits
  smart-contract, binary and C/C++/Rust skills.

## Updating
Re-copy the folder from a newer upstream commit, review the diff, then update the commit
in this table.
