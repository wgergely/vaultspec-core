---
tags:
  - '#audit'
  - '#feature-documentation'
date: '2026-03-21'
related:
  - '[[2026-03-21-builtins-build-strategy-adr]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `feature-documentation` Code Review

<!-- Persistent log of audit findings appended below. -->

<!-- Use: {TOPIC}-### | {LEVEL} | {Summary} \n {DESCRIPTION} format-->

## CLI Layer

CLI-H1 | ~~HIGH~~ FALSE POSITIVE | `cmd.exe` flag typo `\c` instead of `/c`
`src/vaultspec_core/core/helpers.py:137` - Code already uses `/c` (forward slash). Reviewer error.

CLI-H2 | HIGH | Mutable default argument `skip: list[str] = []`
`root.py:150`, `root.py:268`, `root.py:358` - Typer handles this safely at the CLI layer, but if called programmatically the shared mutable default accumulates state across calls.

CLI-M1 | MEDIUM | Variable `target` shadows parameter in `cmd_system_show`
`vault_cmd.py:636` - Loop variable `for target in data["targets"]` shadows the function parameter `target: TargetOption`. Latent defect if function is extended.

CLI-M2 | MEDIUM | `_workspace_initialized` idempotency guard incomplete
`_target.py:125-128` - `apply_target` skips re-init only when `target is None`, not when the same non-None target is re-passed.

CLI-M3 | MEDIUM | Duplicated `_handle_error` function
`root.py:109-118` and `spec_cmd.py:27-36` - Identical helper copy-pasted in two files. DRY violation.

CLI-M4 | MEDIUM | Top-level imports in `vault_cmd.py` break lazy-import pattern
`vault_cmd.py:17-18` - `VaultGraph` and `CheckResult` imported eagerly, unlike rest of CLI.

CLI-M5 | MEDIUM | `_infer_label` missing `/.codex/` mapping
`root.py:465` - `provider_map` has `/.agents/` -> `"antigravity"` but no `/.codex/` entry.

CLI-M6 | MEDIUM | No input sanitization on `--name` for spec add commands
`spec_cmd.py:71-88,253-273,443-460` - No validation of path separators in `name` parameter.

CLI-L1 | LOW | Unused `logger` in `spec_cmd.py` and `vault_cmd.py`
`spec_cmd.py:10,17` and `vault_cmd.py:10,20` - `logging` imported and logger created but never used.

CLI-L2 | LOW | `render_uninstall_summary` hardcodes provider names
`rendering.py:141` - Set `{"claude", "gemini", "antigravity", "codex"}` hardcoded.

CLI-L3 | LOW | `_is_utf8_capable` misses `UTF-8-SIG` variant
`console.py:23` - Normalization doesn't handle BOM-prefixed variant.

CLI-L4 | LOW | `apply_target_install` mutates `TARGET_DIR` directly
`_target.py:155` - Bypasses normal `init_paths` pathway, creating two paths for setting globals.

## Core Domain

CORE-H1 | HIGH | Mutable global `TOOL_CONFIGS` race condition
`types.py:98-106`, `commands.py:825-826,869` - Module-level mutable dict replaced during per-provider sync. Concurrent callers (MCP) can corrupt each other's view.

CORE-H2 | HIGH | `_ensure_tool_configs` creates/deletes dirs with race window
`commands.py:299-336` - Temporary `.vaultspec/` dir created and removed; another process creating files in between causes silent deletion via `shutil.rmtree`.

CORE-M1 | MEDIUM | `_sync_supporting_files` silently swallows errors
`sync.py:54-58` - Bare `except Exception: pass` on content comparison.

CORE-M2 | MEDIUM | `resource_remove` has unsafe `confirm_fn` typing
`resources.py:87,113` - Typed as `object | None` but called as function with `# type: ignore`.

CORE-M3 | MEDIUM | `system.py:41` catches redundant exception hierarchy
`system.py:41` - `except (OSError, Exception)` is redundant; `Exception` subsumes `OSError`.

CORE-M4 | MEDIUM | No path traversal validation on resource names
`resources.py:20-30` - `_resolve_path` joins arbitrary `name` with `base_dir` without sanitization.

CORE-M5 | MEDIUM | `rules_add` reads from stdin without timeout or size limit
`rules.py:131` - `sys.stdin.read()` blocks indefinitely and reads unbounded input.

CORE-M6 | MEDIUM | Duplicate `_toml_quote` in agents.py and config_gen.py
`agents.py:57-59`, `config_gen.py:81-83` - Identical function in two modules.

CORE-M7 | MEDIUM | `_toml_multiline` doesn't escape all TOML special sequences
`agents.py:62-64` - `\n`, `\t`, `\u` in agent prompts interpreted as escape codes.

CORE-L1 | LOW | `atomic_write` tmp file name collision on concurrent writes
`helpers.py:106` - Two concurrent writes to same file share tmp path.

CORE-L2 | LOW | `_collect_rule_refs` silent fallback to `TARGET_DIR`-relative
`config_gen.py:73-77` - Different path format without logging.

CORE-L3 | LOW | Hardcoded `-system.builtin.md` exclusion in sync pruning
`sync.py:167` - Convention not enforced by type or constant.

CORE-L4 | LOW | `uninstall_run` mutates `TARGET_DIR` before validation
`commands.py:555-558` - Global mutated before `_validate_provider` can raise.

## Vaultcore & Graph

VC-H1 | HIGH | `_fix_frontmatter` drops unknown YAML keys' list items
`frontmatter.py:106-112` - Rebuild loop preserves key lines but drops `-` list entries belonging to unknown keys.

VC-H2 | HIGH | `_add_related_link` inserts before existing items
`references.py:61-67` - Appends new item after `related:` line, before existing list entries.

VC-H3 | HIGH | `_fix_frontmatter` produces bare `tags:` with no children
`frontmatter.py:84-94` - When `tags_changed=True` and `new_tags` is empty, produces `tags:` with no list.

VC-H4 | HIGH | Graph pass 2 re-reads every file from disk
`graph/api.py:348-351` - Data already available on DocNode from pass 1, doubling I/O and risking inconsistency.

VC-M1 | MEDIUM | `DocumentMetadata.validate` rejects extra feature tags
`models.py:96-102` - Requires exactly one feature tag, contradicting "extra tags allowed" rule.

VC-M2 | MEDIUM | `get_stats` silently swallows all graph exceptions
`query.py:207-209` - Bare `except Exception` masks real errors.

VC-M3 | MEDIUM | `scan_vault` does not skip `_archive` directory
`scanner.py:48-54` - Archived docs still appear in scans.

VC-M4 | MEDIUM | Each check constructs its own full `VaultGraph`
`references.py:99,104,215,220` - 3+ graph instances per `run_all_checks`, each scanning entire vault.

VC-M5 | MEDIUM | `structure._fix_filename` reports old path after rename
`structure.py:69-74` - Diagnostic uses `rel` (old path) after file rename.

VC-M6 | MEDIUM | `_inject_related` regex fragile with DOTALL
`hydration.py:136` - Non-greedy `.*?` with DOTALL creates anchoring issues.

VC-M7 | MEDIUM | Duplicate feature-tag filtering in frontmatter.py and links.py
`frontmatter.py:168-177`, `links.py:56-65` - Same logic copy-pasted.

VC-L1 | LOW | `re` imported inside function body on every call
`hydration.py:90,123,153` - Should be module-level.

VC-L2 | LOW | `_known` tuple rebuilt every loop iteration
`hydration.py:98-103` - Should be a constant.

VC-L3 | LOW | `DocNode.tags` is `set[str]` vs `DocumentMetadata.tags` is `list[str]`
`graph/api.py:85` vs `models.py:68` - Inconsistent tag ordering.

VC-L4 | LOW | `datetime.now()` used without timezone
`structure.py:75` - Could cause date inconsistencies in CI.

## MCP Server & Tests

MCP-H1 | HIGH | Path traversal in MCP `create` tool
`vault_tools.py:214-215,284,297` - `feature` input cleaned but `..` and `/`/`\` not stripped. `title` has same issue at line 198.

MCP-H2 | HIGH | Bare `except Exception` swallows graph errors
`vault_tools.py:100-101` - Silent empty rankings on any error, no logging.

MCP-M1 | MEDIUM | `test_no_duplicate_tool_names` is tautological
`test_mcp_context_budget.py:117-128` - Tests dict keys for duplicates; dicts cannot have duplicate keys.

MCP-M2 | MEDIUM | `test_console.py` uses `unittest.mock.patch`
`test_console.py:36-51` - Mocks used for terminal simulation; hard to avoid but noted.

MCP-M3 | MEDIUM | `test_install_force_proceeds_if_exists` weak assertion
`test_install.py:23-29` - Conditional assert only on failure; no positive assertion.

MCP-M4 | MEDIUM | `test_uninstall_dry_run_without_force_succeeds` ambiguous OR assertion
`test_uninstall.py:24-29` - OR condition allows vacuous pass.

MCP-M5 | MEDIUM | `test_core_uninstall_treated_as_all` weak assertion
`test_uninstall.py:33-43` - Same conditional-only pattern as M3.

MCP-M6 | MEDIUM | Global state mutation in `sync_workspace` fixture
`test_sync_manifest.py:21-51` - Mutates `_t.TARGET_DIR` and `_t.TOOL_CONFIGS` without isolation fixture.

MCP-M7 | MEDIUM | Exception swallowed in post-creation validation
`vault_tools.py:311-316` - `OSError`/`UnicodeDecodeError` silently ignored.

MCP-L1 | LOW | `__pycache__` file-name check is dead code
`builtins/__init__.py:65` - `__pycache__` is a directory; already filtered by `is_file()`.

MCP-L2 | LOW | `test_mcp_context_budget.py:63` accesses private FastMCP API
`mcp._tool_manager._tools` - Fragile, breaks on FastMCP refactor.

MCP-L3 | LOW | `test_sync_help_shows_providers` only asserts exit 0
`test_sync.py:39-42` - Name says "shows providers" but never checks output content.

MCP-L4 | LOW | `_lifespan` yields `None` instead of context dict
`app.py:32-34` - Harmless now but breaks if tools access lifespan context.

## Platform Compatibility

### Python Codebase (src/vaultspec_core/)

**Verdict: Strong cross-platform hygiene.** All platform-specific code is properly guarded.

PLAT-001 | INFO | `helpers.py` `cmd.exe /c` properly guarded
`helpers.py:136-139` - Gated behind `sys.platform == "win32"`. Confirmed correct.

PLAT-002 | INFO | `base.py` `resolve_executable` properly guarded
`protocol/providers/base.py:147-149` - Same pattern, correctly gated.

PLAT-003 | INFO | `kill_process_tree` properly bifurcated
`helpers.py:181-186` - Windows uses `taskkill`, Unix uses `pkill`+`kill`. Correct.

PLAT-004 | LOW | `pkill` may not exist on minimal Unix systems
`helpers.py:185` - `pkill` unavailable on some Alpine/BSD. `capture_output=True` prevents crash but children survive.

PLAT-005 | LOW | `subprocess.Popen(text=True)` without explicit encoding
`hooks/engine.py:347` - Uses system default encoding. On Windows `cp1252` systems, UTF-8 hook output may be garbled. Should add `encoding="utf-8"`.

PLAT-006 | LOW | Test uses hardcoded Unix path `/a/b.md`
`graph/tests/test_graph.py:40,50` - `Path("/a/b.md")` fragile on Windows though currently passes via string comparison.

PLAT-007 | LOW | Test `write_text` calls without `encoding=` parameter
`config/tests/test_workspace.py` - Several `write_text()` calls omit `encoding="utf-8"`. ASCII-only content so no breakage, but inconsistent.

PLAT-008 | INFO | No `os.path.join` - `pathlib.Path` used throughout
Clean. No string-based path construction.

PLAT-009 | INFO | No `shell=True` in subprocess calls
Clean. Avoids shell injection and platform-specific shell differences.

PLAT-010 | INFO | No Windows-only API imports
No `winreg`, `win32api`, `ctypes`, `_winapi`. Clean.

PLAT-011 | INFO | Backslash normalization applied consistently
Multiple files normalize `\\` to `/` for display/config output. Correct.

PLAT-012 | INFO | UTF-8 encoding explicitly specified in all production I/O
All production `read_text()`/`write_text()` calls specify `encoding="utf-8"`. Clean.

### Developer Tooling

PLAT-100 | HIGH | Justfile entirely POSIX-shell with no `set shell` directive
All recipes use `case`/`esac`, `$PWD`, `command -v`, `trap`, `/dev/null`. On Windows, `just` defaults to `cmd.exe`/PowerShell, breaking every recipe unless `sh` (Git Bash) is on PATH. Needs `set shell := ["bash", "-cu"]` at top.

PLAT-101 | HIGH | `$PWD` used in justfile recipes
Lines 119, 128, 137, 162 - `$PWD` unavailable in native Windows shells.

PLAT-102 | MEDIUM | `command -v` for tool detection in justfile
Lines 115, 118, 134, 138 - POSIX-only builtin.

PLAT-103 | MEDIUM | `trap` and `rm -f` in justfile `_dev-audit`
Lines 183-184 - `trap 'rm -f "$tmp"' EXIT` is bash-only. `/tmp` fallback path doesn't exist on Windows.

PLAT-104 | MEDIUM | CI lint/type/audit jobs Ubuntu-only
`.github/workflows/ci.yml:34,112-114,138` - Not inherently wrong, but tied to POSIX justfile recipes.

PLAT-105 | LOW | macOS missing from CI test matrix
`.github/workflows/ci.yml:86-88` - Matrix covers Linux + Windows, not macOS.

PLAT-106 | LOW | `/dev/null` in justfile
Lines 115, 134 - Does not exist on native Windows `cmd.exe`.

PLAT-107 | LOW | Docker volume mount syntax assumes Unix paths
Lines 119, 137 - `$PWD:/repo` may need different format on Windows Docker Desktop.
