---
tags:
  - '#exec'
  - '#step-record'
date: '2026-02-22'
related:
  - '[[2026-02-21-claude-a2a-overhaul-impl-plan]]'
  - '[[2026-02-21-claude-a2a-overhaul-adr]]'
---

# Phase 3: Process Spawning (ADR Decision 4)

## Changes

### `src/vaultspec/orchestration/team.py`

- Added `import sys` to support `sys.executable` in subprocess spawning.
- Added `self._spawned: dict[str, asyncio.subprocess.Process]` to `TeamCoordinator.__init__()`.
- Added `spawn_agent(script_path, port, name)` method:
  - Uses `asyncio.create_subprocess_exec(sys.executable, script_path, "--port", str(port))`.
  - Polls `http://localhost:{port}/.well-known/agent-card.json` with 10s deadline, 500ms interval.
  - Detects premature process exit and raises `RuntimeError` with stderr.
  - Discovers agent card via `A2ACardResolver` and adds `TeamMember` to session.
- Extended `dissolve_team()`:
  - Iterates `self._spawned`, calls `proc.terminate()` + `asyncio.wait_for(proc.wait(), 5.0)`.
  - Falls back to `proc.kill()` on `TimeoutError`.
  - Handles `ProcessLookupError` for already-exited processes.
  - Clears `self._spawned` after cleanup.

### `src/vaultspec/mcp_tools/team_tools.py`

- Added `spawn_agent` to `__all__`.
- Updated module docstring and `register_tools()` docstring (7 -> 8 tools).
- Extended `_save_session()` with optional `spawned_pids` parameter for PID persistence.
- Added `_load_spawned_pids()` helper to read PIDs from session JSON.
- Added `spawn_agent()` tool function:
  - Loads session and existing PIDs, restores coordinator, calls `coordinator.spawn_agent()`.
  - Captures PIDs from `coordinator._spawned`, merges with existing, persists.
  - Returns JSON with new member's name, URL, and status.
- Extended `dissolve_team()` tool:
  - Loads `spawned_pids` from session, sends `SIGTERM` to each PID after coordinator dissolve.
  - Handles `ProcessLookupError` and `OSError` gracefully.
- Registered `spawn_agent` with `ToolAnnotations(readOnlyHint=False, openWorldHint=True)`.

### `src/vaultspec/orchestration/tests/test_team_spawn.py` (new)

- `_ECHO_SERVER_SCRIPT`: Self-contained A2A echo server using uvicorn.
- `echo_server_script` fixture: Writes script to tmp_path.
- `_find_free_port()`: OS-level free port discovery.
- `test_spawn_agent_starts_process`: Spawns echo server, verifies team membership, process tracking.
- `test_dissolve_terminates_spawned`: Spawns then dissolves, verifies process terminated.
- `test_spawn_invalid_script_fails`: Non-existent script raises `RuntimeError`.
- All tests marked `@pytest.mark.integration` and `@pytest.mark.team`.

## Verification

- Tests require Bash permissions to run (pending).
- No mocking patterns used; all tests exercise real subprocesses and real HTTP.
- Existing `test_team.py` tests unaffected (no API changes to existing methods).
