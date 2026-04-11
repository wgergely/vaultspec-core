---
tags:
  - '#research'
  - '#mcp-registry'
date: '2026-04-11'
related:
  - '[[2026-03-28-mcp-installation-patterns-research]]'
  - '[[2026-02-22-mcp-consolidation-research]]'
  - '[[2026-02-22-mcp-consolidation-adr]]'
---

# `mcp-registry` research: built-in MCP definitions with install/sync/uninstall lifecycle

Researched the internal architecture of vaultspec-core's resource management
pipeline to determine the optimal design for an MCP server registry that
mirrors the existing rule/skill/agent registry pattern. This registry will
allow built-in and custom MCP server definitions to be programmatically
managed and synced to `.mcp.json`.

## Findings

### 1. Existing resource registry architecture

All resource types (rules, skills, agents) follow the same pipeline:

- **Source directory**: `.vaultspec/rules/{resource}/` stores canonical
  definitions
- **Collection**: `collect_{resource}()` gathers source files via
  `collect_md_resources()` (Markdown with YAML frontmatter)
- **Transform**: `transform_{resource}()` adapts content for each tool
  destination
- **Sync**: `{resource}_sync()` calls `sync_to_all_tools()` to distribute
  to per-tool directories
- **CLI**: `spec {resource} list|add|remove|sync` via Typer sub-groups
- **Public API**: re-exported from `core/__init__.py`
- **Built-in naming**: `*.builtin.md` suffix distinguishes bundled from
  custom definitions

The `sync_to_all_tools()` function iterates over `installed_tool_configs()`
and writes transformed content to per-tool destination directories
(`.claude/rules/`, `.gemini/rules/`, etc.).

### 2. MCP definitions diverge from the MD pattern

MCP server definitions are inherently JSON structures matching the
`.mcp.json` schema:

```json
{
  "command": "uv",
  "args": ["run", "python", "-m", "vaultspec_core.mcp_server.app"]
}
```

Key differences from rules/skills/agents:

- **Format**: JSON, not Markdown with frontmatter
- **Destination**: Single `.mcp.json` file, not per-tool directories
- **Transform**: No per-tool adaptation needed - `.mcp.json` is
  provider-agnostic
- **Merge semantics**: JSON key-level merge into `mcpServers` dict, not
  file-level copy

This means `sync_to_all_tools()` is NOT the right abstraction. MCP sync
needs its own pipeline: collect JSON definitions from source, merge into
the single `.mcp.json` destination.

### 3. Source storage convention

MCP definitions should live in `.vaultspec/rules/mcps/` as individual JSON
files. Each file defines one MCP server:

- Filename (minus extension) = server name in `.mcp.json`
- `.builtin.json` suffix for built-in definitions
- `.json` suffix for custom definitions
- File content = the server configuration object

Example: `.vaultspec/rules/mcps/vaultspec-core.builtin.json` contains the
server entry that gets merged as `mcpServers["vaultspec-core"]`.

This is consistent with the existing directory structure under
`.vaultspec/rules/` and will be automatically bundled by the existing
`force-include` in `pyproject.toml`:
`".vaultspec/rules" = "vaultspec_core/builtins"`.

### 4. Current MCP handling across the install/sync/uninstall lifecycle

MCP management currently uses three hardcoded touchpoints, all operating
on a single `vaultspec-core` server entry:

**Install (`init_run()`, line 427)**:
After core scaffolding and builtin seeding, calls `_scaffold_mcp_json()`
as a standalone step gated by `"mcp" not in skip`. This is provider-
agnostic - it runs regardless of which provider is being installed.
The MCP entry is not tracked in the provider manifest; it has no
provider ownership.

**Sync (`sync_provider()`, line 1269)**:
After running all resource syncs (rules, skills, agents, system, config),
calls `_scaffold_mcp_json()` as a "repair" step - it re-ensures the
hardcoded entry exists. Again gated by `"mcp" not in skip`. This means
`vaultspec-core sync` silently repairs a missing `.mcp.json` entry
every time.

**Upgrade (`install_upgrade()`, line 664)**:
Calls `sync_provider()` which triggers the repair step above.
Source counts are gathered for rules/skills/agents but not for MCPs.

**Uninstall (`uninstall_run()`, line 901)**:
Surgical cleanup removes only `mcpServers["vaultspec-core"]` from
`.mcp.json`. If no servers remain, deletes the file entirely.
Gated by `"mcp" not in skip`.

**Key implication**: The registry replaces all three hardcoded
`_scaffold_mcp_json()` calls with data-driven `mcp_sync()`. The
`_scaffold_mcp_json()` function becomes obsolete - its merge logic
moves into `mcp_sync()` which operates on the full set of registry
definitions rather than a single hardcoded entry.

The `--skip mcp` opt-out continues to work because the gating pattern
(`"mcp" not in skip`) stays the same - it just gates `mcp_sync()`
instead of `_scaffold_mcp_json()`.

### 5. Provider manifest implications

The provider manifest (`ManifestData` in `manifest.py`) tracks installed
providers and their state but has no MCP-specific fields. MCP definitions
are not provider-scoped - they are workspace-level (`.mcp.json` is shared
by all providers).

This means:

- MCP registry state does not belong in the provider manifest
- MCP sync runs for all providers, not per-provider
- Uninstalling a single provider should NOT remove MCP entries (unless
  the provider contributed them and no other provider needs them)
- The `source_counts` dict in install_upgrade should include `"mcps"`

However, consumer projects (e.g., vaultspec-rag) will ship their own
MCP definitions. When multiple packages contribute definitions to the
same `.vaultspec/rules/mcps/` directory, the registry should track which
definitions are built-in vs custom, but ownership tracking beyond
`.builtin.json` naming is out of scope for this PR.

### 6. Integration points requiring modification (updated)

**`core/enums.py`**:

- Add `MCPS = "mcps"` to `Resource` enum

**`core/types.py`**:

- Add `mcps_src_dir: Path` to `WorkspaceContext`
- Construct it in `init_paths()` as
  `vaultspec / Resource.RULES.value / Resource.MCPS.value`

**`core/mcps.py`** (new module):

- `collect_mcp_servers()` - reads `.json` files from `mcps_src_dir`
- `mcp_list()` - returns metadata dicts
- `mcp_add()` - scaffolds a new custom definition
- `mcp_remove()` - deletes a definition
- `mcp_sync()` - merges definitions into `.mcp.json`

**`core/__init__.py`**:

- Re-export public API from `mcps.py`

**`core/commands.py`**:

- `_scaffold_mcp_json()` becomes obsolete - replaced by `mcp_sync()`
- `init_run()` line 427: replace `_scaffold_mcp_json(target)` with
  `mcp_sync(target)` (or equivalent call)
- `sync_provider()` `_run_all_syncs()`: add `mcp_sync` to the sync
  list alongside rules/skills/agents/system/config
- `sync_provider()` line 1269: remove the standalone
  `_scaffold_mcp_json()` repair call (now part of `_run_all_syncs`)
- `install_upgrade()` line 674: add `"mcps"` to `source_counts`
- `uninstall_run()` line 901: replace hardcoded `vaultspec-core` key
  removal with registry-aware cleanup (remove all managed entries)

**`cli/spec_cmd.py`**:

- Add `mcps_app` Typer sub-group mirroring `rules_app`

**`builtins/__init__.py`**:

- `seed_builtins()` already handles this - it copies all files from
  `.vaultspec/rules/` recursively, so `mcps/` will be seeded
  automatically

**`diagnosis/collectors.py`**:

- Extend `collect_mcp_config_state()` to detect drift between registry
  definitions and deployed `.mcp.json` entries

### 7. Sync semantics for `.mcp.json`

The merge must be:

- **Idempotent**: re-running produces the same result
- **Non-destructive**: user-added servers are preserved
- **Registry-aware**: only entries whose names match definition files are
  considered "managed"
- **Force mode**: `--force` overwrites managed entries even if user has
  modified them

Algorithm:

- Collect all JSON definitions from `mcps_src_dir`
- Read existing `.mcp.json` (or start with empty structure)
- For each definition: if server name absent or `--force`, write/overwrite
  the entry
- Write back the merged result via `atomic_write()`
- Return `SyncResult` with added/updated/skipped counts

### 8. Uninstall cleanup

Currently `uninstall_run()` hardcodes removal of the `vaultspec-core` key.
With the registry, uninstall should:

- Collect all managed server names from the registry
- Remove each from `.mcp.json`
- If no servers remain, delete `.mcp.json`
- The `.vaultspec/rules/mcps/` directory is already cleaned up when
  `.vaultspec/` is removed during full uninstall

For per-provider uninstall, the question is whether to remove MCP entries
that "belong" to that provider. Since MCP definitions are workspace-level
(not provider-scoped), the simplest approach is: full uninstall removes
all managed entries; per-provider uninstall leaves MCP untouched.

### 9. Doctor diagnostics extension

Current signals: `PARTIAL_MCP` (missing/malformed), `USER_MCP` (extra
servers), `OK` (only vaultspec-core).

New signal needed: `REGISTRY_DRIFT` - when managed entries in `.mcp.json`
differ from their registry definitions (stale command, wrong args, missing
entry that should be present).

### 10. Parallel PR #36 merge surface

PR #36 handles pre-commit hook standardization. The merge surface is
minimal:

- Both touch `commands.py` but in different functions
- #36 touches `_scaffold_precommit()` and pre-commit resolver logic
- This PR touches `_scaffold_mcp_json()` and MCP sync logic
- No overlap in `spec_cmd.py` (no `spec precommit` group in #36)

Risk: low. Avoid modifying `_scaffold_precommit()` or `resolver.py`.

## Design options

### Option A: Standalone MCP sync (recommended)

MCP sync operates independently from `sync_to_all_tools()`. Has its own
collect/merge pipeline targeting `.mcp.json` directly. Called alongside
other syncs in `sync_provider()`.

Pros: Clean separation, JSON-native, no awkward adaptation of the MD
pipeline. Cons: Small amount of pattern divergence from rules/skills.

### Option B: Adapt sync_to_all_tools for JSON

Extend `sync_to_all_tools()` to handle non-MD resources and single-file
destinations.

Pros: Unified sync surface. Cons: Significant complexity to generalize
a function designed for per-tool directory distribution. The abstraction
would leak - MCP has no per-tool variants.

### Option C: Wrapper around existing \_scaffold_mcp_json

Keep `_scaffold_mcp_json()` as the write layer, add collection and CLI
on top.

Pros: Minimal change. Cons: The scaffold function is hardcoded to the
`vaultspec-core` entry - it would need refactoring anyway to support
multiple definitions.

## Recommendation

**Option A** is the clear winner. It mirrors the rule registry's conceptual
pattern (collect -> transform -> sync) while respecting the fundamental
difference in destination format (JSON merge vs file copy). The CLI surface
mirrors rules exactly. The `_scaffold_mcp_json()` function is refactored
into the new `mcp_sync()` so there's one code path for all MCP config
management.
