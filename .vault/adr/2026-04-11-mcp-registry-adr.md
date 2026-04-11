---
tags:
  - '#adr'
  - '#mcp-registry'
date: '2026-04-11'
related:
  - '[[2026-04-11-mcp-registry-research]]'
  - '[[2026-03-28-mcp-installation-patterns-research]]'
  - '[[2026-02-22-mcp-consolidation-adr]]'
---

# `mcp-registry` adr: built-in MCP definitions with install/sync/uninstall lifecycle | (**status:** `accepted`)

## Problem Statement

`.mcp.json` management is currently hardcoded to a single `vaultspec-core`
server entry via `_scaffold_mcp_json()`. There is no mechanism for:

- Registering additional MCP servers programmatically
- Consumer projects (e.g., vaultspec-rag) enrolling their servers through
  Core's CLI
- Listing, adding, or removing MCP definitions from the command line
- Detecting drift between intended and deployed MCP configuration

The rule/skill/agent resources all have a registry pattern (source
definitions in `.vaultspec/rules/{type}/`, CLI CRUD, sync to destinations).
MCP servers lack this entirely, forcing consumers to hand-roll JSON
manipulation.

## Considerations

- MCP definitions are JSON structures, not Markdown with YAML frontmatter
  like rules/skills/agents. The existing `collect_md_resources()` and
  `sync_to_all_tools()` abstractions do not fit.
- `.mcp.json` is a single shared file (provider-agnostic), not a per-tool
  directory tree. Sync is a JSON key-level merge, not a file copy.
- The existing `_scaffold_mcp_json()` already implements correct merge
  semantics (read, merge, preserve user entries, atomic write). This logic
  needs to be generalized, not discarded.
- `seed_builtins()` recursively copies `.vaultspec/rules/` contents, so
  placing MCP definitions in `.vaultspec/rules/mcps/` gets free seeding
  on install.
- The `pyproject.toml` `force-include` already bundles `.vaultspec/rules`
  into the wheel, so new subdirectories are automatically included.
- MCP definitions are not provider-scoped. They are workspace-level: all
  providers share the same `.mcp.json`. The provider manifest does not
  need MCP-specific fields.
- The `--skip mcp` opt-out pattern must be preserved across install, sync,
  and uninstall.

## Constraints

- Must not break the existing `_scaffold_mcp_json()` contract during the
  transition - the hardcoded `vaultspec-core` entry must continue to work.
- Must not touch `_scaffold_precommit()` or `resolver.py` (PR #36 merge
  surface).
- Must not add MCP server runtime management (starting/stopping servers).
- Must not modify how providers consume `.mcp.json`.
- `WorkspaceContext` is a frozen dataclass - adding `mcps_src_dir` requires
  updating its field list and all construction sites.

## Implementation

### Storage format

One JSON file per MCP server in `.vaultspec/rules/mcps/`:

- `{server-name}.builtin.json` for built-in definitions (bundled in wheel)
- `{server-name}.json` for custom/user definitions

File content is the server configuration object matching the `.mcp.json`
`mcpServers` value schema:

```json
{
  "command": "uv",
  "args": ["run", "python", "-m", "vaultspec_core.mcp_server.app"]
}
```

The filename stem (minus `.builtin.json` or `.json` suffix) becomes the
key in `mcpServers`.

### New module: `core/mcps.py`

Mirrors the `core/rules.py` pattern with JSON-specific collection:

- `collect_mcp_servers(warnings)` - reads `.json` files from
  `mcps_src_dir`, returns `dict[str, tuple[Path, dict]]` mapping server
  name to (source path, parsed config)
- `mcp_list()` - returns metadata dicts with `name` and `source` fields
- `mcp_add(name, config, force)` - writes a new custom `.json` definition
- `mcp_remove(name)` - deletes a definition file
- `mcp_sync(dry_run, force)` - collects definitions, merges into
  `.mcp.json`, returns `SyncResult`

### Sync algorithm

`mcp_sync()` replaces `_scaffold_mcp_json()` as the single code path
for all `.mcp.json` management:

- Collect all definitions from `mcps_src_dir`
- Read existing `.mcp.json` (or initialize empty `{"mcpServers": {}}`)
- For each definition file:
  - If server name absent in `.mcp.json`: add (count as `added`)
  - If present and content matches: skip (count as `skipped`)
  - If present and content differs:
    - Without `--force`: skip, emit warning (count as `skipped`)
    - With `--force`: overwrite (count as `updated`)
- Write merged result via `atomic_write()`
- User-added entries (not matching any definition file) are always
  preserved

### Lifecycle integration

**Install** (`init_run()`):
Replace `_scaffold_mcp_json(target)` with `mcp_sync()`. The builtins
are already seeded by `seed_builtins()` before this runs, so the
registry source directory will contain the built-in definition.

**Sync** (`sync_provider()`):
Add `mcp_sync` to `_run_all_syncs()` alongside rules/skills/agents/
system/config. Remove the standalone `_scaffold_mcp_json()` repair
call that currently runs after syncs.

**Upgrade** (`install_upgrade()`):
Add `"mcps": len(collect_mcp_servers())` to `source_counts`.

**Uninstall** (`uninstall_run()`):
Replace hardcoded `vaultspec-core` key removal with registry-aware
cleanup: collect managed server names from registry, remove each from
`.mcp.json`, delete file if empty.

### CLI subcommands

Add `mcps_app` Typer sub-group to `spec_cmd.py`:

```
vaultspec-core spec mcps list [--json]
vaultspec-core spec mcps add --name <name> [--config <json>] [--force]
vaultspec-core spec mcps remove <name> [--force]
vaultspec-core spec mcps sync [--dry-run] [--force] [--json]
```

### Diagnostics

Extend `collect_mcp_config_state()` to compare deployed `.mcp.json`
entries against registry definitions. Add `REGISTRY_DRIFT` signal for
when managed entries are missing or have stale configuration.

### Public API

Re-export from `core/__init__.py`:
`collect_mcp_servers`, `mcp_list`, `mcp_add`, `mcp_remove`, `mcp_sync`

### Enum and type changes

- `Resource` enum: add `MCPS = "mcps"`
- `WorkspaceContext`: add `mcps_src_dir: Path` field
- `init_paths()`: construct `mcps_src_dir` from layout

## Rationale

**Option A (standalone MCP sync)** was chosen over adapting
`sync_to_all_tools()` because:

- MCP definitions are JSON, not Markdown - forcing them through the MD
  pipeline would require artificial format conversion
- `.mcp.json` is a single file, not a per-tool directory tree - the
  `sync_to_all_tools()` abstraction of iterating over tool configs and
  writing to per-tool directories does not apply
- The conceptual pattern (collect -> merge -> write) is preserved while
  the implementation is adapted to JSON merge semantics
- The CLI surface (`spec mcps list|add|remove|sync`) mirrors rules/skills
  exactly, maintaining UX consistency

The `_scaffold_mcp_json()` function is superseded rather than wrapped
because its hardcoded single-entry logic cannot support multiple
definitions. The merge semantics it pioneered (read, merge, preserve
user entries, atomic write) are preserved in `mcp_sync()`.

## Consequences

- `_scaffold_mcp_json()` becomes dead code and should be removed
- All three lifecycle touchpoints (install, sync, uninstall) gain
  data-driven MCP management instead of hardcoded single-entry handling
- Consumer projects can ship `.builtin.json` files that get seeded
  alongside their rules, enabling `vaultspec-core sync` to propagate
  MCP entries without manual JSON editing
- The `--skip mcp` opt-out continues to work unchanged
- The `SyncResult` returned by `sync_provider()` will now include MCP
  sync statistics
- Doctor diagnostics can detect configuration drift for MCP entries,
  not just presence/absence of the `vaultspec-core` key
- The provider manifest does not require MCP-specific fields; MCP
  definitions remain workspace-scoped, not provider-scoped
