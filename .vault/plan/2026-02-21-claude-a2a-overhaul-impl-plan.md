---
tags:
  - "#plan"
  - "#claude-a2a-overhaul"
date: "2026-02-22"
related:
  - "[[2026-02-21-claude-a2a-overhaul-adr]]"
  - "[[2026-02-21-claude-a2a-overhaul-research]]"
  - "[[2026-02-22-claude-team-management-reference]]"
  - "[[2026-02-22-claude-team-management-adr]]"
  - "[[2026-02-22-claude-team-management-plan]]"
  - "[[2026-02-20-a2a-team-adr]]"
---
# `claude-a2a-overhaul` implementation plan

> **Parallel plan**: [[2026-02-22-claude-team-management-plan]] covers the same
> team tools, process spawning, and executor injection work from a different angle.
> That plan focuses on team lifecycle management; this plan adds executor reliability
> (Phase 1) and unified server registration (Phase 4). The two plans share modified
> files (`team.py`, `team_tools.py`, `claude_executor.py`) and must be coordinated
> — do not execute both independently. Phase 1 of this plan (executor hardening) is
> unique and has no overlap. Phases 2-5 here subsume the `claude-team-management`
> plan's Phases 1-3.

Make Claude a viable A2A team member. Three gaps closed across five phases:
executor reliability (SDK fix + hardening), team tools (MCP implementation),
process lifecycle (agent spawning), tool injection, and integration testing.

## Proposed Changes

Per [[2026-02-21-claude-a2a-overhaul-adr]], six decisions implemented across five
phases. Primary targets:

- `src/vaultspec/protocol/a2a/executors/claude_executor.py` — executor hardening
- `src/vaultspec/mcp_tools/team_tools.py` — implement from stub
- `src/vaultspec/orchestration/team.py` — add process spawning
- `src/vaultspec/server.py` — register team tools
- `pyproject.toml` — SDK pin to git main

The `TeamCoordinator` public API is not changed. The ACP bridge is not touched.

## Tasks

- `Phase 1: SDK Fix + Executor Hardening (ADR Decisions 1 + 2)`
    1. **Pin claude-agent-sdk to git main** in `pyproject.toml`:
       `claude-agent-sdk @ git+https://github.com/anthropics/claude-agent-sdk-python.git@main`.
       Run `uv sync`. Verify the `rate_limit_event` fix is present by inspecting
       installed `message_parser.py`.
    2. **Switch to `receive_response()`**: Replace the manual
       `receive_messages().__aiter__().__anext__()` pattern (lines 130-164) with
       `async for msg in sdk_client.receive_response()`. Remove the `_finalised`
       flag — `receive_response()` stops at `ResultMessage` automatically.
    3. **Add bounded retry**: Add `max_retries: int = 3` and
       `retry_base_delay: float = 1.0` to `__init__()`. Wrap the `query() → stream`
       cycle in a retry loop. On `MessageParseError` with rate limit data or
       `AssistantMessage.error == "rate_limit"`, wait `base_delay * 2^attempt` then
       retry. Keep the `MessageParseError` catch as belt-and-suspenders even with the
       SDK fix.
    4. **Add session resume**: Add `_session_ids: dict[str, str]` to `__init__()`.
       In the streaming loop, extract `msg.session_id` from `ResultMessage`. On
       subsequent `execute()` with same `context_id`, pass `resume=session_id` in
       options kwargs.
    5. **Make cancel non-destructive**: Remove `disconnect()` from `cancel()`. Keep
       `interrupt()`. Add `_cancel_events: dict[str, asyncio.Event]` for per-task
       cancel. Check in streaming loop, break if set. Only `disconnect()` on
       completion/failure in the `finally` block.
    6. **Add streaming progress**: Emit `updater.update_status()` with accumulated
       text during streaming (throttle: every 500ms or 100 chars). Emit status on
       retry ("Rate limited, retrying N/M") and cancel ("Task cancelled").
    7. **Extend `_InProcessSDKClient`**: Add `receive_response()` method. Add ability
       to inject errors (for retry testing) and `session_id` on `ResultMessage`
       (for resume testing).
    8. **Write tests**: Retry after rate limit. Failure after max retries. Session
       resume across two executions with same context_id. Non-destructive cancel
       (no disconnect, session preserved). Streaming progress events in output.
       `AssistantMessage.error` handling.
    - **Files modified**: `pyproject.toml`, `claude_executor.py`,
      `test_claude_executor.py`
    - **Verify**: `uv sync` succeeds. All existing 69 non-E2E tests pass. New tests
      pass.

- `Phase 2: Implement team_tools.py (ADR Decision 3)`
    1. **Implement `register_tools()`**: Follow `subagent_server/server.py` pattern.
       Register 7 tools via imperative `mcp.tool(title=..., annotations=...)(fn)`.
    2. **Implement `create_team()`**: Accept `name: str` and `agent_urls: list[str]`.
       Instantiate `TeamCoordinator`, call `form_team()`. Persist session via
       `team_cli._save_session()` helpers (reuse, don't duplicate). Return team_id
       and member list as JSON.
    3. **Implement `team_status()`**: Accept `name: str`. Load session from
       `.vault/logs/teams/{name}.json`. Return status, members, and their states.
    4. **Implement `list_teams()`**: List `.json` files in `.vault/logs/teams/`.
       Return list of team names and statuses.
    5. **Implement `dispatch_task()`**: Accept `team_name: str`, `agent_name: str`,
       `task: str`. Restore coordinator from session. Call
       `dispatch_parallel({agent_name: task})`. Return task ID and status.
    6. **Implement `broadcast_message()`**: Accept `team_name: str`, `message: str`.
       Dispatch same message to all members. Return results.
    7. **Implement `send_message()`**: Accept `team_name: str`, `to: str`,
       `message: str`. Dispatch to specific agent. Return result.
    8. **Implement `dissolve_team()`**: Accept `team_name: str`. Restore coordinator.
       Call `dissolve_team()`. Delete session file. Return confirmation.
    9. **Write tests**: Test each tool function with DI'd coordinator. Test session
       persistence round-trip. Test error cases (unknown team, unknown agent).
    - **Files modified**: `team_tools.py`
    - **New test file**: `src/vaultspec/mcp_tools/tests/test_team_tools.py`
    - **Verify**: All tools callable. Session persistence works. No regressions.

- `Phase 3: Process Spawning (ADR Decision 4)`
    1. **Add `spawn_agent()` to `TeamCoordinator`**: Accept `script_path: str`,
       `port: int`, `name: str`. Use `asyncio.create_subprocess_exec` to start the
       process. Use `sys.executable` as the command (e.g., `[sys.executable, script_path, ...]`)
       to ensure the subprocess runs in the same Python environment (virtualenv) as the host.
       Track in `self._spawned: dict[str, asyncio.subprocess.Process]`.
    2. **Add health check polling**: After spawning, poll
       `http://localhost:{port}/.well-known/agent.json` with timeout (10s, 500ms
       interval). Raise if agent doesn't become reachable.
    3. **Extend `dissolve_team()`**: Terminate all spawned processes. Call
       `process.terminate()`, then `process.wait()` with timeout. If still alive,
       `process.kill()`.
    4. **Add `spawn_agent` tool to team_tools.py**: Accept `script_path: str`,
       `port: int`, `name: str`, `team_name: str`. Call coordinator's `spawn_agent()`.
       Add spawned agent to team session.
    5. **Write tests**: Test spawn + health check with a simple echo server script.
       Test dissolve terminates spawned processes. Test spawn failure (invalid script).
    - **Files modified**: `team.py`, `team_tools.py`
    - **Verify**: Process spawns, becomes reachable, gets added to team. Clean
      shutdown on dissolve.

- `Phase 4: Wiring (ADR Decisions 5 + 6)`
    1. **Register team tools in unified server**: Add
       `from vaultspec.mcp_tools.team_tools import register_tools as register_team_tools`
       and `register_team_tools(mcp)` to `server.py`'s `create_server()`.
    2. **Document MCP injection pattern**: Add a helper or documentation showing how
       to construct `mcp_servers` config for injecting `team_tools` into
       `ClaudeA2AExecutor`. The executor already passes `mcp_servers` through to
       `ClaudeAgentOptions` — the wiring is at the call site, not inside the executor.
    3. **Verify MCP tool discovery**: Start the unified server, connect a client,
       verify team tools appear alongside subagent tools.
    - **Files modified**: `server.py`
    - **Verify**: `vaultspec-mcp` exposes team tools. `list_tools` returns all
      subagent + team tools.

- `Phase 5: Integration Testing`
    1. **Team lifecycle integration test**: Create team with in-process echo agents
       (using existing `EchoExecutor` from conftest). Dispatch task. Collect result.
       Dissolve team. Verify full lifecycle.
    2. **Team tools integration test**: Verify `create_team` → `dispatch_task` →
       `team_status` → `dissolve_team` flow through MCP tools.
    3. **Executor + team tools test**: Construct executor with `mcp_servers` including
       team tools. Verify the executor can be configured to access team capabilities.
    4. **Run full test suite**: All non-E2E tests pass. No regressions.
    - **New test file**: `tests/integration/test_team_lifecycle.py` or extend
      existing `test_team.py`
    - **Verify**: Full lifecycle works end-to-end through tools.

## Parallelization

- **Phase 1** (executor) and **Phase 2** (team tools) are independent and can run
  in parallel. Phase 1 modifies executor code; Phase 2 implements MCP tools. No
  shared files.
- **Phase 3** (spawning) depends on Phase 2 (adds a tool to team_tools.py) and
  modifies `team.py`.
- **Phase 4** (wiring) depends on Phase 2 (tools must exist to register).
- **Phase 5** (integration) depends on all prior phases.

**Recommended**: Run Phase 1 and Phase 2 in parallel. Then Phase 3. Then Phase 4.
Then Phase 5.

```
Phase 1 (executor) ──┐
                      ├── Phase 3 (spawning) ── Phase 4 (wiring) ── Phase 5 (integration)
Phase 2 (tools)  ────┘
```

## Verification

- **Baseline preservation**: All 69 non-E2E tests pass after each phase.
- **New test coverage**: Target 20+ new test cases across all phases.
  - Phase 1: ~8 (retry, resume, cancel, streaming, error handling)
  - Phase 2: ~8 (one per tool + error cases)
  - Phase 3: ~3 (spawn, health check, dissolve cleanup)
  - Phase 5: ~3 (lifecycle, tools flow, executor config)
- **E2E validation**: `test_claude_a2a_responds` should pass with the SDK fix if
  `ANTHROPIC_API_KEY` is available. The `rate_limit_event` crash is fixed upstream.
- **Import hygiene**: No new imports of `anthropic` in the executor. `claude-agent-sdk`
  remains the sole SDK. `anthropic` is NOT added as a direct dependency.
- **MCP consistency**: Team tools follow the same `register_tools(mcp)` pattern as
  `subagent_server/server.py`. Same `ToolAnnotations`, same error reporting via
  `ToolError`.
- **Backward compatibility**: `TeamCoordinator.form_team()`,
  `dispatch_parallel()`, `collect_results()`, `dissolve_team()` signatures unchanged.
  CLI (`team_cli.py`) works unchanged.
