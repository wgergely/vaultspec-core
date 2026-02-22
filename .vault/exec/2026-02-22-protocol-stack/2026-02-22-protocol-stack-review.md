---
tags:
  - "#exec"
  - "#protocol-stack"
date: "2026-02-22"
related:
  - "[[2026-02-22-protocol-stack-deep-audit-plan]]"
  - "[[2026-02-22-protocol-stack-deep-audit-adr]]"
  - "[[2026-02-22-protocol-stack-deep-audit-summary]]"
  - "[[2026-02-22-protocol-stack-deep-audit-research]]"
---

# `protocol-stack` code review

**Status:** `REVISION REQUIRED`

## Audit Context

- **Plan:** `[[2026-02-22-protocol-stack-deep-audit-plan]]`
- **ADR:** `[[2026-02-22-protocol-stack-deep-audit-adr]]`
- **Scope:** 14 files across 4 tracks (Session Management, Team Async, CLI/MCP Parity, Test Fixes)

Files reviewed:

- `src/vaultspec/orchestration/subagent.py` (Track A -- session resume)
- `src/vaultspec/orchestration/task_engine.py` (Track A -- `get_session_id`)
- `src/vaultspec/subagent_server/server.py` (Track A -- MCP `get_task_status` + `dispatch_agent`)
- `src/vaultspec/protocol/a2a/executors/gemini_executor.py` (Track A -- session reuse)
- `tests/protocol/isolation/test_subagent_gemini.py` (Track A -- session assertion)
- `tests/protocol/isolation/test_subagent_claude.py` (Track A -- session assertion)
- `src/vaultspec/orchestration/team_task_engine.py` (Track B -- new `TeamTaskEngine`)
- `src/vaultspec/mcp_tools/team_tools.py` (Track B -- async refactor + new tools)
- `src/vaultspec/subagent_cli.py` (Track C -- 6 CLI flags + debug on serve)
- `src/vaultspec/cli.py` (Track C -- `MODULE_PATHS` fix)
- `src/vaultspec/team_cli.py` (Track C -- `spawn` command)
- `src/vaultspec/orchestration/utils.py` (Track D -- `start_dir` param)
- `src/vaultspec/orchestration/tests/test_utils.py` (Track D -- removed `monkeypatch.chdir`)
- `src/vaultspec/tests/__init__.py` (Track D -- package marker)

## Findings

### Critical / High (Must Fix)

- **[HIGH]** `src/vaultspec/orchestration/team_task_engine.py:135-136` -- `register_bg_task()` writes to `self._bg_tasks` without acquiring `self._lock`. Every other method that accesses `self._bg_tasks` (`_cleanup_expired` at line 69, `cancel_task` at line 130) is called from within a `with self._lock:` block, but `register_bg_task` is entirely unprotected. Since the callers in `team_tools.py` call `register_bg_task` from an async context while `_cleanup_expired` may be called from any thread holding the lock, this creates a data race on the dict. The fix is to wrap the assignment in `with self._lock:`.

- **[HIGH]** `src/vaultspec/mcp_tools/team_tools.py:348-364` (and similarly lines 394-415, 450-469) -- Background tasks created via `asyncio.create_task(_run())` are fire-and-forget with no exception logging on unhandled failures. If the `_run()` coroutine itself raises before reaching the `except Exception` handler (e.g., during `_restore_coordinator`), the exception is caught correctly. However, the `asyncio.Task` returned by `create_task` is stored in `_bg_tasks` but never awaited anywhere except in `cancel_task`. If the task engine expires and removes the task entry (via `_cleanup_expired`), the `asyncio.Task` object may be garbage-collected with a pending exception, producing an "exception was never retrieved" warning. This is not a crash risk but degrades observability. Consider adding a `done_callback` that logs exceptions, mirroring the pattern used in `subagent.py:325-326` for background tasks.

- **[HIGH]** `src/vaultspec/subagent_server/server.py:142-170` -- `_prepare_dispatch_kwargs` was not updated to accept `resume_session_id` per Plan Step 1c. The plan explicitly states: "Also update `_prepare_dispatch_kwargs()` (line 142-170) to accept and include the parameter." While the function is not called from `dispatch_agent` in production (the kwargs are built inline at lines 484-499), it IS imported and tested in `src/vaultspec/subagent_server/tests/test_mcp_tools.py:685-750`. The function and its tests are now inconsistent with the actual `dispatch_agent` implementation, creating a false sense of test coverage. Either update `_prepare_dispatch_kwargs` to include `resume_session_id`, `content_root`, and `client_ref` (to match the inline kwargs), or remove it in favor of the inline construction and update the tests accordingly.

- **[HIGH]** `src/vaultspec/team_cli.py:345-374` -- `command_spawn` does not persist the spawned process PID, unlike the MCP `spawn_agent` tool (`team_tools.py:509-517`) which saves PIDs to the session file. Consequently, `command_dissolve` (line 377-405) cannot terminate spawned processes because the restored coordinator has an empty `_spawned` dict. This is a functional gap between CLI and MCP that defeats the purpose of Track C (CLI/MCP parity). The fix is to persist PIDs in `command_spawn` and read+kill them in `command_dissolve`, mirroring the MCP tool's approach.

### Medium / Low (Recommended)

- **[MEDIUM]** `src/vaultspec/orchestration/subagent.py:220` -- `Any` is used in the type annotation `dict[str, Any]` but is not imported from `typing`. This does not cause a runtime error due to `from __future__ import annotations` (PEP 563), but will cause static analysis tools (mypy, pyright) to report an undefined name. Add `Any` to the `from typing import TYPE_CHECKING` line or import it unconditionally.

- **[MEDIUM]** `src/vaultspec/orchestration/subagent.py:376` -- The synthetic session object `type("_Session", (), {"session_id": resume_session_id})()` is functional but fragile. It relies on the caller only ever accessing `.session_id` on the result. If any future code accesses other attributes of the `NewSessionResponse` (such as `config_options` or `modes`), this will raise `AttributeError` at runtime with no helpful error message. Consider defining a minimal `NamedTuple` or `dataclass` (e.g., `_ResumedSession`) to make the contract explicit and provide better error messages if the interface evolves.

- **[MEDIUM]** `src/vaultspec/mcp_tools/team_tools.py:636` -- `os.kill(pid, signal.SIGTERM)` on Windows does not send SIGTERM; it calls `TerminateProcess` which forcefully kills without cleanup. This is the correct behavior for this use case, but the log message at line 637 says "Sent SIGTERM" which is misleading on Windows. Consider using platform-aware messaging, or use the same `_kill_process_tree` approach from `subagent.py:49-68` for consistency.

- **[MEDIUM]** `src/vaultspec/mcp_tools/team_tools.py:60` -- `_team_task_engine = TeamTaskEngine()` is a module-level singleton. It has no shutdown hook and no mechanism to cancel in-flight background tasks when the MCP server shuts down. The subagent `TaskEngine` is at least managed through a lifespan context manager (`subagent_lifespan`). Consider adding a team lifespan that cancels all `_bg_tasks` on shutdown.

- **[MEDIUM]** `src/vaultspec/cli.py:1532-1544` -- `MODULE_PATHS` now includes entries for `"core"` and `"mcp_tools"` that were not in the original plan. While these directories exist and the additions are sensible, this is scope drift beyond what the ADR authorized (Decision 2b only specified 6 modules: cli, rag, vault, protocol, orchestration, subagent). The additions should be acknowledged in the execution summary.

- **[LOW]** `src/vaultspec/mcp_tools/team_tools.py:665` -- The docstring for `register_tools` says "Registers all 8 team tools" but the function now registers 10 tools (the original 8 plus `get_team_task_status` and `relay_output`). Update the docstring to reflect the actual count.

- **[LOW]** `tests/protocol/isolation/test_subagent_gemini.py:62` and `test_subagent_claude.py:62` -- The session identity assertion `assert result2.session_id == result1.session_id` correctly validates session resume. The tests are well-structured, use real provider instances (no mocking), and pass `resume_session_id` correctly. No issues found.

- **[LOW]** `src/vaultspec/orchestration/utils.py:17` -- The `start_dir` parameter defaults to `None` with a fallback to `Path.cwd()`. This is clean and backward-compatible. The test at `test_utils.py:56` now passes `start_dir=TEST_PROJECT` directly, eliminating the banned `monkeypatch.chdir`. No issues found.

## Recommendations

**Must fix before merge (HIGH):**

- Add `with self._lock:` around the assignment in `TeamTaskEngine.register_bg_task()`.
- Either update `_prepare_dispatch_kwargs` to match the inline kwargs in `dispatch_agent`, or remove the dead function and update its tests. The current state creates a false parity between the helper and the actual implementation.
- Add PID persistence to `team_cli.py:command_spawn` and PID-based process termination to `command_dissolve`, matching the MCP tool behavior in `team_tools.py`.
- Add a `done_callback` to the background `asyncio.Task` objects in `team_tools.py` to log exceptions on fire-and-forget failures.

**Recommended (MEDIUM):**

- Add `Any` to the typing imports in `subagent.py`.
- Replace the synthetic `type("_Session", ...)()` with a minimal named type.
- Fix the misleading "SIGTERM" log message in `team_tools.py` for Windows.
- Add a team tools lifespan manager for graceful shutdown.
- Acknowledge the `core` and `mcp_tools` MODULE_PATHS additions in the execution summary.

**Track-by-track assessment:**

- **Track A (Session Management):** Core fix is correct and well-implemented. The session resume branch, MCP parameter propagation, Gemini executor session reuse, and test assertions all align with the plan. The synthetic `_Session` object is functional. PASS with one MEDIUM note.
- **Track B (Team Async):** Architecture mirrors the proven `TaskEngine` pattern correctly. The `TeamTaskEngine` is clean and minimal. However, the thread-safety gap in `register_bg_task` and the missing exception logging on background tasks are HIGH issues that need fixing.
- **Track C (CLI/MCP Parity):** All 6 CLI flags are present and correctly mapped. `MODULE_PATHS` are valid. Debug flags on serve subparsers work. The `spawn` command in `team_cli.py` has a functional gap (no PID persistence) that undermines the parity goal.
- **Track D (Test Fixes):** All changes are clean. The `__init__.py` exists. The `find_project_root` refactoring is backward-compatible. The `monkeypatch.chdir` removal is correct. Step 4c (stale constants) was intentionally deferred per user decision.

## Notes

- Decision 5 (Programmatic Multi-Turn API) was correctly excluded from implementation per the ADR's deferral.
- Step 4c (stale constants removal) and 4d (monkeypatch policy) are noted as deferred/completed in the execution summary. This is consistent with the plan.
- The protocol isolation tests (`test_subagent_gemini.py`, `test_subagent_claude.py`) require live API keys and cannot be verified in this review. Their structure and assertions are correct.
