---
tags:
  - '#reference'
  - '#cli-architecture'
date: 2026-03-21
---

# CLI Grounding Research: Contract vs Implementation

Date: 2026-03-16
Reference: [cli-contract.md](cli-contract.md)

This document maps every drift, gap, and redundancy between the binding contract and the current implementation across both the Python CLI and the justfile.

______________________________________________________________________

## 1. Global Options

| Contract         | Current Implementation                             | Status                                                                                                                      |
| ---------------- | -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `--target PATH`  | `--target/-t` with help "Workspace root directory" | DRIFT: Help text is vague. Contract says "Select installation destination folder. Use '.' for current working directory."   |
| `--debug` (only) | `--debug/-d` AND `--verbose/-v`                    | DRIFT: Contract eliminates `--verbose`. Current has both.                                                                   |
| (none)           | `--version/-V`                                     | OK: Not mentioned in contract but standard; keep.                                                                           |
| (none)           | `--install-completion`, `--show-completion`        | GAP: Typer auto-generates these. Contract flags them as perplexing. Typer default behavior — must be explicitly suppressed. |

### Action required

- Remove `--verbose/-v` option and all INFO-level logic gating
- Rewrite `--target` help string
- Suppress Typer's completion options or decide to keep them

______________________________________________________________________

## 2. Top-Level Commands

### 2.1 install

| Contract                                                      | Current Implementation                                                                    | Status                                                                                                                                    |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `install <path> [provider] [--upgrade] [--dry-run] [--force]` | `install <path> [provider] [--upgrade] [--dry-run]`                                       | GAP: **`--force` missing entirely.**                                                                                                      |
| Providers: all, core, claude, gemini, antigravity, codex      | Same set via `VALID_PROVIDERS`                                                            | OK                                                                                                                                        |
| `core` = .vaultspec only                                      | `_PROVIDER_TO_TOOLS["core"] = []` (empty list) → scaffolds core dirs but no provider dirs | OK (functionally correct)                                                                                                                 |
| Named provider implies core + provider                        | Fresh install calls `init_run()` which always scaffolds core first, then provider.        | OK (implicit, not documented)                                                                                                             |
| `--force` overrides existing                                  | No `--force` flag exists. If `.vaultspec/` exists: hard error exit 1                      | **MISSING**: Must add `--force` to allow overwriting existing installation                                                                |
| `--dry-run` visual tree with coloured output                  | Current: prints flat list with `"Would create:"` prefix                                   | **BROKEN**: No tree structure. No colour coding. No status categories (exists/new/update/override/delete). Uses rejected "would" wording. |
| Path error when wrong                                         | Typer `exists=True` raises default error                                                  | DRIFT: Error message is Typer's generic "Invalid value" — not actionable                                                                  |
| Path error when missing                                       | Typer requires the argument                                                               | DRIFT: Error message is Typer's generic "Missing argument" — not actionable                                                               |

### 2.2 uninstall

| Contract                                                           | Current Implementation                                                      | Status                                                                                                |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `uninstall <path> [provider] [--keep-vault] [--dry-run] [--force]` | `uninstall <path> [provider] [--keep-vault] [--dry-run]`                    | GAP: **`--force` missing.**                                                                           |
| Must fail by default, requires `--force`                           | Executes immediately without confirmation                                   | **BREAKING**: Destructive operation runs without any safety gate                                      |
| `core` unrolls all providers                                       | Current: `core` removes only `.vaultspec/` dir, leaves provider dirs intact | **WRONG**: Contract says uninstalling core means everything goes. Current only removes `.vaultspec/`. |
| `--dry-run` visual tree                                            | Current: prints `"would remove"` lines                                      | DRIFT: Same flat output issues as install dry-run                                                     |

### 2.3 sync

| Contract                                           | Current Implementation                                                                   | Status                                                                                                                                               |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sync [provider] [--prune] [--dry-run] [--force]`  | `sync [provider] [--prune] [--dry-run] [--force]`                                        | OK: Signature matches                                                                                                                                |
| Providers: all, claude, gemini, antigravity, codex | `_SYNC_PROVIDERS = {"all", "claude", "gemini", "antigravity", "codex"}`                  | OK                                                                                                                                                   |
| `core` must error                                  | `core` is not in `_SYNC_PROVIDERS`, so it falls through to "Unknown sync provider" error | OK (works by omission, error message could be better)                                                                                                |
| Must respect installed provider manifest           | Reads manifest via `read_manifest()`, checks if provider is installed                    | PARTIAL: Checks manifest for per-provider sync, but `sync all` ignores manifest entirely — syncs all configured tools regardless of what's installed |
| Folder checks not safe alone                       | Manifest check exists but `sync all` bypasses it                                         | DRIFT: `sync all` should filter to only installed providers                                                                                          |

______________________________________________________________________

## 3. Domain Command Groups

### 3.1 vault

| Contract Command                | Current Implementation                                                        | Status                                                                                                                                                                                      |
| ------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vault add adr\|research\|plan` | `vault add --type TYPE --feature FEATURE [--title]`                           | DRIFT: Contract uses positional type arg, current uses `--type` option. Contract limits to adr/research/plan; current accepts all 6 DocTypes (adr, audit, exec, plan, reference, research). |
| `--feature` required            | `--feature` is required (typer.Option, no default)                            | OK                                                                                                                                                                                          |
| `--date` defaults to today      | Hardcoded `datetime.now().strftime("%Y-%m-%d")` — no CLI option exists        | **MISSING**: No `--date` override option. Always uses today.                                                                                                                                |
| `--content` option              | Not implemented                                                               | **MISSING**                                                                                                                                                                                 |
| `vault stats`                   | Not a standalone command. Partially covered by `vault audit --summary`        | **MISSING**: Must be a separate command with `--feature`, `--date`, `--type`, `--invalid`, `--orphaned` filters                                                                             |
| `vault list TYPE`               | Not implemented                                                               | **MISSING**: No list command at all. `vault audit --features` lists feature names only.                                                                                                     |
| `vault feature list`            | Partially via `vault audit --features` (lists feature names only, no filters) | **MISSING**: No `--date`, `--orphaned`, `--type` filters. Not a proper subcommand.                                                                                                          |
| `vault feature archive`         | Not implemented                                                               | **MISSING**                                                                                                                                                                                 |
| `vault doctor`                  | Partially via `vault audit --fix`                                             | DRIFT: Exists as a flag on audit, not as its own command. Contract wants standalone `vault doctor`.                                                                                         |

**Current vault commands that have no contract equivalent:**

- `vault audit --graph` — Graph hotspot analysis
- `vault audit --verify` — Verification without fix
- `vault audit --json` — JSON output mode
- `vault audit --limit` — Limit results
- `vault audit --type` (filter) — Only used for graph filtering
- `vault audit --feature` (filter) — Only used for graph filtering

These are valuable capabilities but bundled into a monolithic `audit` command instead of discrete, composable commands.

### 3.2 spec

| Contract Command                              | Current Implementation                                                 | Status                                                                                                      |
| --------------------------------------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `spec rules list\|add\|remove\|edit\|revert`  | `rules list\|add\|show\|edit\|remove\|rename\|sync` (top-level group)  | DRIFT: (1) Not nested under `spec`. (2) Has `show`, `rename`, `sync` not in contract. (3) Missing `revert`. |
| `spec skills list\|add\|remove\|edit\|revert` | `skills list\|add\|show\|edit\|remove\|rename\|sync` (top-level group) | Same drift as rules                                                                                         |
| `spec agents list\|add\|remove\|edit\|revert` | `agents list\|add\|show\|edit\|remove\|rename\|sync` (top-level group) | Same drift as rules                                                                                         |
| `spec system list\|add\|remove\|edit\|revert` | `system show\|sync` (top-level group)                                  | DRIFT: Only has `show` and `sync`. Missing `list`, `add`, `remove`, `edit`, `revert`.                       |
| `spec hooks`                                  | `hooks list\|run` (top-level group)                                    | DRIFT: Not nested under `spec`.                                                                             |
| `revert` on all resources                     | Not implemented anywhere                                               | **MISSING**: No mechanism to restore original/builtin content                                               |

**Current commands with no contract equivalent:**

- `rules sync`, `skills sync`, `agents sync` — Per-resource sync commands. Contract has only top-level `sync`.
- `rules show`, `skills show`, `agents show` — `show` not mentioned in contract.
- `rules rename`, `skills rename`, `agents rename` — `rename` not mentioned in contract.
- `config show`, `config sync` — `config` group not in contract at all.

### 3.3 dev

| Contract Command                    | Current Implementation                                                                        | Status                                                                                                                                                                                                  |
| ----------------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dev test [unit\|integration\|all]` | `test --category [unit\|api\|all\|quality] --module [cli\|vault\|protocol\|core]` (top-level) | DRIFT: (1) Not nested under `dev`. (2) Uses `--category` option instead of positional. (3) Different categories (no `integration`, has `api` and `quality`). (4) Has `--module` filter not in contract. |
| (not user-facing)                   | `test` is a top-level command exposed to all users                                            | DRIFT: Contract says dev commands should not be user-facing                                                                                                                                             |

______________________________________________________________________

## 4. Commands in Current CLI with No Contract Equivalent

| Current Command                              | Disposition                                                                                                                         |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `init [--force] [provider]`                  | **OBSOLETE**: Contract says install/uninstall/sync cover the same ground. `install` calls `init_run()` internally.                  |
| `doctor`                                     | **UNCLEAR**: Contract has `vault doctor` for autofix. Current `doctor` checks Python version and optional deps — different purpose. |
| `readiness [--json]`                         | **UNCLEAR**: Contract lists as purpose unclear. Scores workspace on 4 dimensions (1-5). May be useful but needs clear framing.      |
| `config show`                                | **UNPLACED**: Shows generated tool configs. Useful for debugging but not in contract.                                               |
| `config sync`                                | **REDUNDANT**: Already part of top-level `sync`.                                                                                    |
| `rules sync` / `skills sync` / `agents sync` | **REDUNDANT**: Already part of top-level `sync`. Individual resource sync adds granularity but clutters the surface.                |
| `system sync`                                | **REDUNDANT**: Already part of top-level `sync`.                                                                                    |

______________________________________________________________________

## 5. Justfile Mapping

### Recipes that mirror Python CLI

| Justfile Recipe                            | Python CLI Equivalent                                | Alignment                           |
| ------------------------------------------ | ---------------------------------------------------- | ----------------------------------- |
| `just install [path] [provider] [*args]`   | `vaultspec-core install <path> [provider] [flags]`   | OK: Direct passthrough via `uv run` |
| `just uninstall [path] [provider] [*args]` | `vaultspec-core uninstall <path> [provider] [flags]` | OK: Direct passthrough              |

### Recipes that should mirror but don't

| Justfile Recipe | Issue                                                                                                                                                     |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `just sync`     | **COLLISION**: Justfile `sync` means `uv sync` (dependency management), NOT `vaultspec-core sync`. There is no justfile recipe for `vaultspec-core sync`. |

### Development-only recipes (no Python CLI equivalent needed)

| Justfile Recipe                                                                    | Purpose                  |
| ---------------------------------------------------------------------------------- | ------------------------ |
| `just sync dependencies\|dependency-upgrades`                                      | uv dependency management |
| `just lock dependencies\|dependency-upgrades`                                      | uv lock file management  |
| `just fix lint\|markdown\|vault`                                                   | Auto-fix code/docs       |
| `just check all\|lint\|type\|dependencies\|links\|toml\|markdown\|workflow\|vault` | Quality checks           |
| `just test python\|docker\|all`                                                    | Test execution           |
| `just build python\|docker\|all`                                                   | Package/image building   |
| `just publish docker-ghcr <tag>`                                                   | Image publishing         |

### Justfile gaps

- **No `just sync` for vaultspec-core sync** — name collision with dependency sync
- **No `just vault` recipes** — vault commands not exposed through justfile
- **No `just spec` recipes** — spec commands not exposed through justfile

______________________________________________________________________

## 6. Structural Issues

### 6.1 Double registration

Commands in `spec_cli.py` are registered on both `spec_app` (internal Typer) and mounted to `app` (root) via `cli.py`. The `spec_app` Typer is never actually mounted — only individual commands and sub-Typers are extracted. This is confusing: `spec_app.command("sync")` and `spec_app.command("install")` decorators exist but the commands are re-registered with `app.command("sync")(cmd_sync)`. The `spec_app` serves no purpose as a grouping mechanism.

### 6.2 Flat namespace pollution

All resource groups (`rules`, `skills`, `agents`, `config`, `system`, `hooks`) are mounted at the root level. Contract wants them nested under `spec`. This means the root `--help` output is cluttered with 7 sub-groups + 7 top-level commands = 14 items instead of 3 top-level commands + 3 domain groups.

### 6.3 Workspace resolution bypass

`init`, `install`, `uninstall` bypass workspace resolution in `cli.py:main()` callback. This is a special case that sets `TARGET_DIR` directly. If a new command group (`vault`, `spec`, `dev`) is added, the bypass list must be updated — fragile design.

### 6.4 Module-level mutable globals

`types.py` uses module-level globals (`TARGET_DIR`, `TOOL_CONFIGS`, etc.) mutated by `init_paths()`. `_sync_provider()` temporarily mutates `TOOL_CONFIGS` and restores in a `finally` block. This is fragile and not thread-safe.

### 6.5 Unicode crash on Windows

`doctor` and `readiness` commands crash on Windows with `UnicodeEncodeError` because Rich console uses characters (checkmarks, warning symbols, bar charts) that cp1252 cannot encode. The console is not configured with `force_terminal=True` or UTF-8 encoding override.

### 6.6 Provider manifest location

Manifest is stored at `.vaultspec/providers.json`. Format:

```json
{"version": 1, "installed": ["claude", "gemini"]}
```

This answers the contract's open question about persistence location. The manifest exists but is underutilized — `sync all` ignores it.

______________________________________________________________________

## 7. Capability Inventory: What Exists But Is Unexposed

The vault domain layer has significant capabilities that are not surfaced through the CLI at all or are buried in the monolithic `audit` command:

| Capability               | Backend Module        | Current CLI Exposure     | Contract Requirement                |
| ------------------------ | --------------------- | ------------------------ | ----------------------------------- |
| Document creation        | `hydration.py`        | `vault add`              | `vault add` (with expanded options) |
| Metrics summary          | `metrics/api.py`      | `vault audit --summary`  | `vault stats` (standalone)          |
| Feature listing          | `verification/api.py` | `vault audit --features` | `vault feature list` (with filters) |
| Feature archival         | —                     | None                     | `vault feature archive`             |
| Document listing by type | `scanner.py`          | None                     | `vault list TYPE`                   |
| Graph hotspots           | `graph/api.py`        | `vault audit --graph`    | Not in contract (valuable)          |
| Invalid link detection   | `graph/api.py`        | `vault audit --graph`    | Could feed into `--invalid` filter  |
| Orphan detection         | `graph/api.py`        | `vault audit --graph`    | Could feed into `--orphaned` filter |
| Vertical integrity       | `verification/api.py` | `vault audit --verify`   | Could feed into `vault doctor`      |
| Auto-repair              | `verification/api.py` | `vault audit --fix`      | `vault doctor`                      |
| Malformed detection      | `verification/api.py` | `vault audit --verify`   | Could feed into `vault doctor`      |

______________________________________________________________________

## 8. Summary: Gap Count

| Category                | Count | Examples                                                                                                          |
| ----------------------- | ----- | ----------------------------------------------------------------------------------------------------------------- |
| **Missing flags**       | 3     | install `--force`, uninstall `--force`, vault add `--date`                                                        |
| **Missing commands**    | 7     | vault stats, vault list, vault feature list, vault feature archive, vault doctor, spec (as group), dev (as group) |
| **Missing features**    | 2     | revert mechanism, vault add `--content`                                                                           |
| **Wrong behavior**      | 3     | uninstall runs without `--force`, uninstall core doesn't cascade, sync all ignores manifest                       |
| **Broken output**       | 2     | dry-run flat/no-colour, Unicode crash on Windows                                                                  |
| **Structural drift**    | 4     | flat namespace (not nested), spec_app double-registration, init obsolete, verbose/debug split                     |
| **Redundant commands**  | 5     | init, per-resource sync (rules/skills/agents/config/system sync)                                                  |
| **Help text deficient** | all   | Every command description needs rewrite per quality standards                                                     |

______________________________________________________________________

## 9. Backend Implementation Depth

### 9.1 Sync engine (`sync.py`)

Core function: `sync_files()` → iterates sources, calls `transform_fn()` per file, writes via `atomic_write()`.

- **Dry-run**: logs planned actions, does not write. No visual tree, no colour, no status categories.
- **Prune**: deletes `.md` files (or `vaultspec-*` dirs for skills) not in source set.
- **Content comparison**: reads entire file to compare — no hash-based check.
- **No atomicity across destinations**: if sync fails halfway through `sync_to_all_tools()`, partial state is left with no rollback.
- **No backup of overwritten files**: `atomic_write()` uses tmp+rename but no pre-write backup.

`sync_to_all_tools()` iterates `TOOL_CONFIGS` — does NOT check manifest. This is the root cause of sync-all ignoring installed providers.

### 9.2 Resource operations (`resources.py`)

Four generic CRUD functions: `resource_show`, `resource_edit`, `resource_remove`, `resource_rename`.

- **No revert**: `resource_remove` calls `unlink()` with no backup. No undo.
- **No revert**: `resource_edit` launches editor with no pre-edit snapshot.
- **Editor launch**: calls `_launch_editor()` from helpers — does not validate editor exists before launching.
- **Confirmation**: `resource_remove` uses `typer.confirm()` when `force=False`. Blocking modal.

### 9.3 Revert feasibility

No backup mechanism exists anywhere. Options for implementing `revert`:

1. **Git-based**: if `.vaultspec/` is tracked, `git checkout -- <file>` restores last committed version. Requires git.
1. **Builtin marker**: files ending in `.builtin.md` could have originals bundled in the package. Revert = copy from package.
1. **Shadow copy**: maintain `.vaultspec/.backup/` with pre-edit copies. Adds complexity.

Builtin marker approach is the most natural — builtin firmware ships with the package, custom resources have no "original" to revert to.

### 9.4 Config generation (`config_gen.py`)

Uses `<vaultspec>` tag system to manage blocks within user files (CLAUDE.md, GEMINI.md, etc.). Key pattern:

- `upsert_block()` inserts or replaces managed content blocks
- User content outside `<vaultspec>` tags is preserved
- Separate blocks for `config`, `agents`, `settings` in TOML files

Silent append to user files: if a user-created CLAUDE.md exists without managed blocks, config_sync appends a managed block without explicit warning. This is by design but undocumented.

### 9.5 System prompt assembly (`system.py`)

Assembly order: `base.md` → tool-specific parts → skill listing → shared parts (sorted by `order` frontmatter, default 50).

- System files (e.g., `.gemini/SYSTEM.md`) are only written if `system_file` is set on `ToolConfig`
- Tools without `system_file` but with `emit_system_rule=True` get a `vaultspec-system.builtin.md` rule file instead
- Antigravity has `emit_system_rule=False` — gets no system content at all

### 9.6 Agents sync — dual codepath

Standard tools: `sync_files()` writes agent `.md` files to `agents_dir`.
Codex: uses `<vaultspec>` tag system to write TOML agent blocks into `config.toml`. Completely separate code path with its own rendering (`_render_codex_agent()`), model coercion (`_coerce_codex_model()`), and error handling (`TagError` caught as warning).

______________________________________________________________________

## 10. Vault Backend API Capabilities

### 10.1 What exists and is ready

| Backend Function                                                  | Module              | Ready for CLI? | Notes                                                                                                               |
| ----------------------------------------------------------------- | ------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------- |
| `get_vault_metrics(root_dir)` → `VaultSummary`                    | metrics/api.py      | Partial        | Has total_docs, counts_by_type, total_features. Missing: per-feature counts, date filtering, orphan/invalid counts. |
| `scan_vault(root_dir)` → `Iterator[Path]`                         | scanner.py          | Yes            | Full vault discovery. No filtering — all filtering must be client-side.                                             |
| `get_doc_type(path, root_dir)` → `DocType`                        | scanner.py          | Yes            | Classifies file by parent directory.                                                                                |
| `list_features(root_dir)` → `set[str]`                            | verification/api.py | Partial        | Returns feature names. No metadata (creation date, doc count, plan status).                                         |
| `get_malformed(root_dir)` → `list[VerificationError]`             | verification/api.py | Yes            | Full structural + per-file validation.                                                                              |
| `verify_vertical_integrity(root_dir)` → `list[VerificationError]` | verification/api.py | Yes            | Checks every feature has a PLAN.                                                                                    |
| `fix_violations(root_dir)` → `list[FixResult]`                    | verification/api.py | Partial        | Auto-repairs 6 violation types. No dry-run/preview mode. No selective repair.                                       |
| `VaultGraph(root_dir)`                                            | graph/api.py        | Yes            | Full bidirectional link graph with hotspots, orphans, invalid links, feature rankings.                              |
| `create_vault_doc(root_dir, type, feature, date, title)`          | hydration.py        | Yes            | Creates from template. No `--content` support.                                                                      |
| `parse_frontmatter(content)` → `(dict, str)`                      | parser.py           | Yes            | YAML parsing with fallback.                                                                                         |
| `parse_vault_metadata(content)` → `(DocumentMetadata, str)`       | parser.py           | Yes            | Structured metadata extraction with validation.                                                                     |

### 10.2 What must be built for contract commands

**`vault stats`**: Need a new function or CLI-side composition:

- Per-feature document counts (scan + group-by)
- Date range filtering (parse date from filename or frontmatter)
- Orphan count (graph orphans)
- Invalid link count (graph invalid links)

**`vault list TYPE`**: Need CLI-side composition:

- `scan_vault()` + `get_doc_type()` + filter by type
- Parse frontmatter for each to get feature/date
- Filter by `--date`, `--feature`
- Format as table

**`vault feature list`**: Need enrichment over `list_features()`:

- Per-feature: doc count, doc types present, creation date (earliest doc), plan status
- Filter by `--date`, `--orphaned`, `--type`

**`vault feature archive`**: Completely new capability:

- Move all docs for a feature to an archive subdirectory
- Or add `archived: true` frontmatter flag
- Or rename with archive prefix
- Decision needed on mechanism

**`vault doctor`**: Composition of existing:

- `get_malformed()` + `verify_vertical_integrity()` → find issues
- `fix_violations()` → auto-repair
- Need preview/dry-run wrapper
- Need summary formatting

### 10.3 DocType enum values

```
adr, audit, exec, plan, reference, research
```

Template mapping: adr→adr.md, audit→audit.md, plan→plan.md, research→research.md, reference→ref-audit.md, exec→exec-step.md

______________________________________________________________________

## 11. Hooks Engine

### 11.1 Current supported events

```
vault.document.created
config.synced
audit.completed
```

Only 3 events. Hooks are YAML files in `.vaultspec/rules/hooks/`. Format:

```yaml
event: "vault.document.created"
enabled: true
actions:

  - type: "shell"
    command: "vaultspec-core vault audit --verify"
```

### 11.2 Hooks belong under spec

Hooks are `.vaultspec/` firmware — they are authored/managed as part of the spec framework, not vault documentation. Nesting under `spec hooks` is correct.

### 11.3 Hook engine issues

- Only `"shell"` action type supported
- 60-second hardcoded timeout
- Re-entrance guard prevents recursive hook firing (good)
- No hook validation command (can only list and run)

______________________________________________________________________

## 12. MCP Server Alignment

7 MCP tools registered in `vault_tools.py`:

| MCP Tool                                                       | CLI Equivalent                                        | Alignment                                                |
| -------------------------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------- |
| `query_vault(query, feature, type, related_to, recent, limit)` | `vault list` (proposed)                               | Good — MCP already has the query filtering the CLI lacks |
| `feature_status(feature)`                                      | `vault feature list` (proposed)                       | Partial — MCP returns lifecycle status per feature       |
| `create_vault_document(type, feature, title, extra_context)`   | `vault add`                                           | Good — MCP has `extra_context` param the CLI lacks       |
| `list_spec_resources(resource)`                                | `spec rules/skills/agents list`                       | OK                                                       |
| `get_spec_resource(resource, name)`                            | `spec rules/skills/agents show` (via `resource_show`) | OK                                                       |
| `workspace_status(check)`                                      | `readiness` / `doctor`                                | Bundles both; CLI disposition unclear                    |
| `audit_vault(summary, verify, fix)`                            | `vault stats` + `vault doctor`                        | Maps to multiple contract commands                       |

The MCP server will need restructuring to match the new CLI surface, but the underlying queries it performs are already more capable than the current CLI. The MCP `query_vault` function already does what `vault list` needs.

______________________________________________________________________

## 13. Test Coverage Impact

### 13.1 Tests that will break on restructuring

| Test File                      | What Breaks                                                                        | Severity |
| ------------------------------ | ---------------------------------------------------------------------------------- | -------- |
| `test_main_cli.py`             | All command routing tests — namespace changes from flat to nested                  | HIGH     |
| `test_vault_cli.py`            | `vault audit` decomposition into stats/list/doctor                                 | HIGH     |
| `test_spec_cli.py`             | Commands move under `spec` group, `init`/`doctor`/`readiness` removed or relocated | HIGH     |
| `test_integration.py`          | `--target` propagation — may survive if callback structure preserved               | MEDIUM   |
| `test_commands.py`             | `init_run()` tests — init becomes internal to install                              | MEDIUM   |
| `test_automation_contracts.py` | Justfile recipe validation — recipes change                                        | HIGH     |

### 13.2 Tests that should survive

| Test File                                                   | Why                                      |
| ----------------------------------------------------------- | ---------------------------------------- |
| `test_sync_collect.py`                                      | Tests backend functions, not CLI surface |
| `test_sync_parse.py`                                        | Tests parsing/writing utilities          |
| `test_sync_operations.py`                                   | Tests sync engine logic                  |
| `test_sync_incremental.py`                                  | Tests sync lifecycle                     |
| `test_tags.py`                                              | Tests `<vaultspec>` tag parser           |
| All `vaultcore/tests/`                                      | Tests vault domain models/parser/scanner |
| All `graph/tests/`, `verification/tests/`, `metrics/tests/` | Tests backend APIs                       |

### 13.3 Tests that need to be written

- install `--force` behavior
- install `--dry-run` visual tree output
- uninstall `--force` safety gate
- uninstall `core` cascade behavior
- sync manifest-aware filtering
- `vault stats`, `vault list`, `vault feature list`, `vault feature archive`, `vault doctor`
- `spec` group nesting
- `dev test` nesting
- `revert` for all resource types
- Unicode/encoding safety on Windows

______________________________________________________________________

## 14. Revised Gap Summary

| Category                 | Count        | Items                                                                                                                                  |
| ------------------------ | ------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| **Missing CLI flags**    | 4            | install `--force`, uninstall `--force`, vault add `--date`, vault add `--content`                                                      |
| **Missing CLI commands** | 8            | vault stats, vault list, vault feature list, vault feature archive, vault doctor, spec (group), dev (group), revert (on all resources) |
| **Wrong behavior**       | 3            | uninstall runs without `--force`, uninstall core doesn't cascade, sync all ignores manifest                                            |
| **Broken output**        | 2            | dry-run flat/no-colour, Unicode crash on Windows                                                                                       |
| **Structural drift**     | 5            | flat namespace, spec_app double-registration, init obsolete, verbose/debug split, workspace bypass fragility                           |
| **Backend gaps**         | 4            | vault stats enrichment, vault list composition, feature archive mechanism, fix_violations dry-run                                      |
| **Redundant commands**   | 6            | init, per-resource sync ×4, config group                                                                                               |
| **Test impact**          | 6 files HIGH | CLI routing tests must be rewritten                                                                                                    |
| **MCP alignment**        | 3 tools      | query_vault/feature_status/audit_vault need CLI parity                                                                                 |
| **Help text**            | all          | Every description needs rewrite                                                                                                        |
