---
tags:
  - '#exec'
  - '#packaging-restructure'
date: '2026-02-21'
related:
  - '[[2026-02-21-packaging-restructure-p1p2-plan]]'
  - '[[2026-02-21-packaging-restructure-adr]]'
  - '[[2026-02-21-packaging-restructure-research]]'
---

# `packaging-restructure` Phase 1 code review

**Status:** `REVISION REQUIRED`

## Audit Context

- **Plan:** `[[2026-02-21-packaging-restructure-p1p2-plan]]`
- **Scope:** Steps 14-17 (Phase 1 verification stream D). Covers editable install, test suite, CLI entry points, MCP server importability, bare-import elimination, and packaging config.

## Step Results

### Step 14: `uv sync --dev` -- CONDITIONAL PASS

`uv sync --extra dev` succeeds and `import vaultspec` resolves correctly. However, `uv sync --dev` (the documented command) does NOT install dev dependencies because `pyproject.toml` uses `[project.optional-dependencies].dev` instead of `[dependency-groups].dev`. The `--dev` flag in uv corresponds to dependency groups, not extras. See HIGH finding below.

- `uv sync --extra dev` -- installed 16 dev packages, no errors
- `uv run python -c "import vaultspec; print('OK')"` -- OK
- Package installed as editable at `Y:\code\vaultspec-worktrees\main`
- `src/vaultspec/` on `sys.path` via hatchling wheel build

### Step 15: `uv run pytest` -- FAIL

792 passed, 142 failed, 86 errors, 86 skipped, 65 deselected (in 27s).

All 142 failures and 86 errors trace to **12 missed bare-name imports** in production code. These are all lazy/deferred imports inside function bodies that the import rewrite pass in steps 5-8 did not catch.

### Step 16: CLI entry points -- PASS

Both entry points work correctly:

- `uv run python -m vaultspec --help` -- prints CLI help
- `uv run vaultspec --help` -- prints CLI help

### Step 17: MCP server importability -- PASS (with expected caveat)

- `from vaultspec.subagent_server.server import main` -- importable
- `from vaultspec.server import main` -- fails with `ModuleNotFoundError` (expected: `server.py` is Phase 2 step 18)

The `vaultspec-mcp` entry point in `[project.scripts]` points to `vaultspec.server:main` which does not exist yet. This is a known gap documented in the plan.

## Findings

### Critical / High (Must Fix)

- **[HIGH]** `src/vaultspec/vaultcore/models.py:106` -- Bare-name import `from core.config import get_config` inside function body. Causes `ModuleNotFoundError` at runtime when `_get_docs_dir()` is called. This is the direct cause of `test_audit_verify_text` failure.

- **[HIGH]** `src/vaultspec/protocol/acp/claude_bridge.py:212` -- Bare-name import `from core.config import get_config` inside `__init__`. Causes all ACP bridge tests (lifecycle, resilience, streaming) to fail with `ModuleNotFoundError`. This single import causes ~120 test failures.

- **[HIGH]** `src/vaultspec/protocol/acp/client.py:264,330` -- Two bare-name imports `from core.config import get_config` inside methods. Causes ACP client test failures.

- **[HIGH]** `src/vaultspec/protocol/providers/gemini.py:164` -- Bare-name import `from core.config import get_config`. Causes Gemini provider test failures.

- **[HIGH]** `src/vaultspec/protocol/a2a/agent_card.py:17` -- Bare-name import `from core.config import get_config`. Causes all 12 agent card tests to fail.

- **[HIGH]** `src/vaultspec/protocol/a2a/discovery.py:61` -- Bare-name import `from core.config import get_config`. Causes 3 discovery test failures.

- **[HIGH]** `src/vaultspec/protocol/a2a/server.py:8-9` -- Two bare-name imports: `from protocol.a2a.server import create_app` and `from protocol.a2a.agent_card import agent_card_from_definition`. These are self-referential bare-name imports in the A2A server module.

- **[HIGH]** `src/vaultspec/orchestration/subagent.py:83` -- Bare-name import `from core.config import get_config`. Causes subagent test failure.

- **[HIGH]** `src/vaultspec/orchestration/task_engine.py:128,245` -- Two bare-name imports `from core.config import get_config`. Causes task engine failures at runtime.

- **[HIGH]** `pyproject.toml` -- Dev dependencies defined under `[project.optional-dependencies].dev` instead of `[dependency-groups].dev`. The `uv sync --dev` command (documented in the plan's step 14) does not install dev dependencies. Users must use `uv sync --extra dev` as a workaround. This should be fixed by adding a `[dependency-groups]` section.

### Medium / Low (Recommended)

- **[MEDIUM]** `.vaultspec/lib/src/` -- Directory exists but is empty (0 files). Should be removed entirely for cleanliness per plan verification criteria: "`.vaultspec/lib/src/` and `.vaultspec/lib/scripts/` are empty or removed."

- **[LOW]** `.vaultspec/lib/src/vaultspec.egg-info/` -- Stale build artifact appears in `git status` as untracked. Should be added to `.gitignore` or removed.

## Summary of Bare-Name Imports Remaining

12 occurrences across 10 files, all inside function/method bodies (lazy imports):

| File                                          | Line | Import                                                           |
| --------------------------------------------- | ---- | ---------------------------------------------------------------- |
| `src/vaultspec/vaultcore/models.py`           | 106  | `from core.config import get_config`                             |
| `src/vaultspec/orchestration/subagent.py`     | 83   | `from core.config import get_config`                             |
| `src/vaultspec/orchestration/task_engine.py`  | 128  | `from core.config import get_config`                             |
| `src/vaultspec/orchestration/task_engine.py`  | 245  | `from core.config import get_config`                             |
| `src/vaultspec/protocol/acp/claude_bridge.py` | 212  | `from core.config import get_config`                             |
| `src/vaultspec/protocol/acp/client.py`        | 264  | `from core.config import get_config`                             |
| `src/vaultspec/protocol/acp/client.py`        | 330  | `from core.config import get_config`                             |
| `src/vaultspec/protocol/providers/gemini.py`  | 164  | `from core.config import get_config`                             |
| `src/vaultspec/protocol/a2a/agent_card.py`    | 17   | `from core.config import get_config`                             |
| `src/vaultspec/protocol/a2a/discovery.py`     | 61   | `from core.config import get_config`                             |
| `src/vaultspec/protocol/a2a/server.py`        | 8    | `from protocol.a2a.server import create_app`                     |
| `src/vaultspec/protocol/a2a/server.py`        | 9    | `from protocol.a2a.agent_card import agent_card_from_definition` |

All bare-name imports in `tests/` have been successfully rewritten. The issue is confined to production code lazy imports.

## Recommendations

The restructure is architecturally sound and nearly complete. Two targeted fixes are required before this can pass:

- **Fix all 12 bare-name imports:** Replace `from core.config` with `from vaultspec.core.config` and `from protocol.a2a.` with `from vaultspec.protocol.a2a.` across the 10 listed files. This is a mechanical find-and-replace. After this fix, the 142 failing tests and 86 errors should resolve to passes.

- **Add `[dependency-groups]` to `pyproject.toml`:** Add a `[dependency-groups]` section so that `uv sync --dev` works as documented:

```toml
  [dependency-groups]
  dev = ["vaultspec[dev]"]
```

Alternatively, include the dev dependencies directly in the group.

After these two fixes, re-run the full verification (steps 14-17) to confirm PASS status.

## Notes

- 792 of 1107 selected tests pass, confirming that the vast majority of the import rewrite was successful
- The CLI entry points (`vaultspec`, `python -m vaultspec`) work correctly
- The `hatchling` build backend and `[tool.hatch.build.targets.wheel]` configuration are correct
- The `mcp.json` correctly references `vaultspec-mcp` with `uv run`
- `_paths.py` is confirmed deleted; `.vaultspec/lib/scripts/` directory no longer exists
- No bare-name imports remain in test files -- only in production code lazy imports
- The `vaultspec.server` module (Phase 2) correctly does not exist yet
