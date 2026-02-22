---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#plan"
  - "#cli-ecosystem-factoring"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-ecosystem-factoring-adr]]"
  - "[[2026-02-22-cli-ecosystem-factoring-research]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# cli-ecosystem-factoring plan

Restructure the vaultspec CLI ecosystem in four phases: rename `vaultspec.core`
to `vaultspec.config`, extract shared CLI boilerplate into `cli_common.py`,
decompose the 2459-line `cli.py` monolith into a `vaultspec.core` domain
library, and delete import-fallback antipatterns. The refactoring is purely
structural -- no behavioral changes.

## Proposed Changes

This plan implements the four phases defined in
[[2026-02-22-cli-ecosystem-factoring-adr]]. Each phase is independently
committable and verifiable via the existing test suite. Phases 1 and 2 have no
ordering dependency and can execute in parallel. Phases 3 and 4 depend on
Phase 1 completing first (Phase 3 needs the `vaultspec.core` namespace freed;
Phase 4 acts on files produced by Phase 3).

The research at [[2026-02-22-cli-ecosystem-factoring-research]] provides the
exhaustive inventory of duplication sites, import counts, and antipattern
locations that ground every step below.

### Scope boundary

- No behavioral changes -- identical output before and after each phase
- No new dependencies
- No changes to `pyproject.toml` entry points
- Import-time side effects persist (deferring to CLIContext is future work)
- `from vaultspec.cli import main` and `import vaultspec.cli as cli; cli.ROOT_DIR`
  must keep working after Phase 3

## Tasks

<!-- IMPORTANT: This document must be updated between execution runs to
     track progress. -->

### Phase 1: Rename `vaultspec.core` to `vaultspec.config`

**Executor:** `vaultspec-standard-executor` (mechanical find-and-replace rename)

**Depends on:** nothing

**Goal:** Free the `vaultspec.core` namespace for the domain library (Phase 3)
and align the configuration package name with its contents.

1. Generate the exhaustive file list

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase1-step1.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]], [[2026-02-22-cli-ecosystem-factoring-research]]
- Run `rg "from vaultspec\.core" src/ tests/` and capture the full list of 36
  files (34 in `src/vaultspec/`, 2 in `tests/`). Record this list in the step
  record as the source-of-truth manifest for the rename. Include three conftest
  files (`graph/tests/conftest.py`, `metrics/tests/conftest.py`,
  `verification/tests/conftest.py`), both `tests/conftest.py` and
  `tests/test_config.py`, plus the `core/tests/` internal imports.

2. Rename directory and move tests

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase1-step2.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]]
- Rename `src/vaultspec/core/` to `src/vaultspec/config/`. This moves:
  - `core/__init__.py` -> `config/__init__.py`
  - `core/config.py` -> `config/config.py`
  - `core/workspace.py` -> `config/workspace.py`
  - `core/tests/` -> `config/tests/` (including `__init__.py`, `conftest.py`,
    `test_config.py`, `test_workspace.py`)
- Update the docstring in `config/__init__.py` from "Core configuration and
  types" to "Configuration and workspace types for vaultspec."
- Update internal imports in `config/tests/test_config.py` and
  `config/tests/test_workspace.py` from `vaultspec.core.*` to
  `vaultspec.config.*`.

3. Update all 36 consuming files

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase1-step3.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-research]] section 4
- Replace `vaultspec.core` with `vaultspec.config` in all 57 import sites
  across 36 files. The three import patterns are:
  - `from vaultspec.core import <names>` -> `from vaultspec.config import <names>`
  - `from vaultspec.core.config import <names>` -> `from vaultspec.config.config import <names>`
  - `from vaultspec.core.workspace import <names>` -> `from vaultspec.config.workspace import <names>`
- Files by category:
  - CLI modules (4): `cli.py`, `subagent_cli.py`, `team_cli.py`, `vault_cli.py`
  - Server (2): `server.py`, `subagent_server/server.py`
  - RAG (5): `rag/api.py`, `rag/embeddings.py`, `rag/indexer.py`,
    `rag/search.py`, `rag/store.py`
  - Protocol (6): `protocol/acp/client.py`, `protocol/acp/claude_bridge.py`,
    `protocol/a2a/agent_card.py`, `protocol/a2a/discovery.py`,
    `protocol/providers/gemini.py`, `protocol/a2a/tests/test_agent_card.py`
  - Orchestration (4): `orchestration/subagent.py`,
    `orchestration/session_logger.py`, `orchestration/task_engine.py`,
    `orchestration/tests/test_session_logger.py`
  - Vaultcore (3): `vaultcore/hydration.py`, `vaultcore/models.py`,
    `vaultcore/scanner.py`, `vaultcore/tests/test_scanner.py`
  - Hooks (1): `hooks/engine.py`
  - Verification (1): `verification/api.py`
  - Test conftest files (3): `graph/tests/conftest.py`,
    `metrics/tests/conftest.py`, `verification/tests/conftest.py`
  - CLI tests (1): `tests/cli/test_integration.py`
  - Top-level tests (2): `tests/conftest.py`, `tests/test_config.py`

4. Place deprecation shim at `src/vaultspec/core/__init__.py`

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase1-step4.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]] (backward compatibility
  section)
- Create `src/vaultspec/core/__init__.py` as a deprecation shim that emits a
  `DeprecationWarning` and re-exports everything from `vaultspec.config`.
  This catches any missed references at runtime instead of hard-failing.

5. Run full test suite and verify

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase1-step5.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]] (constraints section)
- Run `python -m pytest src/ tests/ -x -q` and confirm all tests pass.
- Run `rg "from vaultspec\.core" src/ tests/ --glob '!src/vaultspec/core/__init__.py'`
  and confirm zero results (all first-party code migrated).
- Single atomic commit for the entire phase.

**Phase 1 verification criteria:**
- Zero test failures
- Zero `vaultspec.core` imports in first-party code (excluding deprecation shim)
- `from vaultspec.core import get_config` still works (via shim) with a
  `DeprecationWarning`
- `from vaultspec.config import get_config` works without warning

---

### Phase 2: Extract shared CLI foundation (`vaultspec.cli_common`)

**Executor:** `vaultspec-standard-executor` (extract + refactor with clear patterns)

**Depends on:** nothing (independent of Phase 1)

**Goal:** Eliminate boilerplate duplication across all four CLI entry points.

1. Create `src/vaultspec/cli_common.py` with shared functions

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase2-step1.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-research]] sections 2.1-2.7,
  [[2026-02-22-cli-ecosystem-factoring-adr]] (Phase 2)
- Create `src/vaultspec/cli_common.py` (~120 lines) containing these 6 functions:
  - `get_version(root_dir=None) -> str` -- unified version reader using the
    `vault_cli.py` signature (the most flexible variant). Reads `pyproject.toml`
    line-scanning, returns `"unknown"` on failure.
  - `add_common_args(parser) -> None` -- adds `--root`, `--content-dir`,
    `--verbose`/`-v`, `--debug`, `--version`/`-V` to any `ArgumentParser`.
  - `setup_logging(args, default_format=None) -> None` -- encapsulates the
    `configure_logging()` + conditional `reset_logging()` dance. Reads
    `args.debug` and `args.verbose`. Accepts optional `default_format` for
    `subagent_cli.py`'s `"%(message)s"` case.
  - `resolve_args_workspace(args, default_layout) -> WorkspaceLayout` -- post-parse
    workspace re-resolution when `--root` or `--content-dir` overrides are present.
    Sets `args.root` and `args.content_root`.
  - `run_async(coro, *, debug=False) -> T` -- wraps `asyncio.run()` with Windows
    `ProactorEventLoopPolicy`, `ResourceWarning` suppression, and the
    `asyncio.sleep(0.250)` pipe cleanup workaround from `subagent_cli.py`. Returns
    the coroutine result.
  - `cli_error_handler(debug) -> ContextManager` -- context manager that catches
    exceptions, logs them, prints traceback if `debug=True`, and calls
    `sys.exit(1)`.
- The module must be importable without side effects (no import-time workspace
  resolution, no `configure_logging()` calls).

2. Refactor `cli.py` to use `cli_common`

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase2-step2.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-research]] sections 2.1-2.5
- Replace `cli.py`'s `_get_version()` (line 263) with
  `from vaultspec.cli_common import get_version`.
- Replace the 4 common argparse argument definitions in `main()` with
  `add_common_args(parser)`.
- Replace the logging setup block (lines 2346-2354) with
  `setup_logging(args)`.
- Replace the post-parse workspace re-resolution (lines 2356-2362) with
  `resolve_args_workspace(args, _default_layout)` followed by
  `init_paths(layout)`.

3. Refactor `subagent_cli.py` to use `cli_common`

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase2-step3.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-research]] sections 2.1-2.7
- Replace `_get_version()` (line 29), common args, logging setup (lines 439-447),
  workspace re-resolution (lines 424-434), manual event loop management
  (lines 137-180), and the try/except scaffold with `cli_common` equivalents.
- The manual `asyncio.new_event_loop()` + `set_event_loop()` pattern is replaced
  by `run_async(coro, debug=args.debug)`.
- The `ResourceWarning` filter at line 452 is removed (handled by `run_async`).

4. Refactor `team_cli.py` to use `cli_common`

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase2-step4.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-research]] sections 2.1-2.6
- Replace `_get_version()` (line 33), common args, logging setup (lines 571-579),
  workspace re-resolution (lines 558-568).
- Replace all 6 async try/except scaffolds (lines 201-216, 259-270, 284-296,
  345-356, 379-392, 414-440) with `run_async()` + `cli_error_handler()`.
- Each async command's local `async def _fn()` closure is preserved; only the
  wrapping boilerplate changes.

5. Refactor `vault_cli.py` to use `cli_common`

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase2-step5.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-research]] sections 2.1-2.4
- Replace `_get_version(root_dir=None)` (line 31), common args, and logging
  setup (lines 180-185) with `cli_common` equivalents.
- `vault_cli.py` has no async operations and uses a per-command `_resolve_root()`
  helper instead of `resolve_args_workspace()`. The `_resolve_root()` helper can
  remain since it follows a different pattern, or be replaced if
  `resolve_args_workspace()` covers its use case.

6. Run full test suite and verify

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase2-step6.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]] (constraints section)
- Run `python -m pytest src/ tests/ -x -q` and confirm all tests pass.
- Verify that `_get_version` no longer exists in any CLI module
  (`rg "_get_version" src/vaultspec/`).
- Verify `cli_common.py` has no import-time side effects (import it in an
  isolated Python process and confirm no workspace resolution occurs).

**Phase 2 verification criteria:**
- Zero test failures
- No `_get_version` function in any CLI module
- All four CLI modules import from `cli_common` for shared infrastructure
- `cli_common.py` importable without side effects
- Net line reduction of ~10-40 lines across the four CLI modules

---

### Phase 3: Extract business logic from `cli.py` into `vaultspec.core`

**Executor:** `vaultspec-complex-executor` (architectural restructure requiring
precise dependency ordering and function-by-function extraction)

**Depends on:** Phase 1 (the `vaultspec.core` namespace must be freed)

**Goal:** Make the resource management library independently importable and
testable, separate from the CLI layer. Reduce `cli.py` from ~2459 lines to
~700 lines.

1. Create `core/types.py` -- leaf module with no internal deps

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase3-step1.md`)
- Executing sub-agent: `vaultspec-complex-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]] (Phase 3, dependency graph)
- Create `src/vaultspec/core/types.py` (~100 lines). Move from `cli.py`:
  - `ToolConfig` dataclass (line 152)
  - `SyncResult` dataclass (line 278)
  - `init_paths()` function (line 175) and the 13 module-level `Path` globals
    (`ROOT_DIR`, `RULES_SRC_DIR`, `AGENTS_SRC_DIR`, `SKILLS_SRC_DIR`,
    `SYSTEM_SRC_DIR`, `TEMPLATES_DIR`, `FRAMEWORK_CONFIG_SRC`,
    `PROJECT_CONFIG_SRC`, `HOOKS_DIR`) plus `TOOL_CONFIGS` dict
  - `PROTECTED_SKILLS` set (line 134)
  - `CONFIG_HEADER` string (line 139)
- In `cli.py`, replace the moved code with imports from `vaultspec.core.types`.
  Re-export `ROOT_DIR`, `init_paths`, `ToolConfig` etc. at module level so that
  `import vaultspec.cli as cli; cli.ROOT_DIR` continues to work.

2. Create `core/helpers.py` -- depends on types

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase3-step2.md`)
- Executing sub-agent: `vaultspec-complex-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]] (Phase 3, module
  decomposition table)
- Create `src/vaultspec/core/helpers.py` (~80 lines). Move from `cli.py`:
  - `build_file()` -- builds content from frontmatter + body
  - `atomic_write()` -- safe file write with temp + rename
  - `ensure_dir()` -- `mkdir -p` equivalent
  - `resolve_model()` -- resolves tier to concrete model name
  - `_yaml_load()`, `_yaml_dump()`, `_LiteralStr`, `_literal_representer`
    (the YAML handling functions -- keep only the `yaml` branch, the fallback
    is deleted in Phase 4)
- Imports only from `vaultspec.core.types` (for `PROVIDERS` in
  `resolve_model()`).

3. Create `core/sync.py` -- depends on types, helpers

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase3-step3.md`)
- Executing sub-agent: `vaultspec-complex-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]] (Phase 3, dependency graph)
- Create `src/vaultspec/core/sync.py` (~140 lines). Move from `cli.py`:
  - `sync_files()` (line 875) -- the core file-sync engine
  - `sync_skills()` (line 933) -- skill-specific sync logic
  - `print_summary()` -- sync result reporting

4. Create `core/rules.py`, `core/agents.py`, `core/skills.py`

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase3-step4.md`)
- Executing sub-agent: `vaultspec-complex-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]] (Phase 3)
- Create three resource modules, each ~100-130 lines. All depend on
  `types`, `helpers`, and `sync`.
  - `core/rules.py`: `collect_rules`, `transform_rule`, `rules_list`,
    `rules_add`, `rules_sync`
  - `core/agents.py`: `collect_agents`, `transform_agent`, `agents_list`,
    `agents_add`, `agents_set_tier`, `agents_sync`
  - `core/skills.py`: `collect_skills`, `transform_skill`, `skill_dest_path`,
    `skills_list`, `skills_add`, `skills_sync`

5. Create `core/config_gen.py` and `core/system.py`

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase3-step5.md`)
- Executing sub-agent: `vaultspec-complex-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]] (Phase 3, dependency graph)
- Create `core/config_gen.py` (~160 lines). Depends on `types`, `helpers`,
  `rules` (for `collect_rules`):
  - `_collect_rule_refs`, `_xml_to_heading`, `_generate_agents_md`,
    `_generate_config`, `_is_cli_managed`, `config_show`, `config_sync`
- Create `core/system.py` (~200 lines). Depends on `types`, `helpers`,
  `agents`, `skills` (for `collect_*` and listing assembly):
  - `collect_system_parts`, `_collect_agent_listing`, `_collect_skill_listing`,
    `_generate_system_prompt`, `_generate_system_rules`, `system_show`,
    `system_sync`

6. Create `core/resources.py`

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase3-step6.md`)
- Executing sub-agent: `vaultspec-complex-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]] (Phase 3)
- Create `core/resources.py` (~120 lines). Depends on `types`, `helpers`,
  `skills` (for `skill_dest_path`):
  - `resource_show`, `resource_edit`, `resource_remove`, `resource_rename`

7. Create `core/__init__.py` with public API re-exports

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase3-step7.md`)
- Executing sub-agent: `vaultspec-complex-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]] (Phase 3)
- Create `src/vaultspec/core/__init__.py` (~20 lines) that re-exports the
  public API from all submodules. This replaces the Phase 1 deprecation shim.
  The shim at `src/vaultspec/core/__init__.py` is removed since the namespace
  is now reclaimed.
- Note: The Phase 1 deprecation shim re-exported from `vaultspec.config`.
  The new `core/__init__.py` re-exports from the `core/*` submodules. Code that
  previously did `from vaultspec.core import get_config` (via the shim) will
  break unless the new `core/__init__.py` also re-exports the config symbols.
  Decision: The new `core/__init__.py` should NOT re-export config symbols.
  The deprecation shim served its purpose during Phase 1; consumers must use
  `vaultspec.config` for config symbols and `vaultspec.core` for domain symbols.

8. Slim down `cli.py` to thin wrapper

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase3-step8.md`)
- Executing sub-agent: `vaultspec-complex-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]] (backward compatibility)
- Replace all extracted function bodies in `cli.py` with imports from
  `vaultspec.core.*`. The file retains:
  - argparse parser construction
  - `add_sync_flags()` helper
  - `main()` dispatch function
  - `init_run()`, `hooks_list()`, `hooks_run()` (CLI-only operations)
  - `test_run()`, `doctor_run()`, `readiness_run()` (diagnostic commands)
- Re-export key symbols at module level for backward compatibility:
  `ROOT_DIR`, `init_paths`, `ToolConfig`, `SyncResult`, `collect_rules`,
  `collect_agents`, `collect_skills`, etc. -- so that
  `import vaultspec.cli as cli; cli.ROOT_DIR` continues to work.
- Target residual size: ~700 lines.

9. Update `src/vaultspec/tests/cli/conftest.py` and test imports

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase3-step9.md`)
- Executing sub-agent: `vaultspec-complex-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]]
- `src/vaultspec/tests/cli/conftest.py` imports `vaultspec.cli` and uses
  `cli.init_paths()` and `cli.ROOT_DIR`. These re-exports must work after
  Phase 3. Verify all CLI test files still pass. If any test imports moved
  functions directly (e.g., `from vaultspec.cli import collect_rules`), update
  them to use `from vaultspec.core.rules import collect_rules` or confirm the
  re-export in `cli.py` covers them.

10. Run full test suite and verify

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase3-step10.md`)
- Executing sub-agent: `vaultspec-complex-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]] (constraints section)
- Run `python -m pytest src/ tests/ -x -q` and confirm all tests pass.
- Verify `cli.py` line count is ~700 lines (`wc -l src/vaultspec/cli.py`).
- Verify the dependency graph has no cycles: each `core/*.py` module imports
  only from modules above it in the DAG (`types` <- `helpers` <- `sync` <-
  `rules`/`agents`/`skills` <- `config_gen`/`system`/`resources`).
- Verify backward compatibility: `python -c "import vaultspec.cli as cli; print(cli.ROOT_DIR)"`.

**Phase 3 verification criteria:**
- Zero test failures
- `cli.py` reduced to ~700 lines
- All `core/*.py` modules independently importable
  (`python -c "from vaultspec.core.rules import collect_rules"`)
- No circular imports in the `core/` package
- Backward compatibility: `vaultspec.cli.ROOT_DIR`, `vaultspec.cli.main`,
  `vaultspec.cli.init_paths` all resolve

---

### Phase 4: Delete import-fallback antipatterns

**Executor:** `vaultspec-simple-executor` (delete dead code, minimal judgment)

**Depends on:** Phase 3 (file locations change after extraction)

**Goal:** Remove dead code and silent degradation paths that mask installation
errors.

1. Delete fallback YAML parser

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase4-step1.md`)
- Executing sub-agent: `vaultspec-simple-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-research]] section 3.6.1
- After Phase 3, the YAML functions live in `core/helpers.py`. Delete the
  `except ImportError` branch (the 50-line fallback parser). Import `yaml`
  unconditionally. `PyYAML>=6.0` is a declared core dependency in
  `pyproject.toml`.

2. Delete silent `PROVIDERS = {}` fallback and fix logger NameError

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase4-step2.md`)
- Executing sub-agent: `vaultspec-simple-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-research]] section 3.6.2
- After Phase 3, the `PROVIDERS` dict and its import live in `core/types.py`
  (or `core/agents.py` depending on Phase 3 placement). Delete the
  `except ImportError: PROVIDERS = {}` branch. Import `ClaudeProvider` and
  `GeminiProvider` unconditionally. This also eliminates the `logger`
  NameError bug (line 129 referencing `logger` before line 136 defines it).

3. Move `import html` to top-level stdlib imports

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase4-step3.md`)
- Executing sub-agent: `vaultspec-simple-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-research]] section 3.6.3
- After Phase 3, the `import html` lives in whichever `core/*.py` module
  contains `_collect_skill_listing` (likely `core/system.py`). Move it to the
  top-level stdlib imports section. Keep the `skills_ref.prompt` try/except
  as-is (genuinely optional).

4. Delete `sys.exit(1)` guards in `subagent_cli.py` and `team_cli.py`

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase4-step4.md`)
- Executing sub-agent: `vaultspec-simple-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-research]] section 3.6.5
- In `subagent_cli.py` (lines 38-46): remove the `try/except ImportError`
  around `from vaultspec.orchestration.subagent import ...`. Import directly.
- In `team_cli.py` (lines 41-53): remove the `try/except ImportError` around
  `from vaultspec.orchestration.team import ...`. Import directly.
- These are first-party imports. Let `ImportError` propagate with full traceback
  if the installation is broken.

5. Run full test suite and verify

- Step summary: (`.vault/exec/2026-02-22-cli-ecosystem-factoring/2026-02-22-cli-ecosystem-factoring-phase4-step5.md`)
- Executing sub-agent: `vaultspec-simple-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]] (constraints section)
- Run `python -m pytest src/ tests/ -x -q` and confirm all tests pass.
- Verify no fallback import patterns remain:
  `rg "except ImportError" src/vaultspec/core/` should return zero results.
- Verify the `logger` NameError bug is resolved.

**Phase 4 verification criteria:**
- Zero test failures
- No `except ImportError` in `core/*.py` (all core deps are unconditional)
- No `sys.exit(1)` guards around first-party imports in `subagent_cli.py`
  or `team_cli.py`
- Legitimate guards preserved: `skills_ref.prompt` in `core/system.py`,
  `doctor_run`/`readiness_run` in `cli.py`, RAG imports in `vault_cli.py`

## Parallelization

**Phases 1 and 2 are fully independent** and can execute in parallel via
separate sub-agent dispatches. They touch different files and different
concerns (Phase 1 = rename imports, Phase 2 = extract shared boilerplate).

**Phase 3 depends on Phase 1** completing first. The `vaultspec.core` namespace
must be freed (renamed to `vaultspec.config`) before Phase 3 can create the new
`vaultspec.core` domain library in that namespace.

**Phase 4 depends on Phase 3** completing first. The antipatterns move to new
file locations during Phase 3; Phase 4 deletes them at their final locations.

**Execution timeline:**

```
Time ->
Phase 1 =====>
Phase 2 =====>
                Phase 3 =============>
                                       Phase 4 ===>
```

Within Phase 3, steps 1-3 are sequential (each builds on the previous), but
step 4 (rules, agents, skills) can be done as a batch since those three modules
are at the same level in the dependency graph. Steps 5-6 (config_gen, system,
resources) similarly form a batch at the next DAG level.

## Verification

**Per-phase gate:** Each phase must pass `python -m pytest src/ tests/ -x -q`
before the next phase begins. This is the primary verification mechanism since
the ADR mandates zero behavioral changes.

**Post-completion audit:**
- Verify `cli.py` line count dropped from ~2459 to ~700
- Verify `vaultspec.core` contains 9 submodules with correct dependency ordering
- Verify `cli_common.py` has no import-time side effects
- Verify all entry points (`vaultspec`, `vaultspec-vault`, `vaultspec-team`,
  `vaultspec-subagent`) still work: `vaultspec --version`, `vaultspec-vault --version`,
  `vaultspec-team --version`, `vaultspec-subagent --version`
- Verify backward compatibility: `python -c "from vaultspec.cli import main"`,
  `python -c "import vaultspec.cli as cli; print(cli.ROOT_DIR)"`
- Run `rg "except ImportError" src/vaultspec/core/` to confirm all antipatterns
  are deleted (should return zero results)
- Manual inspection: confirm the `logger` NameError bug at the former
  `cli.py:129` is eliminated

**Limitation:** This is a structural refactoring. Behavioral correctness is
verified by the existing test suite. There is no new functionality to test
beyond import-path resolution and module importability. If the test suite has
coverage gaps (e.g., untested functions in `cli.py`), those gaps persist. A
follow-up coverage audit may be warranted but is out of scope for this plan.
