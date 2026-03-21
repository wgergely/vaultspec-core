---
tags:
  - '#plan'
  - '#install-cmds'
date: '2026-03-16'
related:
  - '[[2026-03-15-install-cmds-plan]]'
  - '[[2026-03-16-binding-decisions]]'
  - '[[2026-03-15-install-cmds-capability-audit]]'
  - '[[2026-03-16-managed-content-blocks-adr]]'
---

# install-cmds execution plan

## Context

The `install`/`uninstall` CLI commands on `feature/install-cmds` branch
(commit `66bddc8`) are a working but naive first pass lacking provider
scoping, dry-run on install, capability declarations, and correct
provider file locations. A grounding research phase verified each
provider's official documentation and produced 8 user-approved binding
decisions that must now be implemented.

**Problem:** The current ToolConfig mappings have incorrect file locations
(`.gemini/GEMINI.md` is never read by Gemini CLI), missing capabilities
(no ProviderCapability enum), and a special-cased AGENTS.md generation
path that skips rule references. The install/uninstall commands lack
provider targeting and dry-run support.

**Outcome:** A hardened install/uninstall/sync surface with correct
provider file locations, a formalized capability model, provider-scoped
operations, dry-run manifests, shared directory ownership tracking, and
a TOML adapter for Codex agent definitions.

### Reference documents

- Plan: `.vault/plan/2026-03-15-install-cmds-plan.md`
- Audit: `.vault/audit/2026-03-15-install-cmds-capability-audit.md`
- Binding decisions: `.vault/research/2026-03-16-binding-decisions.md`
- Claude research: `.vault/research/2026-03-15-claude-code-provider-research.md`
- Gemini research: `.vault/research/2026-03-15-gemini-cli-provider-research.md`
- Codex research: `.vault/research/2026-03-15-codex-cli-provider-research.md`
- Antigravity research: `.vault/research/2026-03-16-antigravity-provider-research.md`
- Prior codex ADR: `.vault/adr/2026-03-11-codex-integration-adr.md`

______________________________________________________________________

## Phase 1: ProviderCapability enum and Resource additions

### Files to modify

- `src/vaultspec_core/core/enums.py`

### Tasks

- [ ] 1.1 Add `ProviderCapability(StrEnum)` with values:
  `RULES`, `SKILLS`, `AGENTS`, `ROOT_CONFIG`, `SYSTEM`, `HOOKS`,
  `TEAMS`, `SCHEDULED_TASKS`, `WORKFLOWS`

- [ ] 1.2 Add `WORKFLOWS = "workflows"` to `Resource(StrEnum)`

### Notes

- `TEAMS`, `SCHEDULED_TASKS`, `WORKFLOWS` are declared for completeness
  but not actively used by install/sync in this feature. They formalize
  the capability model for future phases.

______________________________________________________________________

## Phase 2: ToolConfig and init_paths() revision

### Files to modify

- `src/vaultspec_core/core/types.py`

### Tasks

- [ ] 2.1 Add `capabilities: frozenset[ProviderCapability]` field to
  `ToolConfig` dataclass (default `frozenset()`)

- [ ] 2.2 Revise `init_paths()` TOOL_CONFIGS per binding decisions:

  **Claude** (Decision 2):

  - `config_file` → `target / FileName.CLAUDE.value` (project root)
  - `rules_dir` → `.claude/rules/` (unchanged)
  - `skills_dir` → `.claude/skills/` (unchanged)
  - `agents_dir` → `.claude/agents/` (unchanged)
  - `capabilities` → `{RULES, SKILLS, AGENTS, ROOT_CONFIG, HOOKS, TEAMS, SCHEDULED_TASKS}`

  **Gemini** (Decisions 1, 3, 4, 7):

  - `config_file` → `target / FileName.GEMINI.value` (project root)
  - `rules_dir` → `.gemini/rules/` (unchanged)
  - `skills_dir` → `target / DirName.ANTIGRAVITY.value / Resource.SKILLS.value` (`.agents/skills/`)
  - `agents_dir` → `.gemini/agents/` (unchanged, Decision 4)
  - `system_file` → `.gemini/SYSTEM.md` (unchanged)
  - Add secondary config concept for `.gemini/GEMINI.md` rule refs (new field or handled in config_gen)
  - `capabilities` → `{RULES, SKILLS, AGENTS, ROOT_CONFIG, SYSTEM, HOOKS}`

  **Antigravity** (Decision 5):

  - No changes to current shape (confirmed correct)
  - `capabilities` → `{RULES, SKILLS, ROOT_CONFIG, WORKFLOWS}`

  **Codex** (Decision 6):

  - `config_file` → `target / FileName.AGENTS.value` (project root)
  - `native_config_file` → `.codex/config.toml` (unchanged)
  - `skills_dir` → `.agents/skills/` (unchanged)
  - `capabilities` → `{RULES, SKILLS, AGENTS, ROOT_CONFIG}`

- [ ] 2.3 Add `rule_ref_config_file: Path | None` field to ToolConfig
  for Gemini's secondary `.gemini/GEMINI.md` that carries `@rules/...`
  references (or handle in config_gen.py — design choice during impl)

______________________________________________________________________

## Phase 3: config_gen.py revision

### Files to modify

- `src/vaultspec_core/core/config_gen.py`

### Tasks

- [ ] 3.1 Delete `_generate_codex_agents_md()` function (Decision 8)

- [ ] 3.2 Remove special-case AGENTS.md code in `config_sync()`
  (lines ~298-307) — the standard TOOL_CONFIGS loop now handles it
  since Codex has `config_file` set

- [ ] 3.3 Implement `.gemini/GEMINI.md` secondary config generation
  (Decision 7): generate a file at `.gemini/GEMINI.md` containing
  `@rules/...` references for Gemini CLI's subdirectory discovery.
  This is separate from the root `./GEMINI.md` shared with Antigravity.

- [ ] 3.4 Implement TOML adapter for Codex agents in `config.toml`:

  - Write `[agents.<name>]` sub-tables into config.toml

  - Must preserve all other settings in the file

  - config.toml schema rejects unknown top-level keys
    (`additionalProperties: false`) — cannot add `[vaultspec]` namespace

  - Use managed block markers to delimit vaultspec-managed agents

  - Codex behavioral rules are delivered via AGENTS.md rule references
    (same mechanism as Claude/Gemini) — no separate rules adapter needed

- [ ] 3.5 Wire TOML agent adapter into `config_sync()` for Codex

______________________________________________________________________

## Phase 4: Provider manifest (providers.json)

### Files to modify

- `src/vaultspec_core/core/types.py` (or new module)
- `src/vaultspec_core/core/commands.py`

### Tasks

- [ ] 4.1 Define provider manifest schema at `.vaultspec/providers.json`:

  ```json
  {
    "installed": ["claude", "gemini", "antigravity", "codex"],
    "version": "1.0"
  }
  ```

- [ ] 4.2 Write manifest on install, update on provider add/remove

- [ ] 4.3 Read manifest in uninstall to check shared directory
  co-dependencies before removing `.agents/skills/`, `.agents/rules/`,
  etc.

______________________________________________________________________

## Phase 5: Revise install command

### Files to modify

- `src/vaultspec_core/core/commands.py`
- `src/vaultspec_core/spec_cli.py`

### Tasks

- [ ] 5.1 Change CLI signature to positional provider argument:

  ```
  vaultspec-core install <path> [provider] [--upgrade] [--dry-run]
  ```

  Where `provider` is: `all` (default), `core`, `claude`, `gemini`,
  `codex`, `antigravity`

- [ ] 5.2 Implement `core` provider option: scaffolds `.vaultspec/` +
  `.vault/` only, zero provider directories

- [ ] 5.3 Implement `--dry-run` for install: produce exact manifest of
  files/directories that would be created using ProviderCapability
  to map provider + capability to concrete paths

- [ ] 5.4 Revise `init_run()` scaffolding to use ProviderCapability:

  - Only scaffold directories for capabilities the provider declares
  - Scaffold `.agents/skills/` for any provider with SKILLS capability
  - Scaffold `.gemini/agents/` only for Gemini
  - Scaffold `.agents/rules/` only for Antigravity
  - Scaffold `.agents/workflows/` only for Antigravity
  - Scaffold `.codex/config.toml` only for Codex

- [ ] 5.5 Write providers.json manifest on install (Phase 4)

- [ ] 5.6 Implement `--upgrade` behavior:

  - Re-sync `.vaultspec/` builtin content (`*.builtin.md` only)
  - Re-sync framework.md and project.md stubs (only if missing)
  - Call `sync <provider>` to update synced destinations
  - Never overwrite custom user rules/skills/agents
  - Never remove existing files

______________________________________________________________________

## Phase 6: Revise uninstall command

### Files to modify

- `src/vaultspec_core/core/commands.py`
- `src/vaultspec_core/spec_cli.py`

### Tasks

- [ ] 6.1 Change CLI signature to positional provider argument:

  ```
  vaultspec-core uninstall <path> [provider] [--keep-vault] [--dry-run]
  ```

  Where `provider` is: `all` (default), `core`, `claude`, `gemini`,
  `codex`, `antigravity`

- [ ] 6.2 Implement provider-scoped uninstall:

  - `all`: remove everything (current behavior)
  - `core`: remove `.vaultspec/` only
  - `<provider>`: remove only that provider's directories and config

- [ ] 6.3 Implement shared directory protection:

  - Read providers.json to check co-dependencies

  - If uninstalling Antigravity but Gemini/Codex remain → preserve
    `.agents/skills/`

  - If uninstalling Gemini but Antigravity remains → preserve
    `./GEMINI.md`

- [ ] 6.4 Update providers.json on uninstall (remove provider from list)

- [ ] 6.5 `--dry-run` lists exactly which files/directories would be
  removed (existing partial impl, extend with provider scoping)

______________________________________________________________________

## Phase 7: Revise sync command

### Files to modify

- `src/vaultspec_core/spec_cli.py`

### Tasks

- [ ] 7.1 Sync uses ProviderCapability to determine what to sync per
  provider instead of None-checking ToolConfig fields

- [ ] 7.2 Provider validation: when `sync <provider>` is called, check
  providers.json to verify provider is installed. If not, emit:
  `"Provider 'X' is not installed. Run 'vaultspec-core install . X' first."`

- [ ] 7.3 Wire TOML adapter (Phase 3.4) into per-provider sync for Codex

______________________________________________________________________

## Phase 8: Justfile and CLI registration

### Files to modify

- `justfile`
- `src/vaultspec_core/cli.py`

### Tasks

- [ ] 8.1 Update justfile install recipe:

  ```just
  install path='.' provider='all' *args='':
    uv run vaultspec-core install "{{path}}" {{provider}} {{args}}
  ```

- [ ] 8.2 Update justfile uninstall recipe:

```just
  uninstall path='.' provider='all' *args='':
    uv run vaultspec-core uninstall "{{path}}" {{provider}} {{args}}
```

- [ ] 8.3 Verify CLI registration in cli.py (likely no changes needed)

______________________________________________________________________

## Phase 9: Tests and contracts

### Files to modify

- `tests/test_automation_contracts.py`
- `src/vaultspec_core/tests/cli/test_spec_cli.py` (new tests)
- `tests/test_commands.py` (update existing)

### Tasks

- [ ] 9.1 Contract test: every `Tool` enum member has a `ToolConfig`
  with non-empty `capabilities`

- [ ] 9.2 Contract test: each `ProviderCapability` value maps to at
  least one provider

- [ ] 9.3 Contract test: capability set is consistent with ToolConfig
  fields (if RULES declared, rules_dir must not be None OR provider
  has rules delivered via root config references)

- [ ] 9.4 Test `install . core --dry-run` lists only `.vaultspec/` and
  `.vault/`

- [ ] 9.5 Test `install . claude --dry-run` lists `.vaultspec/` +
  `.vault/` + `.claude/` + `CLAUDE.md`

- [ ] 9.6 Test `install . gemini --dry-run` includes `.gemini/` +
  `.agents/skills/` + `GEMINI.md` + `.gemini/GEMINI.md`

- [ ] 9.7 Test `install . --upgrade` does not remove custom rules

- [ ] 9.8 Test `install .` without args installs all providers

- [ ] 9.9 Test `install . gemini` does NOT create `.claude/`

- [ ] 9.10 Test `uninstall . claude --dry-run` lists only Claude artifacts

- [ ] 9.11 Test uninstall shared dir protection: uninstall antigravity
  with gemini still installed → `.agents/skills/` preserved

- [ ] 9.12 Test providers.json is written on install and updated on
  uninstall

- [ ] 9.13 Test AGENTS.md gets rule references (via standard pipeline)

- [ ] 9.14 Test `.gemini/GEMINI.md` secondary config contains rule refs

- [ ] 9.15 Test AGENTS.md includes rule references for Codex

- [ ] 9.16 Test TOML adapter writes agents to `.codex/config.toml`

- [ ] 9.17 Update justfile contract tests for new recipe signatures

______________________________________________________________________

## Verification

1. `uv run pytest tests src -v` — all tests pass
1. `just install . core --dry-run` — lists only framework dirs
1. `just install . claude --dry-run` — lists framework + claude dirs
1. `just install . --upgrade --dry-run` — shows what would be updated
1. `just uninstall . claude --dry-run` — lists only claude artifacts
1. `vaultspec-core sync claude` — syncs only claude provider
1. `vaultspec-core sync codex` — syncs codex including AGENTS.md rules + TOML agents
1. Root config files at project root: `CLAUDE.md`, `GEMINI.md`, `AGENTS.md`
1. `.gemini/GEMINI.md` contains rule references
1. `.codex/config.toml` contains `[agents.*]` sections
1. CI passes on all 6 jobs
