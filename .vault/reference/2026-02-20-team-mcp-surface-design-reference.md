---
tags:
  - '#reference'
  - '#team-mcp-integration'
date: '2026-02-20'
related:
  - '[[2026-02-20-a2a-team-adr]]'
---

<!-- Migrated from frontmatter — do not promote back -->

**Title:** vs-team-mcp Tool Surface Design
**Subtitle:** MCP server surface for TeamCoordinator orchestration
**Author:** vaultspec-code-reviewer (Audit & Design)
**References:** `.vault/adr/2026-02-20-a2a-team-adr.md` · `.vaultspec/lib/src/orchestration/team.py` · `.vaultspec/lib/scripts/team.py`

# vs-team-mcp Surface Design

## Executive Summary

This document specifies the MCP tool surface for `vs-team-mcp`, a server that exposes the TeamCoordinator API to Claude and other MCP clients.

**Key Findings:**

- TeamCoordinator is fully async with context manager support (`__aenter__`, `__aexit__`)
- 6 major public methods + 1 session restoration utility
- Session state persists to `.vault/logs/teams/{name}.json` (CLI already handles this)
- All network operations are async; tools must be called within async context

______________________________________________________________________

## TeamCoordinator API Audit

### Constructor & Context Management

```python
def __init__(
    self,
    api_key: str | None = None,
    collect_timeout: float = _DEFAULT_COLLECT_TIMEOUT,  # 300.0 seconds
) -> None
```

**Async Context Manager:**

```python
async def __aenter__(self) -> TeamCoordinator
async def __aexit__(self, *_: object) -> None
```

- Creates `httpx.AsyncClient` on entry
- Closes on exit (idempotent)
- If context manager not used, creates client on-demand via `_ensure_http_client()`

### Session State

**Public Accessor:**

```python
@property
def session(self) -> TeamSession:
    """Raise RuntimeError if no active session."""
```

**Session Structure (TeamSession dataclass):**

```python
@dataclass
class TeamSession:
    team_id: str                          # UUID, unique identifier
    name: str                             # Human-readable name
    context_id: str                       # Always equals team_id (A2A Decision 2)
    members: dict[str, TeamMember]        # Keyed by agent name
    status: TeamStatus                    # One of: FORMING, ACTIVE, DISSOLVING, DISSOLVED
    created_at: float                     # Unix timestamp
```

**TeamMember Structure:**

```python
@dataclass
class TeamMember:
    name: str                             # Agent name (from card.name or URL fallback)
    url: str                              # Agent base URL
    card: AgentCard                       # a2a.types.AgentCard
    status: MemberStatus                  # One of: SPAWNING, IDLE, WORKING, SHUTDOWN_REQUESTED, TERMINATED
```

**Enums:**

```python
class MemberStatus(StrEnum):
    SPAWNING = "spawning"
    IDLE = "idle"
    WORKING = "working"
    SHUTDOWN_REQUESTED = "shutdown_requested"
    TERMINATED = "terminated"

class TeamStatus(StrEnum):
    FORMING = "forming"
    ACTIVE = "active"
    DISSOLVING = "dissolving"
    DISSOLVED = "dissolved"
```

### Public Methods

#### 1. restore_session (SYNC)

```python
def restore_session(self, session: TeamSession) -> None
```

**Purpose:** Restore a previously persisted session without re-fetching agent cards.

**Usage:** Load session from disk, pass to this method, then use coordinator with restored state.

**Clears:** Per-member A2A client cache (HTTP client may have changed).

**Raises:** None.

**Async:** No.

______________________________________________________________________

#### 2. form_team (ASYNC)

```python
async def form_team(
    self,
    name: str,
    agent_urls: list[str],
    api_key: str | None = None,
) -> TeamSession
```

**Purpose:** Discover agents via `A2ACardResolver` and assemble a named team session.

**Parameters:**

- `name`: Human-readable team name (forwarded in A2A message metadata)
- `agent_urls`: List of agent base URLs (e.g., `http://localhost:10010/`)
- `api_key`: Optional override (takes precedence over constructor value for this call)

**Returns:** `TeamSession` with ACTIVE status.

**Side Effects:**

- Sets `self._session`
- If API key override provided, recreates HTTP client with new headers
- Clears per-member client cache
- Generates UUID for both `team_id` and `context_id` (Decision 2)

**Raises:**

- `httpx` exceptions (network, DNS, timeout)
- A2A resolution errors (invalid agent URLs, malformed cards)

**Async:** Yes (parallel A2ACardResolver calls via `asyncio.gather`).

______________________________________________________________________

#### 3. dispatch_parallel (ASYNC)

```python
async def dispatch_parallel(
    self,
    assignments: dict[str, str],
) -> dict[str, Task]
```

**Purpose:** Fan out tasks to multiple agents concurrently.

**Parameters:**

- `assignments`: Mapping of agent name → task text (task text is message content)

**Returns:** Mapping of agent name → `a2a.types.Task` (always terminal state).

**Behavior:**

- Sets member status to WORKING before dispatch
- Polls each task to terminal state (completed, failed, canceled)
- Sets member status back to IDLE on completion or error
- Stores task IDs in `self._in_flight` for `collect_results()` usage
- Per-agent errors are logged; entry omitted from results dict

**Side Effects:**

- Updates TeamMember.status (WORKING → IDLE)
- Updates `self._in_flight` with task IDs

**Raises:** None (errors logged, returned as omitted dict entries).

**Async:** Yes (concurrent A2A sends via `asyncio.gather`).

______________________________________________________________________

#### 4. collect_results (ASYNC)

```python
async def collect_results(self) -> dict[str, str]
```

**Purpose:** Poll all in-flight tasks until terminal state; extract artifact text.

**Parameters:** None (uses `self._in_flight`).

**Returns:** Mapping of agent name → extracted text (from first TextPart of task.status.message).

**Behavior:**

- Applies `self._collect_timeout` guard (default 300s)
- Extracts text via `extract_artifact_text(task)` helper
- On A2A poll error, returns `[error: <error_msg>]` string
- Clears nothing (caller responsible for cleanup)

**Raises:** `asyncio.TimeoutError` if collection exceeds timeout.

**Async:** Yes.

______________________________________________________________________

#### 5. relay_output (ASYNC)

```python
async def relay_output(
    self,
    src_task: Task,
    dst_agent: str,
    instructions: str,
) -> Task
```

**Purpose:** Relay a completed task's output to another agent (with instructions).

**Parameters:**

- `src_task`: The completed source task (a2a.types.Task)
- `dst_agent`: Name of destination agent (must be team member)
- `instructions`: Additional instructions to append to message

**Returns:** Resulting `Task` from destination agent (terminal state).

**Behavior:**

- Extracts artifact text from `src_task` via `extract_artifact_text()`
- Builds two-part message: [output_text, instructions]
- Sets `reference_task_ids=[src_task.id]` in A2A message
- Stores resulting task ID in `self._in_flight`

**Side Effects:**

- Updates `self._in_flight[dst_agent]`

**Raises:** Same as `dispatch_parallel` (wrapped A2A errors).

**Async:** Yes.

______________________________________________________________________

#### 6. dissolve_team (ASYNC)

```python
async def dissolve_team(self) -> None
```

**Purpose:** Tear down the active team session.

**Parameters:** None.

**Returns:** None.

**Behavior:**

- Marks session status DISSOLVING → DISSOLVED
- Best-effort cancels all in-flight tasks (via A2A CancelTaskRequest)
- Clears `self._in_flight` and per-member client cache
- Sets all member status to TERMINATED
- Idempotent: calling on already-dissolved session is a no-op

**Side Effects:**

- Updates TeamSession.status
- Clears internal caches
- Updates all TeamMember.status

**Raises:** None (cancellation errors logged, not raised).

**Async:** Yes.

______________________________________________________________________

#### 7. ping_agents (ASYNC)

```python
async def ping_agents(self) -> dict[str, bool]
```

**Purpose:** Check reachability of all team members.

**Parameters:** None (uses `self.session.members`).

**Returns:** Mapping of agent name → reachable bool.

**Behavior:**

- Issues `GET /.well-known/agent-card.json` to each member URL via `A2ACardResolver`
- Sets member status to IDLE on success
- Leaves status unchanged on failure
- Errors logged, not raised

**Side Effects:**

- Updates TeamMember.status (on success only)

**Raises:** None.

**Async:** Yes.

______________________________________________________________________

## MCP Tool Surface Specification

### Tool 1: create_team

**Name:** `create_team`

**Description:** Form a new named team from a list of agent URLs.

**Parameters:**

| Name         | Type          | Required | Description                                               |
| ------------ | ------------- | -------- | --------------------------------------------------------- |
| `name`       | string        | Yes      | Team name (human-readable, used in A2A metadata)          |
| `agent_urls` | array[string] | Yes      | List of agent base URLs (e.g., `http://localhost:10010/`) |
| `api_key`    | string        | No       | Optional API key for X-API-Key header                     |

**Return Structure:**

```json
{
  "status": "success|error",
  "team_id": "uuid",
  "team_name": "string",
  "member_count": "number",
  "members": {
    "<agent_name>": {
      "name": "string",
      "url": "string",
      "status": "idle|spawning|working|shutdown_requested|terminated"
    }
  },
  "error": "error message (if status=error)"
}
```

**Implementation:** Call `coordinator.form_team()` within async context.

**Session Persistence:** Yes. After successful formation, save TeamSession to `.vault/logs/teams/{name}.json`.

**Errors:** Network errors, invalid URLs, A2A card fetch failures.

______________________________________________________________________

### Tool 2: get_team_status

**Name:** `get_team_status`

**Description:** Retrieve the current status of a persisted team session.

**Parameters:**

| Name   | Type   | Required | Description |
| ------ | ------ | -------- | ----------- |
| `name` | string | Yes      | Team name   |

**Return Structure:**

```json
{
  "status": "success|error",
  "team": {
    "id": "uuid",
    "name": "string",
    "status": "forming|active|dissolving|dissolved",
    "created_at": "unix_timestamp",
    "member_count": "number",
    "members": {
      "<agent_name>": {
        "name": "string",
        "url": "string",
        "status": "idle|spawning|working|shutdown_requested|terminated"
      }
    }
  },
  "error": "error message (if status=error)"
}
```

**Implementation:** Load TeamSession from disk, return serialized state (no API calls).

**Session Persistence:** No (read-only).

**Errors:** File not found, corrupt JSON, missing team name.

______________________________________________________________________

### Tool 3: list_teams

**Name:** `list_teams`

**Description:** List all persisted team sessions.

**Parameters:** None.

**Return Structure:**

```json
{
  "status": "success|error",
  "teams": [
    {
      "name": "string",
      "team_id": "uuid",
      "status": "forming|active|dissolving|dissolved",
      "member_count": "number"
    }
  ],
  "error": "error message (if status=error)"
}
```

**Implementation:** Scan `.vault/logs/teams/` for `.json` files, parse each.

**Session Persistence:** No (read-only).

**Errors:** Directory not found (return empty list), malformed JSON (skip, continue).

______________________________________________________________________

### Tool 4: dispatch_task

**Name:** `dispatch_task`

**Description:** Dispatch a task to one or more team members in parallel.

**Parameters:**

| Name          | Type   | Required | Description                       |
| ------------- | ------ | -------- | --------------------------------- |
| `name`        | string | Yes      | Team name                         |
| `assignments` | object | Yes      | Mapping of agent_name → task_text |
| `api_key`     | string | No       | Optional API key override         |

**Return Structure:**

```json
{
  "status": "success|partial|error",
  "results": {
    "<agent_name>": {
      "task_id": "string",
      "state": "completed|failed|canceled",
      "output": "string (artifact text, may be empty)"
    }
  },
  "failed_agents": [
    {
      "agent_name": "string",
      "error": "error message"
    }
  ],
  "error": "error message (if status=error)"
}
```

**Implementation:**

1. Load TeamSession from disk
1. Restore coordinator with `restore_session()`
1. Call `dispatch_parallel(assignments)`
1. For each result, extract artifact text
1. Update session status if needed (currently read-only, but may need to track in-flight)

**Session Persistence:** Yes. After dispatch, optionally log in-flight task tracking (future enhancement).

**Errors:** Team not found, agent not in team, A2A dispatch errors.

______________________________________________________________________

### Tool 5: collect_results

**Name:** `collect_results`

**Description:** Poll in-flight tasks until terminal state (blocking).

**Parameters:**

| Name              | Type   | Required | Description                   |
| ----------------- | ------ | -------- | ----------------------------- |
| `name`            | string | Yes      | Team name                     |
| `timeout_seconds` | number | No       | Polling timeout (default 300) |

**Return Structure:**

```json
{
  "status": "success|timeout|error",
  "results": {
    "<agent_name>": "artifact_text_or_error_message"
  },
  "error": "error message (if status=error)"
}
```

**Implementation:**

1. Load TeamSession from disk
1. Restore coordinator with timeout override
1. Call `collect_results()`
1. Return extracted artifacts

**Limitation:** This tool assumes in-flight task IDs were stored in the coordinator's `_in_flight` dict after a prior dispatch. However, since we reload the coordinator from disk, we lose this state. **Design choice**: This tool is for use within a single orchestration session where the coordinator stays alive. For multi-session collect, consider storing in-flight task IDs in the session JSON.

**Session Persistence:** No immediate updates (just reads session).

**Errors:** Timeout, poll errors, no tasks in flight.

______________________________________________________________________

### Tool 6: relay_message

**Name:** `relay_message`

**Description:** Relay a completed task's output to another agent.

**Parameters:**

| Name           | Type   | Required | Description                             |
| -------------- | ------ | -------- | --------------------------------------- |
| `name`         | string | Yes      | Team name                               |
| `src_task_id`  | string | Yes      | Source task ID to relay from            |
| `src_agent`    | string | Yes      | Source agent name (to fetch task)       |
| `dst_agent`    | string | Yes      | Destination agent name                  |
| `instructions` | string | Yes      | Additional instructions for destination |
| `api_key`      | string | No       | Optional API key                        |

**Return Structure:**

```json
{
  "status": "success|error",
  "task_id": "string",
  "state": "completed|failed|canceled",
  "output": "string (artifact text)",
  "error": "error message (if status=error)"
}
```

**Implementation:**

1. Load TeamSession from disk
1. Restore coordinator
1. Fetch source task via `coordinator._get_client(src_agent).get_task()`
1. Call `relay_output(src_task, dst_agent, instructions)`
1. Return resulting task

**Session Persistence:** No (relay is stateless from persistence perspective).

**Errors:** Team not found, source agent not in team, destination agent not in team, source task fetch error.

______________________________________________________________________

### Tool 7: dissolve_team_session

**Name:** `dissolve_team_session`

**Description:** Tear down an active team session.

**Parameters:**

| Name      | Type    | Required | Description                             |
| --------- | ------- | -------- | --------------------------------------- |
| `name`    | string  | Yes      | Team name                               |
| `api_key` | string  | No       | Optional API key                        |
| `force`   | boolean | No       | Skip confirmation (always true for MCP) |

**Return Structure:**

```json
{
  "status": "success|error",
  "team_id": "string",
  "message": "Team dissolved successfully",
  "error": "error message (if status=error)"
}
```

**Implementation:**

1. Load TeamSession from disk
1. Restore coordinator
1. Call `dissolve_team()`
1. Delete `.vault/logs/teams/{name}.json`

**Session Persistence:** Deletes persisted session file.

**Errors:** Team not found, dissolve errors.

______________________________________________________________________

### Tool 8: ping_team_members

**Name:** `ping_team_members`

**Description:** Check reachability of all team members.

**Parameters:**

| Name      | Type   | Required | Description      |
| --------- | ------ | -------- | ---------------- |
| `name`    | string | Yes      | Team name        |
| `api_key` | string | No       | Optional API key |

**Return Structure:**

```json
{
  "status": "success|partial|error",
  "results": {
    "<agent_name>": {
      "reachable": true,
      "url": "string"
    }
  },
  "error": "error message (if status=error)"
}
```

**Implementation:**

1. Load TeamSession from disk
1. Restore coordinator
1. Call `ping_agents()`
1. Update in-memory session member status (do NOT persist unless explicitly needed)
1. Return results

**Session Persistence:** No (read-only operation, status updates are in-memory only).

**Errors:** Team not found, ping errors.

______________________________________________________________________

## mcp.json Configuration

### Entry for vs-team-mcp

```json
{
  "mcpServers": {
    "vs-team-mcp": {
      "command": "python",
      "args": [".vaultspec/lib/scripts/team.py", "serve"],
      "stdio": true,
      "env": {
        "PYTHONPATH": ".vaultspec/lib/src:.vaultspec/lib/scripts"
      }
    }
  }
}
```

**Notes:**

- Assumes `team.py serve` command will be added (currently does not exist)
- Uses `stdio` transport (FastMCP-compatible)
- PYTHONPATH ensures imports resolve correctly

______________________________________________________________________

## Session Persistence Strategy

### Current State (CLI)

The CLI (`team.py`) already persists sessions via:

- Save: `_save_session(root, session)` → `.vault/logs/teams/{name}.json`
- Load: `_load_session(root, name)` → reconstructs TeamSession from JSON
- Delete: `_delete_session(root, name)` → removes file

**Serialized Fields:**

- `team_id`, `name`, `context_id`, `status`, `created_at`
- For each member: `name`, `url`, `status`, `card` (serialized as JSON dict)

### MCP Requirements

**Each MCP tool must:**

1. Load session from disk (if needed for the operation)
1. Restore coordinator with `restore_session()`
1. Perform the operation
1. Optionally save updated session back to disk

**Session mutations that require save:**

- `create_team`: Create new session file
- `dissolve_team_session`: Delete session file
- Future: `collect_results` with persisted in-flight tracking

______________________________________________________________________

## Async/Concurrency Considerations

### Context Manager Requirement

All tools that call `TeamCoordinator` methods must:

1. Create coordinator: `coord = TeamCoordinator(api_key=...)`
1. Use async context: `async with coord: await coord.form_team(...)`
1. OR manually ensure HTTP client: `coord._ensure_http_client()` then manually close

**For MCP server:** Use a single persistent coordinator instance (created once at server startup) shared across all tool calls, or create one per-tool (simpler, more isolated).

### Tool Call Serialization

MCP tools execute serially by default (one at a time). However, within a single tool, `dispatch_parallel()` and `collect_results()` internally use `asyncio.gather()` for concurrency.

**Implication:** It's safe to have multiple tools "in flight" from the MCP client perspective, as each tool call is a separate async context.

______________________________________________________________________

## Error Handling

### A2A-Level Errors

- Network errors (httpx): Propagate as tool error with error message
- Card fetch failures: Tool status = "error", error field populated
- Task dispatch errors: Tool status = "partial", failed_agents list populated

### Session-Level Errors

- Team not found: Tool status = "error", error message
- Corrupt session JSON: Tool status = "error", error message
- Missing required field: Tool status = "error", error message

### Timeout Errors

- `collect_results` timeout: Tool status = "timeout", error message, partial results included

______________________________________________________________________

## Future Enhancements

1. **Persistent In-Flight Tracking:** Store `_in_flight` map in session JSON so `collect_results` works across server restarts.
1. **Message History:** Optionally persist all dispatch/relay operations to audit log.
1. **Agent Health Monitoring:** Background health checks via `ping_agents()` with automatic member status sync.
1. **Task Result Caching:** Store completed task outputs in session for replay/audit.

______________________________________________________________________

## Implementation Checklist

- [ ] Create `team.py serve` MCP server entry point
- [ ] Use FastMCP with `stdio` transport
- [ ] Register 8 tools: create_team, get_team_status, list_teams, dispatch_task, collect_results, relay_message, dissolve_team_session, ping_team_members
- [ ] Each tool: parse params → load session → restore coordinator → call API → return JSON
- [ ] Handle errors: wrap exceptions as ToolError with meaningful messages
- [ ] Test: basic flow (create → dispatch → dissolve)
- [ ] Test: error cases (invalid team, unreachable agent, timeout)
- [ ] Update mcp.json with vs-team-mcp entry

______________________________________________________________________

## References

- **ADR:** `.vault/adr/2026-02-20-a2a-team-adr.md`
- **TeamCoordinator Audit:** `.vaultspec/lib/src/orchestration/team.py:113-562`
- **Team CLI Reference:** `.vaultspec/lib/scripts/team.py:1-499`
- **A2A Types:** `a2a.types` (Task, TaskState, Message, Part, AgentCard)
