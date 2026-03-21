---
tags:
  - '#plan'
  - '#workspace-paths'
date: '2026-02-19'
related:
  - '[[2026-02-19-workspace-path-decoupling-adr]]'
  - '[[2026-02-19-workspace-path-decoupling-research]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `workspace-paths` `implementation` plan

Implement three-path workspace decoupling with git-aware layout detection, as
specified in \[[2026-02-19-workspace-path-decoupling-adr]\]. The work delivers
all 8 items from the ADR's deliverables table, organized into 3 phases.

## Proposed Changes

Decouple VaultSpec's path handling from a single `ROOT_DIR` into three
independent roots (`content_root`, `output_root`, `framework_root`) via a new
`core/workspace.py` module. Add git-aware layout detection for standalone
worktree support. Update all three CLIs with `--content-dir` flag. Fix stale
`requirements.txt` and add `extension.toml` for companion project discovery.

All changes follow the \[[2026-02-19-workspace-path-decoupling-adr]\] resolution
matrix and bootstrap ordering constraints.

## Tasks

- `Phase 1: Core Module + Config` — Foundation with no external impact

  1. **Create `core/workspace.py`** — New file at `.vaultspec/lib/src/core/workspace.py`. Implement `LayoutMode` enum (`STANDALONE`, `EXPLICIT`), `GitInfo` frozen dataclass, `WorkspaceLayout` frozen dataclass, `discover_git()` function, `_parse_git_pointer()` helper, `_walk_up_for_git()` helper, `resolve_workspace()` function, and `_validate()` function. Stdlib only. Follow the ADR's data types, resolution matrix (6 rows), and validation rules. `framework_root` parameter is accepted from caller, never derived from env vars. ~250 lines.
  1. **Add `content_dir` to `core/config.py`** — Add `content_dir: Path | None = None` field to `VaultSpecConfig` dataclass (after `root_dir`). Add corresponding `ConfigVariable` entry to `CONFIG_REGISTRY` with `env_name="VAULTSPEC_CONTENT_DIR"`, `var_type=Path`, `default=None`.
  1. **Create `core/tests/test_workspace.py`** — New file at `.vaultspec/lib/src/core/tests/test_workspace.py`. Unit tests using `tmp_path` and `monkeypatch` fixtures for: standard `.git/` directory, `.git` file (worktree gitdir pointer), `.gt/` container mode (CWD in worktree), `.gt/` container mode (CWD at container root), no git (structural fallback), EXPLICIT mode (both env vars set), vault_root follows output_root semantics (`output_root / .vault` in every case), validation errors (missing content_root, missing `framework_root/lib`), `framework_root` from structural not env vars. ~200 lines.

- `Phase 2: Bootstrap + CLI Integration` — Wire the module into entry points

  1. **Update `_paths.py`** — Rewrite `.vaultspec/lib/scripts/_paths.py`. Preserve the two-step bootstrap: Step 1 computes `_SCRIPTS_DIR`, `_LIB_DIR`, `_FRAMEWORK_ROOT`, `LIB_SRC_DIR` structurally and adds to `sys.path`. Step 2 imports `resolve_workspace` and calls it with env var overrides and `framework_root=_FRAMEWORK_ROOT`. Export `ROOT_DIR = _layout.output_root` and `LIB_SRC_DIR` as before. Add `_env_path()` helper.
  1. **Update `cli.py` `init_paths()`** — Change signature from `init_paths(root: Path)` to `init_paths(layout: WorkspaceLayout)`. Source dirs (`RULES_SRC_DIR`, `AGENTS_SRC_DIR`, `SKILLS_SRC_DIR`, `SYSTEM_SRC_DIR`, `FRAMEWORK_CONFIG_SRC`, `PROJECT_CONFIG_SRC`, `CONSTITUTION_SRC`, `HOOKS_DIR`) derived from `layout.content_root`. Output dirs in `TOOL_CONFIGS` derived from `layout.output_root`. Update the default initialization call at module level. Update `main()` to build a `WorkspaceLayout` via `resolve_workspace()` when `--root` or `--content-dir` is provided. Add `--content-dir` argument to the top-level parser.
  1. **Update `subagent.py`** — Add `--content-dir` argument. In the `main()` function, use `resolve_workspace()` with `root_override=args.root` and `content_override=args.content_dir` where root is currently passed directly.
  1. **Update `vault.py`** — Add `--content-dir` argument to all subcommand parsers that accept `--root`. Pass through to `resolve_workspace()` at each command entry point where `root_dir` is resolved.

- `Phase 3: Packaging + Extension Manifest` — Non-code deliverables

  1. **Fix `requirements.txt`** — Update to match `pyproject.toml` runtime deps. Change `mcp>=0.1.0` to `mcp>=1.20.0`. Add missing: `claude-agent-sdk>=0.1.30`, `sse-starlette>=1.0.0`. Remove dev-only deps from the main list (they belong in `pyproject.toml [project.optional-dependencies]` only).
  1. **Create `extension.toml`** — New file at repo root. Follow the schema from ADR-006: `[extension]` (name, version, description), `[requires.python]` (version), `[runtime]` (type, install), `[entry_points]` (cli, mcp), `[provides]` (mcp, content_types), `[outputs]` (claude_dir, gemini_dir, agent_dir, agents_md).

## Parallelization

- **Phase 1 steps can run in parallel.** Step 1 (workspace.py), step 2 (config.py edit), and step 3 (tests) are independent. The tests import workspace.py but writing both simultaneously is fine — tests validate post-write.
- **Phase 2 steps are sequential.** `_paths.py` must be updated first (step 1) since all CLIs import from it. Then cli.py (step 2), then subagent.py + vault.py (steps 3-4) which follow the same pattern.
- **Phase 3 steps are independent** of each other and of Phase 2. Can run in parallel with Phase 2 if desired.

**Recommended team allocation:**

- The coding agent handles Phase 1 (all 3 steps) then Phase 2 (all 4 steps) sequentially.
- The coding agent handles Phase 3 in parallel or after Phase 2.
- The test runner validates after Phase 1 (unit tests) and after Phase 2 (integration — existing CLI tests still pass).
- The auditor reviews the final output.

## Verification

- **Unit tests pass:** `core/tests/test_workspace.py` covers all 6 resolution matrix rows plus validation and edge cases.
- **Existing tests pass:** Existing CLI tests in `.vaultspec/lib/tests/cli/` must still pass — backwards compatibility for standalone mode.
- **Standalone behavior unchanged:** Running `cli.py sync-all` with no env vars produces identical output to before the change.
- **EXPLICIT mode works:** Setting `VAULTSPEC_ROOT_DIR=/tmp/out VAULTSPEC_CONTENT_DIR=/tmp/content` with appropriately scaffolded directories resolves to the expected paths.
- **Bootstrap ordering correct:** `_paths.py` computes `LIB_SRC_DIR` structurally before importing `core.workspace`. `framework_root` in `WorkspaceLayout` always reflects the physical script location.
- **No new dependencies:** `core/workspace.py` uses only stdlib. Confirmed via import audit.
- **`requirements.txt` matches `pyproject.toml`:** Runtime deps are aligned. Version constraints match.
- **`extension.toml` validates:** The companion project can parse it (structural, not runtime-tested here).
