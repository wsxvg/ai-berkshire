# AI Berkshire Codex Guide

This repository contains investment research workflows, reports, and shared
validation tools. Keep compatibility with both Claude Code and Codex users.

## Project Layout

- `skills/*.md`: Claude Code slash-command source files.
- `codex-skills/*/SKILL.md`: Codex skill packages. Most are generated from
  `skills/*.md`; Codex-only hand-written packages are allowed when clearly
  marked and no same-named `skills/*.md` source exists.
- `codex-prompts/*.md`: generated Codex custom prompts for slash-command
  style entry points. These are a compatibility layer; skills remain preferred.
- `tools/*.py`: shared financial validation and data tools used by both systems.
- `reports/`: research outputs. Do not rewrite unrelated reports while changing
  tooling or skills.
- `scripts/sync-codex-skills.py`: regenerates Codex skills from `skills/*.md`.
- `scripts/install-codex-skills.sh`: installs Codex skills locally.
- `scripts/install-codex-prompts.sh`: installs generated Codex slash prompts
  locally.
- `scripts/install-claude-commands.sh`: installs Claude Code commands locally.
- `opencode-skills/*/SKILL.md`: OpenCode skill packages, generated from
  `skills/*.md` via `scripts/sync-opencode-skills.py`.
- `scripts/sync-opencode-skills.py`: generates OpenCode skills from
  `skills/*.md` into `opencode-skills/`.
- `scripts/install-opencode-skills.sh`: installs OpenCode skills (macOS/Linux).
- `scripts/install-opencode-skills.ps1`: installs OpenCode skills (Windows).

## Compatibility Rules

- Treat `skills/*.md` as the canonical workflow source.
- After changing any file in `skills/`, run:
  `python3 scripts/sync-codex-skills.py` and
  `python3 scripts/sync-opencode-skills.py`
- If slash prompt compatibility is needed, also run:
  `python3 scripts/sync-codex-prompts.py`
- Do not manually edit generated `codex-skills/*/SKILL.md` or
  `opencode-skills/*/SKILL.md` unless also updating the corresponding source in
  `skills/`.
- For Codex-only hand-written packages under `codex-skills/`, keep them clearly
  marked as Codex-only and do not create a same-named `skills/*.md` file unless
  intentionally adopting the workflow for Claude Code too.
- Keep tool paths compatible with the documented checkout path:
  `~/ai-berkshire/tools/...`
- Keep `CLAUDE.md` for Claude Code behavior and this `AGENTS.md` for Codex
  behavior.

## Research Quality Rules

- Financial data must come from at least two independent sources when the skill
  requires verification.
- Use exact arithmetic tools for market cap, valuation, cross-source checks, and
  scenario analysis:
  `python3 tools/financial_rigor.py ...`
- Use report audit tooling before treating generated research as publishable:
  `python3 tools/report_audit.py ...`
- Clearly label low-confidence conclusions, incomplete data, and source gaps.
- This project is for learning and research, not investment advice.

## Editing Rules

- Preserve existing report files unless the task specifically asks to change
  them.
- Keep changes scoped to the requested skill, tool, script, or documentation.
- Before finishing a skill/tool change, run the relevant syntax or generation
  check. For compatibility changes, run:
  `python3 scripts/sync-codex-skills.py`

## Code Knowledge Graph (codebase-memory MCP)

This repo has a pre-built code knowledge graph. Prefer it for code navigation
instead of blindly reading files or grepping the whole tree.

- MCP server: `codebase-memory`
- Project name to query: **`X`** (the graph was indexed via the `X:` drive
  mapping, so all node paths look like `X:/...`)
- Tools to use:
  - `search_graph` — find functions / classes / variables by name
  - `query_graph` — Cypher queries for call relations, dependencies, complexity
  - `get_code_snippet` — pull a specific implementation snippet
  - `get_architecture` — whole-repo tree / architecture overview
  - `impact` / `affected` — blast radius of editing a file
- Why `X:` instead of the real path: the tool's symbol extractor fails on the
  Chinese path `c:/项目/A基金/基金`. Work around it with a drive mapping:
  `subst X: "c:\项目\A基金\基金"` before indexing.
- To refresh the index (it does NOT auto-update): make sure `X:` exists, then
  `index_repository(repo_path="X:/", mode="full")`.
- Caveats the AI must respect:
  - `subst X:` is lost after a reboot; it only affects re-indexing, not queries.
  - The graph is a periodically refreshed map, not a live mirror. For exact
    function bodies, fall back to `get_code_snippet` / `read` on that one file.
  - The graph complements reading; it tells you *where* to look, not the full
    file contents.
