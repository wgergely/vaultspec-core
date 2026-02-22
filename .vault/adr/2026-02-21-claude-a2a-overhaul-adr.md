---
tags:
  - "#adr"
  - "#claude-a2a-overhaul"
date: "2026-02-22"
related:
  - "[[2026-02-21-claude-a2a-overhaul-research]]"
  - "[[2026-02-21-protocol-gap-analysis-research]]"
  - "[[2026-02-21-a2a-layer-audit-research]]"
  - "[[2026-02-21-claude-sdk-rate-limit-research]]"
  - "[[2026-02-22-claude-team-management-reference]]"
  - "[[2026-02-22-claude-team-management-adr]]"
  - "[[2026-02-22-claude-team-management-plan]]"
  - "[[2026-02-20-a2a-team-adr]]"
---

# `claude-a2a-overhaul` adr: `Claude A2A Executor, Team Tools, and Process Lifecycle` | (**status:** `proposed`)

## Problem Statement

Claude cannot operate as a viable team member in A2A. Three gaps prevent this:

**Gap 1 — Executor reliability.** The `ClaudeA2AExecutor` crashes on every session
because `claude-agent-sdk` 0.1.39 throws `MessageParseError` on `rate_limit_event`
messages emitted by the Claude CLI on 100% of sessions. The executor has no retry,
no session resume, destructive cancel, and no streaming progress events.

**Gap 2 — No team tools.** `src/vaultspec/mcp_tools/team_tools.py` is an empty stub.
Claude agents running inside `ClaudeA2AExecutor` have no MCP tools to create teams,
dispatch tasks, broadcast messages, spawn agents, or manage team lifecycle. Without
these tools, Claude cannot act as a team leader or coordinator.

**Gap 3 — No process lifecycle.** `TeamCoordinator` can only connect to pre-existing
agent URLs. It cannot spawn local agent processes. The reference `AgentManager`
(`tmp-ref/python-a2a`) uses `subprocess` to start agents from templates, monitor
health, and clean shutdown. Without spawning, teams must be manually started.

These three gaps compound: even if the executor works, Claude has no tools to manage
teams; even if tools exist, there's no way to spawn the agents they'd manage.

## Considerations

### SDK Fix Status

The `rate_limit_event` crash is an upstream bug in `claude-agent-sdk`. PR #598
(merged Feb 20, 2026) fixes it by returning `None` for unknown message types
instead of raising `MessageParseError`. The fix is NOT in the released version
(0.1.39, released Feb 19). Options:

- Install from git main: `claude-agent-sdk @ git+https://...@main`
- Keep current workaround (catch `MessageParseError` in executor loop)
- Wait for 0.1.40 release

### Why Stay on claude-agent-sdk

The executor needs `mcp_servers` to receive team tools injection. The `claude-agent-sdk`
passes `mcp_servers` to `ClaudeAgentOptions`, which configures which MCP servers the
Claude subprocess can connect to. This is how Claude gets access to team management
capabilities. The raw `anthropic` SDK has no equivalent — it's a stateless API client
with no MCP support.

Additionally, `claude-agent-sdk` provides:
- Full Claude Code tool suite (Bash, Read, Write, Edit, Glob, Grep, etc.)
- `can_use_tool` sandbox callbacks (read-only / read-write mode)
- `permission_mode` for auto-approval
- System prompt injection
- Context compaction for long conversations

All of these are required for Claude to do actual work as a team member.

### Reference Architecture

Per [[2026-02-22-claude-team-management-reference]], the reference implementation
(`python-a2a`) has three components we lack:

- **`AgentManager`**: Spawns agent processes via `subprocess`, tracks PIDs, monitors
  health, auto-discovers ports. Maps to our `TeamCoordinator` + new spawn capability.
- **`AgentNetwork`**: High-level agent grouping with `network.add(name, url)` and
  `network.get_agent(name).ask(query)`. Maps to our `TeamCoordinator.dispatch_parallel()`.
- **MCP tools**: The reference exposes agent management as callable tools. Maps to
  our empty `team_tools.py` stub.

### Existing Patterns

The `subagent_server/server.py` establishes the MCP tool registration pattern:
imperative `mcp.tool(title=..., annotations=ToolAnnotations(...))(function_ref)`.
The `team_cli.py` (506 lines) already implements all 7 team subcommands with session
persistence via JSON in `.vault/logs/teams/`. The team tools should wrap the same
`TeamCoordinator` methods that the CLI uses.

## Constraints

- **No mocks in tests.** DI-injected test doubles only. Extend existing patterns.
- **claude-agent-sdk stays.** Required for MCP injection, tool use, and sandboxing.
- **Backward compatibility.** `TeamCoordinator` public API (`form_team`,
  `dispatch_parallel`, `collect_results`, `dissolve_team`) must not break.
- **Test baseline.** 69/69 non-E2E tests pass. No regressions.
- **MCP pattern consistency.** Follow `subagent_server/server.py` registration pattern.

## Implementation

Six decisions addressing all three gaps.

### Decision 1: Install claude-agent-sdk from Git Main

Pin `claude-agent-sdk` to git main in `pyproject.toml` to get the `rate_limit_event`
fix immediately. When 0.1.40 releases, switch back to a version pin.

```
claude-agent-sdk @ git+https://github.com/anthropics/claude-agent-sdk-python.git@main
```

Keep the existing `MessageParseError` catch in the executor loop as a safety net —
belt and suspenders. The catch becomes a no-op once the SDK fix is active (the SDK
filters unknowns before they reach the executor), but it protects against future
unknown message types.

### Decision 2: Harden ClaudeA2AExecutor

Five changes to the executor, building on the existing architecture:

**2a. Switch to `receive_response()`**: Replace `receive_messages().__aiter__().__anext__()`
with `async for msg in sdk_client.receive_response()`. Consistent with the ACP bridge
(Phase 1). `receive_response()` yields messages until `ResultMessage`, then stops —
cleaner than manual `_finalised` tracking.

**2b. Session resume via `context_id`**: Add `_session_ids: dict[str, str]` mapping
`context_id` to Claude `session_id`. Extract `session_id` from `ResultMessage` in the
streaming loop. On subsequent `execute()` calls with the same `context_id`, pass
`resume=session_id` in `ClaudeAgentOptions`. Enables multi-turn A2A conversations.

**2c. Non-destructive cancel**: In `cancel()`, call `interrupt()` only — do not call
`disconnect()` or pop from `_active_clients`. Add `_cancel_events: dict[str, asyncio.Event]`
for per-task cancel signaling. Check in the streaming loop, break if set. The subprocess
and session survive cancellation.

**2d. Streaming progress events**: Emit `updater.update_status()` with accumulated text
during streaming (throttled). Emit status on retry and cancel. A2A clients see
incremental progress instead of a silent wait followed by a single result.

**2e. Bounded retry on transient errors**: Wrap the `query() → stream` cycle in a retry
loop (3 attempts, exponential backoff). Trigger on `MessageParseError` with rate limit
data or `AssistantMessage.error == "rate_limit"`. After retries exhausted, fail the task.

### Decision 3: Implement team_tools.py MCP Module

Implement `src/vaultspec/mcp_tools/team_tools.py` following the `subagent_server/server.py`
registration pattern. Seven tools wrapping `TeamCoordinator` + new spawn capability:

| Tool | TeamCoordinator Method | Description |
|------|----------------------|-------------|
| `create_team` | `form_team()` | Form a team from agent URLs |
| `team_status` | session inspection | Get status of a running team |
| `list_teams` | session file listing | List active teams |
| `dispatch_task` | `dispatch_parallel()` | Assign a task to a team member |
| `broadcast_message` | `dispatch_parallel()` (all) | Send message to all members |
| `send_message` | `_dispatch_one()` / `relay_output()` | Message a specific member |
| `dissolve_team` | `dissolve_team()` | Dissolve a running team |

Each tool follows the imperative registration pattern:
```python
mcp.tool(
    title="Create Team",
    annotations=ToolAnnotations(readOnlyHint=False, ...),
)(create_team)
```

Session persistence reuses the `team_cli.py` helpers (`_save_session`, `_load_session`,
`_restore_coordinator`) — the tools and CLI share the same `.vault/logs/teams/` storage.

### Decision 4: Add Process Spawning to TeamCoordinator

Add `spawn_agent(script_path, port, name)` method to `TeamCoordinator`. Uses
`asyncio.create_subprocess_exec` to start a local A2A server process. Tracks spawned
processes in `self._spawned: dict[str, asyncio.subprocess.Process]`. Clean shutdown
in `dissolve_team()` terminates all spawned processes.

This mirrors the reference `AgentManager.start_agent_server` pattern but uses
`asyncio.subprocess` instead of `subprocess.Popen` for consistency with our async
architecture.

The spawned agent's URL is `http://localhost:{port}/`. After spawning, the coordinator
waits for the agent card endpoint to become reachable (polling with timeout), then
adds the agent to the team session via the existing `form_team` flow.

### Decision 5: Inject Team Tools into ClaudeA2AExecutor

The executor already accepts `mcp_servers: dict[str, Any]` and passes it to
`ClaudeAgentOptions`. To give Claude access to team tools:

- Start a local `team_tools` MCP server (stdio or SSE transport)
- Pass its configuration in the `mcp_servers` dict when constructing the executor
- The Claude subprocess connects to it and can call `create_team`, `dispatch_task`, etc.

This is done at the server/app initialization level (`server.py` or wherever the
executor is constructed), not inside the executor itself. The executor is transport-agnostic
— it just passes `mcp_servers` through.

### Decision 6: Register Team Tools in Unified MCP Server

Add `register_team_tools(mcp)` call to `server.py`'s `create_server()` function,
alongside the existing `register_subagent_tools(mcp)`. This makes team tools available
to any MCP client connecting to the unified `vaultspec-mcp` server — not just Claude
agents running inside the A2A executor.

## Rationale

### Why Three Gaps Must Be Addressed Together

Fixing the executor alone (Gap 1) gives Claude reliable A2A communication but no team
management. Implementing team tools alone (Gap 2) gives tools with no reliable executor
to run them in. Adding process spawning alone (Gap 3) gives lifecycle management with
no tools to invoke it. The three capabilities are interdependent — Claude as a viable
team member requires all three.

### Why MCP Tools (not Direct Python API)

Claude agents interact with capabilities via tools. MCP is the standard tool protocol.
The `claude-agent-sdk` natively supports `mcp_servers` in its options. Exposing team
management as MCP tools means any Claude agent (A2A, ACP, or standalone) can manage
teams — not just our executor code.

### Why Wrap TeamCoordinator (not Rewrite)

`TeamCoordinator` already works correctly for its current scope (form, dispatch,
collect, relay, dissolve). The CLI (`team_cli.py`) validates these methods across all
7 subcommands. The tools add spawning capability and MCP exposure — they don't replace
the coordinator.

### Why asyncio.subprocess (not subprocess.Popen)

Our entire stack is async. `asyncio.create_subprocess_exec` integrates naturally with
the event loop, supports non-blocking I/O, and allows `await process.wait()` for clean
shutdown. `subprocess.Popen` would require threading or polling for process management.

## Consequences

### Positive

- Claude can create teams, spawn agents, dispatch tasks, and dissolve teams — all via
  natural language through MCP tools.
- E2E `test_claude_a2a_responds` should pass with the SDK fix.
- Multi-turn A2A conversations via session resume.
- Non-destructive cancel preserves sessions.
- Streaming progress gives observability into long-running tasks.
- Team tools available to all MCP clients, not just A2A executor.

### Negative

- `claude-agent-sdk` pinned to git main is less stable than a release version. Must
  monitor for 0.1.40 release and switch back.
- Process spawning adds complexity to `TeamCoordinator`. Must handle process crashes,
  orphaned processes, port conflicts.
- Team tools share session storage with `team_cli.py`. Concurrent access (CLI + MCP)
  could cause conflicts. Consider file locking in a future phase.
- In-memory `_session_ids` and `_conversations` grow unbounded. Consider eviction
  for long-lived executors.

### Migration

- `pyproject.toml`: Pin `claude-agent-sdk` to git main.
- `claude_executor.py`: Extend (not rewrite). Add retry, session resume, cancel, streaming.
- `team_tools.py`: Implement from stub. Follow `subagent_server/server.py` pattern.
- `team.py`: Add `spawn_agent()` method. Extend `dissolve_team()` for process cleanup.
- `server.py`: Add `register_team_tools(mcp)` call.
- `test_claude_executor.py`: Extend with new test cases for retry, resume, cancel.
- New test file for team tools.
- No changes to ACP bridge, TeamCoordinator public API, or existing test fixtures.
