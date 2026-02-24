---
tags:
  - "#exec"
  - "#cli-ecosystem-factoring"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-ecosystem-factoring-plan]]"
  - "[[2026-02-22-cli-ecosystem-factoring-adr]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# cli-ecosystem-factoring code review

**Status:** `REVISION REQUIRED`

## Audit Context

- **Plan:** [[2026-02-22-cli-ecosystem-factoring-plan]]
- **ADR:** [[2026-02-22-cli-ecosystem-factoring-adr]]
- **Scope:** All files created/modified across Phases 1-4:
  - `src/vaultspec/core/` (9 submodules + `__init__.py`)
  - `src/vaultspec/cli_common.py`
  - `src/vaultspec/cli.py` (slimmed)
  - `src/vaultspec/subagent_cli.py` (refactored)
  - `src/vaultspec/team_cli.py` (refactored)
  - `src/vaultspec/config/` (renamed from core)
  - `src/vaultspec/orchestration/__init__.py` (modified)

## Summary

The refactoring achieves its primary objectives: `cli.py` is reduced from 2459 to 982 lines, the 9-module `vaultspec.core` domain library is independently importable with correct dependency ordering, `cli_common.py` eliminates boilerplate duplication, and the `vaultspec.config` rename is complete. However, one critical import regression breaks the `subagent_cli` entry point, and several medium-severity issues need attention.

## Findings

### Critical / High (Must Fix)

- **[CRITICAL]** `src/vaultspec/subagent_cli.py:28` and `src/vaultspec/subagent_cli.py:170`: Import regression breaks subagent_cli entry point.

  Line 28: `from .orchestration import run_subagent` -- FAILS at import time.
  Line 170: `from .orchestration import load_agent, AgentNotFoundError` -- FAILS at runtime.

  **Root cause:** `src/vaultspec/orchestration/__init__.py` was rewritten during this refactoring (explicit imports replaced with wildcard `from .X import *` for 6 submodules). The `.subagent` module was NOT included in the wildcard list. The old code used `from vaultspec.orchestration.subagent import run_subagent` (direct module path), which bypassed `__init__.py`. The refactored code changed the import to go through `__init__.py`, which now fails.

  **Evidence:** `python -m pytest src/vaultspec/tests/cli/test_integration.py::test_cli_help` fails with:
  ```
  ImportError: cannot import name 'run_subagent' from 'vaultspec.orchestration'
  ```

  **Fix options (pick one):**
  1. Add `from .subagent import *` to `orchestration/__init__.py`
  2. Revert the import in `subagent_cli.py` to use the direct module path: `from .orchestration.subagent import run_subagent` (and similarly for `load_agent`, `AgentNotFoundError`)

  Option 2 is preferable because it matches the original behavior without expanding the `orchestration` package's public surface unnecessarily.

- **[HIGH]** `src/vaultspec/orchestration/__init__.py`: Wildcard import rewrite is out-of-scope drift.

  The plan does NOT list `orchestration/__init__.py` as a file to modify. The change from explicit imports to `from .X import *` wildcards modifies the public API surface of the `orchestration` package (adds `from .team import *`, `from .team_task_engine import *` which were not previously exported). This is architectural drift -- the refactoring was supposed to be "no behavioral changes."

  **Fix:** Revert `orchestration/__init__.py` to its committed state (explicit imports without `.subagent`) and change `subagent_cli.py` back to using direct module paths.

### Medium / Low (Recommended)

- **[MEDIUM]** `src/vaultspec/core/types.py:49`: Top-level import of `ClaudeProvider` and `GeminiProvider` creates import-time side effects.

  ```python
  from ..protocol.providers import ClaudeProvider, GeminiProvider
  PROVIDERS: dict[str, Any] = {
      "claude": ClaudeProvider(),
      "gemini": GeminiProvider(),
  }
  ```

  This instantiates provider objects at import time. The ADR acknowledges "import-time side effects persist (for now)" so this is not a blocker, but it means importing `vaultspec.core.types` triggers provider construction. The plan notes this as acceptable current behavior.

- **[MEDIUM]** `src/vaultspec/cli.py` at 982 lines, exceeds the ~700-line target stated in the plan.

  The residual file has 982 lines vs the planned ~700. The overshoot comes from `readiness_run()` (~250 lines) and `doctor_run()` (~65 lines), which are large diagnostic commands that were planned to remain in `cli.py`. The plan's estimate was approximate, so this is acceptable but worth noting.

- **[MEDIUM]** `src/vaultspec/tests/cli/test_vault_cli.py:6,40-48`: Test file references `_get_version()` in docstrings/comments.

  The test class `TestGetVersion` and its docstrings still reference `_get_version()` (the old function name). The actual test code correctly imports from `cli_common.get_version`. These are cosmetic but misleading.

- **[LOW]** `src/vaultspec/core/system.py:19-22`: Retained `except ImportError` for `skills_ref.prompt`.

  ```python
  try:
      from skills_ref.prompt import to_prompt
  except ImportError:
      to_prompt = None
  ```

  This is the legitimate optional-dependency guard that the plan explicitly says to keep. Verified correct.

- **[LOW]** `src/vaultspec/core/helpers.py:69`: Defensive `except (ImportError, KeyError, AttributeError)` in `resolve_model()`.

  The `ImportError` catch for `CapabilityLevel` import is arguably unnecessary since `protocol.providers` is a first-party module. However, this was present in the original code and the plan says "no behavioral changes," so preserving it is correct.

- **[LOW]** No tests exist under `src/vaultspec/core/tests/`. The plan did not call for new tests (relying on existing CLI tests for verification), so this is expected. Future work should add unit tests for the core domain library.

## Verification Results

### Tests
- `python -m pytest src/vaultspec/tests/cli/ -x -q` -- **1 FAILED** (`test_cli_help` -- the `run_subagent` ImportError)
- `python -m pytest src/vaultspec/tests/cli/ -q --ignore=test_integration.py` -- **168 PASSED**
- `python -m pytest src/vaultspec/config/tests/ -x -q` -- **87 PASSED**

### Structural Checks
- `wc -l src/vaultspec/cli.py` = **982** (target ~700, overshoot ~40%)
- `ls src/vaultspec/core/` = 9 submodules + `__init__.py` + `tests/` + `__pycache__/` -- **PASS**
- `ls src/vaultspec/cli_common.py` = exists, 227 lines -- **PASS**

### Import Integrity
- `from vaultspec.cli import main` -- **PASS**
- `import vaultspec.cli as cli; cli.ROOT_DIR` -- **PASS** (returns workspace root)
- `from vaultspec.core.rules import collect_rules` -- **PASS**
- `from vaultspec.core.agents import collect_agents` -- **PASS**
- `from vaultspec.core.types import ToolConfig, SyncResult` -- **PASS**
- `from vaultspec.config import get_config, WorkspaceLayout` -- **PASS**
- All 9 core submodules individually importable -- **PASS**
- `cli_common.py` importable without side effects -- **PASS**

### Antipattern Verification
- `rg "except ImportError" src/vaultspec/core/` -- **1 result** (`core/system.py` -- the legitimate `skills_ref.prompt` guard)
- `rg "PROVIDERS = {}" src/vaultspec/` -- **ZERO results** -- **PASS**
- `sys.exit(1)` import guards in `subagent_cli.py` / `team_cli.py` -- **REMOVED** -- **PASS**
- `_get_version` in `src/vaultspec/*.py` (non-test) -- **ZERO results** -- **PASS**

### Dependency Graph
- `types.py`: imports from `..protocol.providers` (external to core) -- leaf module -- **PASS**
- `helpers.py`: imports only stdlib + `yaml` -- **PASS**
- `sync.py`: imports from `.helpers`, `.types` -- **PASS**
- `rules.py`: imports from `.helpers`, `.sync`, `.types` -- **PASS**
- `agents.py`: imports from `.helpers`, `.sync`, `.types` -- **PASS**
- `skills.py`: imports from `.helpers`, `.sync`, `.types` -- **PASS**
- `config_gen.py`: imports from `.helpers`, `.rules`, `.sync`, `.types` -- **PASS**
- `system.py`: imports from `.agents`, `.config_gen`, `.helpers`, `.skills`, `.sync`, `.types` -- **PASS**
- `resources.py`: imports from `.helpers`, `.skills`, `.types` -- **PASS**
- DAG: types <- helpers <- sync <- rules/agents/skills <- config_gen/system/resources -- **NO CYCLES**

### Code Quality
- No mock usage in any new code -- **PASS**
- No dead code or leftover comments referencing old locations -- **PASS** (except test docstrings)
- Proper relative imports within core/ package -- **PASS**
- `import html` moved to top-level in `system.py:6` -- **PASS** (Phase 4 requirement met)

## Recommendations

1. **[MUST FIX]** Fix the `subagent_cli.py` import regression. Change line 28 to `from .orchestration.subagent import run_subagent` and line 170 to `from .orchestration.subagent import load_agent, AgentNotFoundError`. This restores the original direct-module import path.

2. **[MUST FIX]** Revert `orchestration/__init__.py` to its last committed state. The wildcard-import rewrite is out-of-scope for this refactoring.

3. **[RECOMMENDED]** Update `test_vault_cli.py` docstrings/comments to reference `get_version()` instead of `_get_version()`.

4. **[FUTURE]** Add unit tests under `src/vaultspec/core/tests/` for the domain library.

## Notes

The refactoring is structurally sound. The core domain library has a clean dependency DAG, all modules are independently importable, backward compatibility via `__getattr__` in `cli.py` works correctly, and the antipattern deletions are complete. The single blocking issue is the `orchestration/__init__.py` modification which broke `subagent_cli`. Once that is fixed, this passes review.
