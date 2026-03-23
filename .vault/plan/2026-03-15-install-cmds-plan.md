---
tags:
  - '#plan'
  - '#install-cmds'
date: '2026-03-15'
related:
  - '[[2026-03-16-managed-content-blocks-adr]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `install-cmds` implementation plan

Harden the `install`/`uninstall` CLI commands and justfile recipes with
proper provider targeting, dry-run support, and a formalized provider
capability model. This plan supersedes the initial `install`/`uninstall`
implementation on `feature/codex` (commit `56bbeb0`) which lacks provider
scoping, dry-run, and capability declarations.

## Motivation

The current implementation has three structural gaps:

1. **No ProviderCapability enum.** Provider capabilities are implicitly
   encoded as `None` vs set fields in `ToolConfig`. There is no
   centralized declaration of what each provider supports. The sync
   engine, install command, and dry-run output all need to reason about
   capabilities, so this must be formalized.

1. **No scope model.** The install/sync pipeline assumes project-level
   deployment only. User-level directories (`~/.gemini/`, `~/.claude/`,
   `~/.agents/`) are completely absent. This plan scopes the work to
   project-level only but defines the extension point for user-level
   scope in a future phase.

1. **Root config file locations are unverified.** The current code has
   Gemini writing to `.gemini/GEMINI.md` and Antigravity writing to
   `PROJECT_ROOT/GEMINI.md`. Official Gemini CLI docs say it reads
   `GEMINI.md` via upward directory traversal from cwd to `.git`
   boundary. Each provider's expected config location must be
   verified against official documentation before implementation.

## Prerequisite: grounding research phase

Before any code changes, each provider's official documentation must
be consulted to establish the correct file locations. The research
must answer these questions for each provider and produce a binding
reference table that the user explicitly approves.

### Per-provider research checklist

For **each** of Claude, Gemini CLI, Antigravity (.agents/), and Codex:

- [ ] Where does the tool read its root config file from?
  (project root? inside .tool/? hierarchical scan?)

- [ ] Where does the tool read rules from?

- [ ] Where does the tool read skills from?

- [ ] Where does the tool read agent definitions from?

- [ ] Does the tool support system prompt overrides? Where?

- [ ] Does the tool support hooks? Where?

- [ ] What is the relationship between `.agents/` and `.gemini/`?
  (alias? precedence? independent?)

- [ ] What is the correct root config filename?
  (CLAUDE.md, GEMINI.md, AGENTS.md, or something else?)

### Binding decisions requiring user approval

The following decisions MUST be presented to the user with research
evidence and approved interactively before implementation:

1. Root config file location for each provider
1. Whether Antigravity's root config should be GEMINI.md or AGENTS.md
1. Whether `.gemini/GEMINI.md` is a valid read location for Gemini CLI
1. The relationship model between Antigravity and Gemini providers
1. Whether Codex should own AGENTS.md exclusively

**IMPORTANT:** Do not assume answers. Present findings with source
links and ask the user to confirm each binding decision.

## Phase 1: ProviderCapability enum

### 1.1 Define the enum

Add to `src/vaultspec_core/core/enums.py`:

```python
class ProviderCapability(StrEnum):
    """Capabilities a provider can declare support for."""
    RULES = "rules"
    SKILLS = "skills"
    AGENTS = "agents"
    ROOT_CONFIG = "root_config"
    SYSTEM = "system"
    HOOKS = "hooks"
```

### 1.2 Add capabilities to ToolConfig

Extend `ToolConfig` with a `capabilities` field:

```python
capabilities: frozenset[ProviderCapability] = frozenset()
```

### 1.3 Populate capabilities during init_paths()

Each provider's capabilities are derived from its ToolConfig fields
but declared explicitly. Example:

```python
Tool.CLAUDE: ToolConfig(
    capabilities=frozenset({
        ProviderCapability.RULES,
        ProviderCapability.SKILLS,
        ProviderCapability.AGENTS,
        ProviderCapability.ROOT_CONFIG,
        ProviderCapability.SYSTEM,
    }),
    ...
)
```

### 1.4 Research needed

- [ ] Confirm which capabilities each provider actually supports
  (this depends on the grounding research phase)

- [ ] Determine whether HOOKS is per-provider or remains global-only

- [ ] Determine whether RULES should be universal or opt-in

### 1.5 Tests

- Contract test: every Tool enum member has a ToolConfig with
  non-empty capabilities

- Each capability in the enum maps to at least one provider

- Capability set is consistent with ToolConfig fields (e.g. if
  RULES is declared, rules_dir must not be None)

## Phase 2: Revise install command

### 2.1 New CLI signature

```
vaultspec-core install <path> [provider] [--upgrade] [--dry-run]
```

Where `provider` is one of: `all`, `core`, `claude`, `gemini`,
`codex`, `antigravity`.

- `all` (default): scaffold `.vaultspec/` + `.vault/` + all providers
- `core`: scaffold `.vaultspec/` + `.vault/` only, zero providers
- `<provider>`: scaffold `.vaultspec/` + `.vault/` + specific provider

### 2.2 --dry-run implementation

Dry-run must produce an exact manifest of files and directories that
would be created or updated. This requires the capability matrix to
map provider + capability to concrete file paths.

Example output for `install . gemini --dry-run`:

```
Would create:
  .vaultspec/rules/rules/
  .vaultspec/rules/skills/
  .vaultspec/rules/agents/
  .vaultspec/rules/system/
  .vaultspec/rules/templates/
  .vault/adr/
  .vault/audit/
  ...
  .gemini/rules/
  .gemini/skills/
  .gemini/agents/
  GEMINI.md          (root config)
  .gemini/SYSTEM.md  (system prompt)
```

### 2.3 --upgrade behavior

- Re-sync `.vaultspec/` builtin content (\*.builtin.md files only)
- Re-sync framework.md and project.md stubs (only if missing)
- Call `sync <provider>` to update synced destinations
- **Never** overwrite custom user rules/skills/agents
- **Never** remove existing files

### 2.4 Justfile recipe

```
install path='.' provider='all' *args='':
  uv run vaultspec-core install "{{path}}" {{provider}} {{args}}
```

### 2.5 Tests

- `install . core --dry-run` lists only .vaultspec/ and .vault/
- `install . claude --dry-run` lists .vaultspec/ + .vault/ + .claude/
- `install . --upgrade` does not remove custom rules
- `install .` without args installs all providers
- `install . gemini` does not create .claude/ directories

## Phase 3: Revise uninstall command

### 3.1 New CLI signature

```
vaultspec-core uninstall <path> [provider] [--keep-vault] [--dry-run]
```

Where `provider` scoping works as:

- `all` (default): remove everything
- `core`: remove .vaultspec/ only (leave providers intact)
- `<provider>`: remove only that provider's directories and config

### 3.2 --dry-run for uninstall

Lists exactly which files/directories would be removed.

### 3.3 Justfile recipe

```
uninstall path='.' provider='all' *args='':
  uv run vaultspec-core uninstall "{{path}}" {{provider}} {{args}}
```

## Phase 4: Revise sync command

### 4.1 Sync uses ProviderCapability

The sync command should use the capability enum to determine what
to sync for each provider, rather than relying on None-checking
ToolConfig fields.

### 4.2 Provider validation

When `sync <provider>` is called, validate that the provider's
directories exist (i.e. it was installed). If not, emit a clear
error: "Provider 'claude' is not installed. Run
'vaultspec-core install . claude' first."

## Phase 5: Scope model (project vs user) — DEFERRED

This phase is explicitly deferred to a future plan. Document the
extension points but do not implement.

### 5.1 What scope means

- **Project scope** (current): rules/configs synced to `./<provider>/`
  within the git repository

- **User scope** (future): rules/configs synced to `~/.<provider>/`
  in the user's home directory

### 5.2 Complexity assessment

User-level scope introduces:

- Platform-specific home directory resolution (Windows, macOS, Linux)
- XDG compliance on Linux vs hardcoded paths
- Conflict resolution between project and user rules
- Precedence model (project overrides user, or merge?)
- Different rule sets per scope (some rules are personal, some shared)
- Testing with isolated home directories

This is a significant architectural rework and should not be
bundled with the install-cmds feature.

### 5.3 Extension point

The `ProviderCapability` enum and scoped install command provide
the foundation. A future `--scope project|user` flag on install
and sync can be added without breaking the project-level API.

## Conflicts and overlaps to resolve

### Known overlap: .agents/skills/

Both Antigravity and Codex write to `.agents/skills/`. Content is
identical (same source). However:

- Pruning by one provider could remove files expected by the other

- `uninstall codex` should not remove `.agents/skills/` if
  Antigravity is still installed

- `uninstall antigravity` should not remove `.agents/skills/` if
  Codex is still installed

**Resolution:** Track which providers are installed (e.g. via a
`.vaultspec/providers.json` manifest) so uninstall can check for
co-dependencies before removing shared directories.

### Known conflict: root config file ownership

- Antigravity currently writes `PROJECT_ROOT/GEMINI.md`
- Codex writes `PROJECT_ROOT/AGENTS.md`
- If Gemini's root config should also be at project root, it
  conflicts with Antigravity's GEMINI.md

**Resolution:** Determined by grounding research phase. The
binding decisions must be approved by the user.

### Known gap: .gemini/GEMINI.md vs PROJECT_ROOT/GEMINI.md

Gemini CLI reads GEMINI.md via upward traversal from cwd. It does
NOT specifically look inside `.gemini/` for GEMINI.md. The current
Gemini provider writes to `.gemini/GEMINI.md` which may be invisible
to the Gemini CLI depending on working directory.

**Resolution:** Determined by grounding research phase.

## Files to modify

1. `src/vaultspec_core/core/enums.py` — add ProviderCapability enum

1. `src/vaultspec_core/core/types.py` — add capabilities to ToolConfig,
   populate in init_paths()

1. `src/vaultspec_core/core/commands.py` — revise install_run,
   uninstall_run with provider targeting and dry-run

1. `src/vaultspec_core/spec_cli.py` — update CLI signatures for
   install, uninstall, sync

1. `src/vaultspec_core/cli.py` — update command registration

1. `justfile` — update install/uninstall recipes

1. `tests/test_automation_contracts.py` — update contracts

1. `src/vaultspec_core/tests/cli/test_spec_cli.py` — new tests

## Verification

1. `uv run pytest tests src -v` — all tests pass
1. `just install . core --dry-run` — lists only framework dirs
1. `just install . claude --dry-run` — lists framework + claude dirs
1. `just install . --upgrade --dry-run` — shows what would be updated
1. `just uninstall . claude --dry-run` — lists only claude artifacts
1. `vaultspec-core sync claude` — syncs only claude provider
1. `vaultspec-core sync antigravity` — syncs only antigravity
1. CI passes on all 6 jobs

## Implementation order

1. Grounding research (blocking — requires user approval)
1. Phase 1: ProviderCapability enum
1. Phase 2: Revise install command
1. Phase 3: Revise uninstall command
1. Phase 4: Revise sync command
1. Update automation contracts and tests
1. CI verification
