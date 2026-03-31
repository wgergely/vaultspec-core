---
tags:
  - '#exec'
  - '#audit-findings'
date: '2026-03-30'
related:
  - '[[2026-03-30-audit-findings-plan]]'
  - '[[2026-03-27-cli-ambiguous-states-audit]]'
---

# `audit-findings` phase 6-8 exec

Implemented all formerly-deferred findings: security and path
safety (phase 6), systemic filesystem hardening (phase 7), and
completeness with UX polish (phase 8).

- Modified: `src/vaultspec_core/core/types.py`
- Modified: `src/vaultspec_core/core/sync.py`
- Modified: `src/vaultspec_core/core/tags.py`
- Modified: `src/vaultspec_core/config/workspace.py`
- Modified: `src/vaultspec_core/vaultcore/resolve.py`
- Modified: `src/vaultspec_core/core/rules.py`
- Modified: `src/vaultspec_core/core/commands.py`
- Modified: `src/vaultspec_core/core/revert.py`
- Modified: `src/vaultspec_core/core/agents.py`
- Modified: `src/vaultspec_core/core/skills.py`
- Modified: `src/vaultspec_core/vaultcore/index.py`
- Modified: `src/vaultspec_core/vaultcore/hydration.py`
- Modified: `src/vaultspec_core/vaultcore/checks/dangling.py`
- Modified: `src/vaultspec_core/vaultcore/checks/links.py`
- Modified: `src/vaultspec_core/vaultcore/checks/frontmatter.py`
- Modified: `src/vaultspec_core/vaultcore/checks/references.py`
- Modified: `src/vaultspec_core/core/manifest.py`
- Modified: `src/vaultspec_core/protocol/providers/base.py`
- Modified: `src/vaultspec_core/core/diagnosis/collectors.py`
- Modified: `src/vaultspec_core/cli/root.py`
- Modified: `src/vaultspec_core/core/helpers.py`
- Modified: `src/vaultspec_core/core/resolver.py`
- Modified: `src/vaultspec_core/config/config.py`
- Modified: `src/vaultspec_core/mcp_server/vault_tools.py`
- Modified: `src/vaultspec_core/tests/cli/workspace_factory.py`
- Modified: `src/vaultspec_core/tests/cli/test_resolver.py`

## Description

### Phase 6: Security and path safety

- R6-SI1: Added `_validate_tool_containment()` in `types.py` that
  verifies all ToolConfig directories are descendants of workspace
  root. Called from `init_paths()`. Raises `VaultSpecError` if
  any path escapes the workspace.
- R3-SEC3: Added content-ownership heuristic to sync prune. Before
  deleting stale `.md` files, checks for `AUTO-GENERATED` marker,
  `vaultspec` tag, or `trigger:` header. User-authored files are
  skipped with a warning.
- R4-EX6: Unified exception hierarchy. `TagError`, `WorkspaceError`,
  and `RelatedResolutionError` now inherit from `VaultSpecError`.

### Phase 7: Systemic filesystem hardening

- R4-FS1: Migrated 8 raw `write_text`/`write_bytes` calls to
  `atomic_write` across sync.py, rules.py, commands.py, revert.py,
  agents.py, skills.py, index.py, hydration.py.
- R4-FS2: Added backup-before-write to vault document auto-fix
  checks in dangling.py, links.py, frontmatter.py, references.py.
  `.bak` file written before modification, removed on success.
- R4-C1/R4-C2/R2-W4: Added advisory file locking to manifest
  read-modify-write via `_manifest_lock()` context manager using
  `fcntl.flock` (Unix) / `msvcrt.locking` (Windows).
- R6-CG1: Added circular include guard to `resolve_includes` via
  `visited: set[str]` parameter.

### Phase 8: Completeness and UX polish

- R1-M2/R3-P1: Implemented `ProviderDirSignal.MIXED` detection in
  `collect_provider_dir_state` by checking children against known
  resource patterns.
- R2-E3: `cmd_doctor` checks `target.exists()` before diagnosis.
- R2-W3: `atomic_write` uses `write_bytes` to prevent `\n` to
  `\r\n` conversion on Windows.
- R2-B4/R3-F4: Preflight messaging now says "detected, will be
  addressed by..." for non-immediate steps.
- R3-P2: Replaced 6 catch-all `"Unhandled signal"` warnings with
  explicit match arms documenting why no action is needed.
- R4-C3: Thread-safe config singleton via `threading.Lock`.
- R5-D4: `collect_skills` warns on skill dirs without `SKILL.md`.
- R5-D5: MCP `find` tool logs warning and includes note when graph
  ranking is unavailable.
- R6-SI4: Added `errored` field to `SyncResult` and
  `format_summary`.
- R6-SI5: `sync_to_all_tools` tracks seen destination dirs to
  prevent double-sync skipped inflation.
- R3-UX1-UX7: All 7 ambiguous error/warning messages improved with
  recovery guidance, actual paths, and signal values.

## Tests

All 680 existing tests pass. Ruff lint and format clean. Updated
test fixtures in `workspace_factory.py` for content-ownership guard
and resolver test assertions for improved messages.
