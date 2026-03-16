---
tags:
  - "#research"
  - "#install-cmds"
  - "#binding-decisions"
date: "2026-03-16"
related:
  - "[[2026-03-15-install-cmds-plan]]"
  - "[[2026-03-15-install-cmds-capability-audit]]"
  - "[[2026-03-15-claude-code-provider-research]]"
  - "[[2026-03-15-gemini-cli-provider-research]]"
  - "[[2026-03-15-codex-cli-provider-research]]"
  - "[[2026-03-16-antigravity-provider-research]]"
---

# Binding decisions for install-cmds feature

All decisions approved by user during grounding research phase on
2026-03-16. These are authoritative and override any prior assumptions
in the codebase or plan documents.

## Decision 1: GEMINI.md location for Gemini provider — APPROVED

Change Gemini `config_file` from `.gemini/GEMINI.md` to `./GEMINI.md`
(project root). Both Gemini CLI and Antigravity read from project root.
Shared file, identical content.

## Decision 2: CLAUDE.md location for Claude provider — APPROVED

Change Claude `config_file` from `.claude/CLAUDE.md` to `./CLAUDE.md`
(project root). Consistent with Gemini and Codex. All three root configs
at project root:

| Provider | Root Config |
|----------|------------|
| Claude | `./CLAUDE.md` |
| Gemini + Antigravity | `./GEMINI.md` |
| Codex | `./AGENTS.md` |

## Decision 3: Gemini skills_dir → `.agents/skills/` with shared ownership — APPROVED

Gemini `ToolConfig.skills_dir` → `.agents/skills/`. No `.gemini/skills/`
created. `.agents/skills/` is co-owned by Gemini, Antigravity, and Codex.

Shared ownership constraint: uninstall MUST check whether any remaining
installed provider still references `.agents/skills/` before removing or
pruning. Requires `.vaultspec/providers.json` manifest to track
co-dependencies.

## Decision 4: Gemini agents_dir stays at `.gemini/agents/` — APPROVED

No change. `.gemini/agents/*.md` is the correct native path per Gemini
CLI docs. No `.agents/agents/` alias exists. Gemini-only, no shared
ownership concern.

## Decision 5: Antigravity ToolConfig shape confirmed — APPROVED

Current shape is correct:
- `rules_dir` → `.agents/rules/`
- `skills_dir` → `.agents/skills/`
- `agents_dir` → `None`
- `config_file` → `TARGET_DIR / GEMINI.md` (shared with Gemini)
- `system_file` → `None`
- `emit_system_rule` → `False`

`.agents/workflows/` scaffolded but not synced (deferred capability).

## Decision 6: Codex ToolConfig, AGENTS.md unification, TOML adapter — APPROVED

1. Add `config_file` → `TARGET_DIR / "AGENTS.md"` to Codex ToolConfig
2. Remove `_generate_codex_agents_md()` — use standard `_generate_config()`
3. Keep `native_config_file` → `.codex/config.toml`
4. TOML adapter for BOTH rules AND agents is **first-class work** (not
   deferred):
   - Read/write `[rules]` section in `.codex/config.toml`
   - Read/write `[agents.*]` tables in `.codex/config.toml`
   - Without clobbering other settings
   - Implementation in Phase 4 (sync revision)

## Decision 7: Gemini rules via `.gemini/GEMINI.md` secondary config — APPROVED

Keep `rules_dir` → `.gemini/rules/` and use `.gemini/GEMINI.md` as a
secondary config file carrying `@rules/...` references.

Architecture:
- `./GEMINI.md` (project root) = framework + project content, shared
  with Antigravity
- `.gemini/GEMINI.md` = Gemini-specific rule references
- `.gemini/rules/*.md` = synced markdown rule files

Gemini CLI eagerly scans subdirectories at startup, so `.gemini/GEMINI.md`
is reliably discovered and concatenated with root `GEMINI.md`.
Antigravity does not read `.gemini/GEMINI.md` — clean separation.

## Decision 8: Delete `_generate_codex_agents_md()` — APPROVED

Remove the separate function and special-case code in `config_sync()`.
Once Codex `ToolConfig.config_file` is set (Decision 6), the standard
`_generate_config()` pipeline handles AGENTS.md with rule references
included automatically.

## Summary: final ToolConfig shapes

### Claude
| Field | Value |
|-------|-------|
| config_file | `TARGET_DIR / "CLAUDE.md"` |
| rules_dir | `.claude/rules/` |
| skills_dir | `.claude/skills/` |
| agents_dir | `.claude/agents/` |
| system_file | None |

### Gemini
| Field | Value |
|-------|-------|
| config_file | `TARGET_DIR / "GEMINI.md"` |
| rules_dir | `.gemini/rules/` |
| skills_dir | `.agents/skills/` |
| agents_dir | `.gemini/agents/` |
| system_file | `.gemini/system.md` |
| secondary config | `.gemini/GEMINI.md` (rule refs) |

### Antigravity
| Field | Value |
|-------|-------|
| config_file | `TARGET_DIR / "GEMINI.md"` |
| rules_dir | `.agents/rules/` |
| skills_dir | `.agents/skills/` |
| agents_dir | None |
| system_file | None |

### Codex
| Field | Value |
|-------|-------|
| config_file | `TARGET_DIR / "AGENTS.md"` |
| native_config_file | `.codex/config.toml` |
| rules_dir | None (TOML adapter, first-class) |
| skills_dir | `.agents/skills/` |
| agents_dir | None (TOML adapter, first-class) |
| system_file | None |
