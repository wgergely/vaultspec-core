---
tags:
  - "#audit"
  - "#install-cmds"
  - "#provider-capabilities"
date: "2026-03-15"
related:
  - "[[2026-03-15-install-cmds-plan]]"
  - "[[2026-03-15-claude-code-provider-research]]"
  - "[[2026-03-15-gemini-cli-provider-research]]"
  - "[[2026-03-15-codex-cli-provider-research]]"
  - "[[2026-03-16-antigravity-provider-research]]"
  - "[[2026-03-16-binding-decisions]]"
---

# install-cmds capability audit

Tracks pending tasks, deferred capabilities, and unresolved issues
discovered during the grounding research phase of the install-cmds feature.

## Grounding research status

| Provider | Research | User Approval | Truth Doc Persisted |
|----------|----------|---------------|---------------------|
| Claude Code | Done | Approved | Yes |
| Gemini CLI | Done | Approved | Yes |
| Codex CLI | Done | Approved | Yes |
| Antigravity | Done | Approved | Yes |

## Binding decisions status

All 8 binding decisions approved on 2026-03-16. Full details at
`[[2026-03-16-binding-decisions]]`.

| # | Decision | Status |
|---|----------|--------|
| 1 | Gemini config_file → `./GEMINI.md` (root) | Approved |
| 2 | Claude config_file → `./CLAUDE.md` (root) | Approved |
| 3 | Gemini skills_dir → `.agents/skills/` + shared ownership tracking | Approved |
| 4 | Gemini agents_dir stays `.gemini/agents/` | Approved |
| 5 | Antigravity ToolConfig shape confirmed | Approved |
| 6 | Codex config_file → `./AGENTS.md` + TOML adapter first-class | Approved |
| 7 | Gemini rules via `.gemini/GEMINI.md` secondary config | Approved |
| 8 | Delete `_generate_codex_agents_md()` | Approved |

## Deferred capabilities (not in current scope)

### Teams support via skills

- **Provider:** Claude Code
- **Finding:** Agent teams can be invoked as skill commands. vaultspec could
  expose `/vaultspec-start-{name}-team` skills that scaffold and launch
  pre-configured teams (e.g. review team, implementation team).
- **Why deferred:** Teams are experimental (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`).
  The install-cmds feature should declare the TEAMS capability in the enum
  but not implement sync or scaffolding for it.
- **Action:** Add `TEAMS` to `ProviderCapability` enum. Implementation in
  a future phase once teams graduate from experimental.

### Scheduled tasks

- **Provider:** Claude Code
- **Finding:** Session-scoped cron scheduling via `/loop` and CronCreate.
  No persistent file configuration — tasks are ephemeral.
- **Why deferred:** Nothing to sync or scaffold. vaultspec could create
  skill-based wrappers (e.g. `/vaultspec-watch-ci`) but this is a separate
  feature.
- **Action:** Add `SCHEDULED_TASKS` to `ProviderCapability` enum as
  informational. No install/sync support needed.

### User-level scope (all providers)

- **Finding:** All providers support user-level paths (`~/.claude/`,
  `~/.gemini/`, etc.) in addition to project-level.
- **Why deferred:** Per the plan, scope model is explicitly deferred to a
  future plan. Project-level only for install-cmds.
- **Action:** Document extension points but do not implement.

### Workflows resource type

- **Provider:** Antigravity
- **Finding:** `.agents/workflows/*.md` are user-triggered saved prompts
  invoked with `/` prefix. This is a distinct resource type from rules
  and skills.
- **Why deferred:** `Resource.WORKFLOWS` does not exist in enums.py and
  there is no sync pipeline. The directory is scaffolded but not managed.
- **Action:** Add `WORKFLOWS` to `ProviderCapability` enum. Add
  `Resource.WORKFLOWS` to enums.py. Sync pipeline deferred to future phase.

## Implementation tasks (from binding decisions)

### Must do in install-cmds feature

- [ ] Change Claude `config_file` to `TARGET_DIR / "CLAUDE.md"`
- [ ] Change Gemini `config_file` to `TARGET_DIR / "GEMINI.md"`
- [ ] Change Gemini `skills_dir` to `.agents/skills/`
- [ ] Add Codex `config_file` → `TARGET_DIR / "AGENTS.md"`
- [ ] Add `.gemini/GEMINI.md` secondary config for Gemini rule references
- [ ] Delete `_generate_codex_agents_md()` and special-case in `config_sync()`
- [ ] Implement TOML adapter for Codex rules (`[rules]` in config.toml)
- [ ] Implement TOML adapter for Codex agents (`[agents.*]` in config.toml)
- [ ] Implement `.vaultspec/providers.json` manifest for shared dir tracking
- [ ] Remove all `.agent/` (singular) references from codebase
- [ ] Add `ProviderCapability` enum with all capabilities
- [ ] Add `WORKFLOWS` to `Resource` enum in enums.py

### Resolved issues

| Issue | Resolution | Decision # |
|-------|-----------|------------|
| `.gemini/GEMINI.md` not read by Gemini CLI | Move to root `./GEMINI.md` + use `.gemini/GEMINI.md` for rule refs | 1, 7 |
| Duplicate skill loading Gemini + Antigravity | Gemini skills_dir → `.agents/skills/`, no `.gemini/skills/` | 3 |
| `_generate_codex_agents_md()` missing rule refs | Delete function, use standard `_generate_config()` | 6, 8 |
| CLAUDE.md location ambiguity | Move to root `./CLAUDE.md` | 2 |
| `.agent/` singular references | Remove all, no backward compat | User instruction |
| Shared `.agents/skills/` ownership | Provider manifest + uninstall co-dependency check | 3 |
| Codex TOML adapter | First-class work for both rules and agents | 6 |
