---
tags:
  - '#reference'
  - '#gemini'
date: '2026-02-22'
related:
  - '[[2026-02-21-claude-acp-bidirectional-reference]]'
  - '[[2026-02-15-provider-parity-reference]]'
---

# Gemini ACP Bridge & A2A Executor Overhaul Reference

## Crates / Packages

| Package                          | Role                                                                                          |
| -------------------------------- | --------------------------------------------------------------------------------------------- |
| `acp` (Python)                   | ACP protocol SDK -- `Agent`, `Client`, `run_agent`, `spawn_agent_process`, `connect_to_agent` |
| `a2a` (Python)                   | A2A protocol SDK -- `AgentExecutor`, `TaskUpdater`, `EventQueue`, `DefaultRequestHandler`     |
| `@anthropic-ai/claude-code` (TS) | Claude Code TS SDK -- reference for ACP Agent patterns                                        |
| `google.adk`                     | Google Agent Development Kit -- `LlmAgent`, `Runner`, session services                        |
| `python-a2a`                     | Third-party A2A library -- `AgentManager` subprocess lifecycle                                |

## Files Audited

### Reference Codebases

| File                       | Path                                                                                | Role                                            |
| -------------------------- | ----------------------------------------------------------------------------------- | ----------------------------------------------- |
| gemini.py                  | `tmp-ref/acp-python-sdk/examples/gemini.py`                                         | Canonical Gemini ACP client example             |
| interfaces.py              | `tmp-ref/acp-python-sdk/src/acp/interfaces.py`                                      | Agent and Client protocol definitions           |
| transports.py              | `tmp-ref/acp-python-sdk/src/acp/transports.py`                                      | `spawn_stdio_transport` with defensive shutdown |
| core.py                    | `tmp-ref/acp-python-sdk/src/acp/core.py`                                            | `connect_to_agent`, `run_agent`                 |
| supervisor.py              | `tmp-ref/acp-python-sdk/src/acp/task/supervisor.py`                                 | `TaskSupervisor` background task management     |
| session_state.py           | `tmp-ref/acp-python-sdk/src/acp/contrib/session_state.py`                           | `SessionAccumulator` state tracking             |
| dispatcher.py              | `tmp-ref/acp-python-sdk/src/acp/task/dispatcher.py`                                 | `DefaultMessageDispatcher`                      |
| agent_executor.py          | `tmp-ref/a2a-python-sdk/src/a2a/server/agent_execution/agent_executor.py`           | `AgentExecutor` ABC                             |
| task_updater.py            | `tmp-ref/a2a-python-sdk/src/a2a/server/tasks/task_updater.py`                       | `TaskUpdater` with terminal state guards        |
| event_queue.py             | `tmp-ref/a2a-python-sdk/src/a2a/server/events/event_queue.py`                       | `EventQueue` bounded queue                      |
| default_request_handler.py | `tmp-ref/a2a-python-sdk/src/a2a/server/request_handlers/default_request_handler.py` | `DefaultRequestHandler` orchestration           |
| agent.ts                   | `tmp-ref/acp-claude-code/src/agent.ts`                                              | `ClaudeACPAgent` TS reference                   |
| agent_manager.py           | `tmp-ref/python-a2a/python_a2a/agent_flow/utils/agent_manager.py`                   | `AgentManager` subprocess lifecycle             |
| agent.py                   | `tmp-ref/a2a-educational/version_2_adk_agent/agents/google_adk/agent.py`            | `TellTimeAgent` Google ADK agent                |
| task_manager.py            | `tmp-ref/a2a-educational/version_2_adk_agent/agents/google_adk/task_manager.py`     | A2A task manager with ADK                       |

### Our Codebase

| File               | Path                                                      | Role                                        |
| ------------------ | --------------------------------------------------------- | ------------------------------------------- |
| gemini_bridge.py   | `src/vaultspec/protocol/acp/gemini_bridge.py`             | Gemini ACP bridge (broken scaffold)         |
| gemini_executor.py | `src/vaultspec/protocol/a2a/executors/gemini_executor.py` | Gemini A2A executor (unhardened)            |
| claude_bridge.py   | `src/vaultspec/protocol/acp/claude_bridge.py`             | Claude ACP bridge (gold standard to mirror) |

______________________________________________________________________

## 1. Subprocess Spawning for Gemini CLI

### Reference Pattern: ACP Python SDK `gemini.py`

The canonical reference for spawning Gemini CLI over ACP. Three-step resolution:

```python

# tmp-ref/acp-python-sdk/examples/gemini.py:263-272

def _resolve_gemini_cli(binary: str | None) -> str:
    if binary:
        return binary
    env_value = os.environ.get("ACP_GEMINI_BIN")
    if env_value:
        return env_value
    resolved = shutil.which("gemini")
    if resolved:
        return resolved
    raise FileNotFoundError("Unable to locate `gemini` CLI, provide --gemini path")
```

Spawn with `asyncio.create_subprocess_exec`, `--experimental-acp` flag, PIPE for stdin/stdout:

```python

# tmp-ref/acp-python-sdk/examples/gemini.py:290-304

cmd = [gemini_path, "--experimental-acp"]
if args.model:
    cmd += ["--model", args.model]
if args.sandbox:
    cmd.append("--sandbox")

proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=None,
)
```

### Reference Pattern: ACP SDK `spawn_stdio_transport`

Trimmed env with platform-specific variable lists to avoid leaking secrets:

```python

# tmp-ref/acp-python-sdk/src/acp/transports.py:13-30

DEFAULT_INHERITED_ENV_VARS = (
    ["APPDATA", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "PATH",
     "PATHEXT", "PROCESSOR_ARCHITECTURE", "SYSTEMDRIVE", "SYSTEMROOT",
     "TEMP", "USERNAME", "USERPROFILE"]
    if os.name == "nt"
    else ["HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER"]
)
```

Defensive shutdown sequence -- close stdin first, wait, escalate:

```python

# tmp-ref/acp-python-sdk/src/acp/transports.py:97-118

# Attempt graceful stdin shutdown first

if process.stdin is not None:
    try:
        process.stdin.write_eof()
    except (AttributeError, OSError, RuntimeError):
        process.stdin.close()
    with contextlib.suppress(Exception):
        await process.stdin.drain()
    with contextlib.suppress(Exception):
        process.stdin.close()

try:
    await asyncio.wait_for(process.wait(), timeout=shutdown_timeout)
except asyncio.TimeoutError:
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=shutdown_timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
```

### Our Gemini Bridge: Current State and Gaps

The bridge at `src/vaultspec/protocol/acp/gemini_bridge.py:208-307` spawns via `spawn_agent_process`, which wraps `spawn_stdio_transport` + `ClientSideConnection`. This is correct but has issues:

- **Windows `cmd.exe /c` workaround** (lines 223-238): Fragile. The SDK's `spawn_stdio_transport` already handles Windows platform differences. Our bridge should let the SDK handle this by passing the full env.
- **`os.environ.copy()` passed as env** (line 259): Defeats the SDK's env trimming. The reference uses `default_environment()` which only inherits safe variables.
- **Synchronous `subprocess.run` version check** (lines 215-221): Blocks the event loop. Should be removed or made async.
- **Missing `McpCapabilities` import** (line 194): Referenced but never imported -- will raise `NameError` at runtime.
- **No session resume** -- the bridge spawns a new child process per session but never stores or passes a native Gemini session ID for multi-turn resume.

### Blueprint: Subprocess Spawning

- Use `resolve_executable("gemini")` for CLI resolution (already exists at line 240 for non-Windows).
- Let `spawn_agent_process` handle env trimming -- do not pass `env=os.environ.copy()`.
- Remove the synchronous version check or convert to async.
- Fix the `McpCapabilities` import.
- For Windows, prefer `shutil.which("gemini")` to find the `.cmd` wrapper, then pass to `spawn_agent_process` directly.

______________________________________________________________________

## 2. Multi-Turn Session Management

### Reference Pattern: ACP Claude Code TS

The TypeScript reference extracts and stores the provider-native session ID for resume:

```typescript
// tmp-ref/acp-claude-code/src/agent.ts (conceptual)
// Sessions stored as Map<string, AgentSession>
// AgentSession includes:
//   pendingPrompt, abortController, claudeSessionId, permissionMode
// On subsequent prompt(), passes resume: session.claudeSessionId
```

### Reference Pattern: Our Claude Bridge (Gold Standard)

`src/vaultspec/protocol/acp/claude_bridge.py` captures and uses `claude_session_id`:

```python

# claude_bridge.py:670-680  -- Capturing session ID from SDK messages

msg_session_id = getattr(message, "session_id", None)
if (state and msg_session_id
        and msg_session_id != state.claude_session_id):
    state.claude_session_id = msg_session_id

# claude_bridge.py:842-843  -- Using it for resume in load_session

if state.claude_session_id:
    options.resume = state.claude_session_id
```

### Reference Pattern: Google ADK Session Management

The educational reference shows Gemini-native session management:

```python

# tmp-ref/a2a-educational/version_2_adk_agent/agents/google_adk/agent.py:100-115

session = await self._runner.session_service.get_session(
    app_name=self._agent.name,
    user_id=self._user_id,
    session_id=session_id
)
if session is None:
    session = await self._runner.session_service.create_session(...)
```

### Our Gemini Bridge: Current State and Gaps

`src/vaultspec/protocol/acp/gemini_bridge.py` spawns a child process per session and stores `child_session_id` in `_SessionState` (line 119). However:

- **No session resume capability**: The `_SessionState` dataclass has no field equivalent to `claude_session_id` for tracking the Gemini-native session across reconnections.
- **Missing `load_session` method**: The bridge has no implementation. The Claude bridge recovers sessions by reconstructing the SDK client with stored config (claude_bridge.py:782-861).
- **Missing `resume_session` method**: Same gap. The Claude bridge passes `options.resume = state.claude_session_id` (claude_bridge.py:904-905).
- **Missing `list_sessions` method**: The Claude bridge iterates `self._sessions` and returns `SessionInfo` objects (claude_bridge.py:982-1013).
- **Missing `fork_session` method**: The Claude bridge clones config into a new session ID (claude_bridge.py:924-980).
- **Missing `set_session_mode`**: The Claude bridge updates the sandbox callback on the active client (claude_bridge.py:1015-1036).
- **Missing `set_session_model`**: The Claude bridge updates the model on the active client options (claude_bridge.py:1038-1057).
- **Missing `set_config_option`**: The Claude bridge has a no-op implementation (claude_bridge.py:1059-1066).

### Blueprint: Session Management

- Add a `gemini_session_id: str | None` field to `_SessionState` for tracking the child's native session.
- Implement `load_session` following the Claude bridge pattern: look up stored state, rebuild child connection with stored config, pass native session ID if available.
- Implement `resume_session` as a thin wrapper over `load_session` logic.
- Implement `list_sessions` by iterating `self._sessions` and filtering by `cwd`.
- Implement `fork_session` by cloning stored config into a new child process.
- Implement `set_session_mode` and `set_session_model` by delegating to the child connection if supported, or storing for next session creation.
- Implement `set_config_option` as a no-op with debug logging.
- Declare session capabilities correctly in `initialize` -- currently claims `fork=None, list=None, resume=None` which advertises no support. Should advertise the implemented capabilities.

______________________________________________________________________

## 3. Retry and Error Handling

### Reference Pattern: A2A SDK `DefaultRequestHandler`

The `DefaultRequestHandler` tracks running agents and handles errors robustly:

```python

# tmp-ref/a2a-python-sdk default_request_handler.py:70-71

_running_agents: dict[str, asyncio.Task]
_background_tasks: set[asyncio.Task]
```

Error handling in streaming disconnect:

```python

# default_request_handler.py:388-395

except (asyncio.CancelledError, GeneratorExit):

    # Client disconnected: continue consuming and persisting events in background

    bg_task = asyncio.create_task(
        result_aggregator.consume_all(consumer)
    )
    bg_task.set_name(f'background_consume:{task_id}')
    self._track_background_task(bg_task)
    raise
```

Cleanup pattern:

```python

# default_request_handler.py:433-447

async def _cleanup_producer(self, producer_task, task_id):
    try:
        await producer_task
    except asyncio.CancelledError:
        logger.debug('Producer task %s was cancelled during cleanup', task_id)
    await self._queue_manager.close(task_id)
    async with self._running_agents_lock:
        self._running_agents.pop(task_id, None)
```

### Reference Pattern: ACP SDK `TaskSupervisor`

Background task tracking with error handler chain and graceful shutdown (cancel all, await all).

### Reference Pattern: python-a2a `AgentManager`

Subprocess health monitoring with retry:

```python

# tmp-ref/python-a2a/python_a2a/agent_flow/utils/agent_manager.py (conceptual)

# Connection retry loop: 3 attempts with 1s sleep between

# terminate() -> wait(5) -> kill() shutdown sequence

```

### Reference Pattern: Claude Bridge `MessageParseError`

The Claude bridge handles SDK parse errors gracefully:

```python

# claude_bridge.py:715-717

except MessageParseError as exc:
    logger.debug("Skipping unparseable SDK message: %s", exc)
    continue
```

### Our Gemini Bridge: Current State and Gaps

- **No retry on child process failure**: If `spawn_agent_process` fails or the child dies mid-session, the bridge does not attempt recovery.
- **No `MessageParseError`-equivalent handling**: The Gemini bridge forwards child updates through `GeminiProxyClient` but has no error recovery in the proxy worker (lines 134-143 catch generic `Exception` and log, but do not reconnect).
- **No subprocess health monitoring**: Unlike the python-a2a `AgentManager`, the bridge has a fire-and-forget `_monitor_exit` task (lines 276-279) that only logs -- no recovery action.

### Our Gemini Executor: Current State and Gaps

- **Bare `try/except`** around `run_subagent()` (lines 79-106): Catches all exceptions, marks task as failed. No retry.
- **No `CancelledError` handling**: If the asyncio task is cancelled externally, it will propagate unhandled.

### Blueprint: Error Handling

**ACP Bridge:**

- Add subprocess health monitoring that detects child death and attempts re-spawn with stored session config.
- Add a connection retry loop (3 attempts, exponential backoff) in `new_session` for transient spawn failures.
- Handle `asyncio.CancelledError` explicitly in the proxy worker.

**A2A Executor:**

- Add `asyncio.CancelledError` handling in `execute()` to clean up and mark task as cancelled.
- Add retry logic: configurable max retries (default 1) with exponential backoff for transient Gemini API errors.
- Track the running subagent task in a `_running_tasks: dict[str, asyncio.Task]` for proper cancel support.

______________________________________________________________________

## 4. Streaming Progress

### Reference Pattern: A2A SDK `TaskUpdater`

The `TaskUpdater` provides granular status updates with terminal state guards:

```python

# tmp-ref/a2a-python-sdk task_updater.py:65-108

async def update_status(self, state, message=None, final=False, ...):
    async with self._lock:
        if self._terminal_state_reached:
            raise RuntimeError(f'Task {self.task_id} is already in a terminal state.')
        if state in self._terminal_states:
            self._terminal_state_reached = True
            final = True
        await self.event_queue.enqueue_event(TaskStatusUpdateEvent(...))
```

Artifact streaming:

```python

# task_updater.py:110-152

async def add_artifact(self, parts, artifact_id=None, name=None,
                       append=None, last_chunk=None, ...):

    # Supports incremental artifact chunks with append/last_chunk flags

    await self.event_queue.enqueue_event(TaskArtifactUpdateEvent(...))
```

### Reference Pattern: A2A SDK `EventQueue`

Bounded `asyncio.Queue` (default 1024) with tap (child queues), close (graceful/immediate), and Python 3.12/3.13 `QueueShutDown` compatibility.

### Reference Pattern: ACP SDK `SessionAccumulator`

Merges ACP `SessionNotification` objects into immutable `SessionSnapshot` with subscriber pattern. Tracks tool calls, plan entries, mode, commands, messages. Auto-resets on session change.

### Reference Pattern: Claude Bridge Streaming

The Claude bridge streams incremental updates via `_emit_stream_event` (lines 1105-1235):

- `text_delta` -> `AgentMessageChunk`
- `thinking_delta` -> `AgentThoughtChunk`
- `input_json_delta` -> `ToolCallProgress` with partial tool arguments
- `content_block_start` with `tool_use` -> block index tracking
- `tool_use_error` -> `ToolCallProgress` with `failed` status

### Our Gemini Bridge: Current State

The Gemini bridge already has basic streaming via the `GeminiProxyClient` + `forward_update` pattern. It receives `ToolCallStart` and `ToolCallProgress` from the child and re-emits them, with tool kind mapping and content accumulation. This is reasonably correct but lacks:

- **No `SessionAccumulator`-style state tracking**: The bridge does not maintain a merged view of session state across notifications.
- **No `AgentThoughtChunk` emission**: Even if the child emits thinking events, the bridge only checks for `ToolCallStart` and `ToolCallProgress` in `forward_update` (lines 325-330) and passes everything else through verbatim.

### Our Gemini Executor: Current State and Gaps

- **No streaming at all**: The executor calls `run_subagent()` and waits for the full result (lines 80-86). Only emits a single `add_artifact` at the end (lines 90-93).
- **No incremental progress**: No `update_status` calls between `start_work` and `complete/failed`.
- **No artifact chunking**: Emits a single monolithic artifact instead of streaming chunks.

### Blueprint: Streaming

**A2A Executor:**

- Replace the blocking `run_subagent()` call with a streaming-capable variant that yields incremental results.
- Emit `update_status(TaskState.working)` periodically or on each chunk.
- Use `add_artifact` with `append=True` and `last_chunk=False` for incremental streaming, followed by a final `add_artifact` with `last_chunk=True`.
- Consider implementing a progress callback that the subagent invocation can call to emit intermediate artifacts.

**ACP Bridge:**

- The `forward_update` pass-through is adequate for streaming. No major changes needed beyond ensuring `AgentThoughtChunk` and other session update types are properly forwarded.

______________________________________________________________________

## 5. Cancel / Abort

### Reference Pattern: ACP Python SDK

Cancel is a notification (not a request) routed to the agent:

```python

# tmp-ref/acp-python-sdk/src/acp/interfaces.py:224-225

@param_model(CancelNotification)
async def cancel(self, session_id: str, **kwargs: Any) -> None: ...
```

The Gemini example tests confirm the cancel -> prompt returns "cancelled" stop_reason pattern:

```python

# tmp-ref/acp-python-sdk/tests/real_user/test_cancel_prompt_flow.py (conceptual)

# 1. Start a prompt (blocking)

# 2. Send cancel notification during prompt

# 3. Prompt returns with stop_reason="cancelled"

```

### Reference Pattern: ACP Claude Code TS

Per-session `AbortController` pattern:

```typescript
// tmp-ref/acp-claude-code/src/agent.ts (conceptual)
// Cancel: abortController.abort() + pendingPrompt.return()
// In streaming loop: check abortController.signal.aborted
```

### Reference Pattern: Claude Bridge

```python

# claude_bridge.py:747-761

async def cancel(self, session_id, **kwargs):
    self._cancelled = True
    state = self._sessions.get(session_id)
    if state:
        state.cancel_event.set()

    # Interrupt (not disconnect!) -- session stays alive for future prompts

    sdk_client = (state.sdk_client if state else None) or self._sdk_client
    if sdk_client is not None:
        try:
            await sdk_client.interrupt()
        except Exception:
            logger.exception("Error interrupting SDK client")
```

Key insight: The Claude bridge uses `interrupt()` which preserves the session for future prompts. `disconnect()` would kill it.

### Reference Pattern: A2A SDK `DefaultRequestHandler.on_cancel_task`

```python

# default_request_handler.py:124-185

async def on_cancel_task(self, params, context=None):

    # 1. Validate task exists and is not in terminal state

    # 2. Tap the event queue

    # 3. Call executor.cancel(context, queue)

    # 4. Cancel the producer asyncio.Task

    if producer_task := self._running_agents.get(task.id):
        producer_task.cancel()

    # 5. Consume remaining events

    # 6. Verify task ended in canceled state

```

### Our Gemini Bridge: Current State

```python

# gemini_bridge.py:353-358

async def cancel(self, session_id, **kwargs):
    state = self._sessions.get(session_id)
    if state:
        state.cancel_event.set()
        with contextlib.suppress(Exception):
            await state.child_conn.cancel(session_id=state.child_session_id)
```

This is structurally correct -- sets the event and delegates to the child. But the `cancel_event` is never checked during `prompt()` (the prompt just delegates to the child and awaits). If the child does not honor the cancel, the bridge hangs.

### Our Gemini Executor: Current State

```python

# gemini_executor.py:108-113

async def cancel(self, context, event_queue):
    task_id = context.task_id or ""
    context_id = context.context_id or ""
    updater = TaskUpdater(event_queue, task_id, context_id)
    logger.info("Cancelling task %s", task_id)
    await updater.cancel()
```

This is a **no-op**: it only publishes a cancelled status but never actually stops the running `run_subagent()` call. There is no reference to the running asyncio task.

### Blueprint: Cancel

**ACP Bridge:**

- Add a timeout on `prompt()` that checks `cancel_event` periodically. If the child does not return within a grace period after cancel, forcibly close the child connection.
- Follow the Claude bridge pattern: cancel preserves the session (interrupt, not disconnect).

**A2A Executor:**

- Store the running subagent `asyncio.Task` in an instance variable: `self._running_task: asyncio.Task | None`.

- In `cancel()`, call `self._running_task.cancel()` if it exists, then publish the cancelled status.

- In `execute()`, wrap the subagent call in a try/except for `asyncio.CancelledError` and mark the task as cancelled.

- Pattern from `DefaultRequestHandler`:

  ```python
  if producer_task := self._running_tasks.get(task_id):
    producer_task.cancel()
  ```

______________________________________________________________________

## 6. ACP Protocol Compliance

### Full Agent Protocol (from `acp.interfaces.Agent`)

The ACP `Agent` protocol defines these required methods:

| Method              | Signature                                                                      | Claude Bridge | Gemini Bridge |
| ------------------- | ------------------------------------------------------------------------------ | :-----------: | :-----------: |
| `initialize`        | `(protocol_version, client_capabilities?, client_info?) -> InitializeResponse` |      YES      |      YES      |
| `new_session`       | `(cwd, mcp_servers?) -> NewSessionResponse`                                    |      YES      |      YES      |
| `load_session`      | `(cwd, session_id, mcp_servers?) -> LoadSessionResponse?`                      |      YES      |  **MISSING**  |
| `list_sessions`     | `(cursor?, cwd?) -> ListSessionsResponse`                                      |      YES      |  **MISSING**  |
| `set_session_mode`  | `(mode_id, session_id) -> SetSessionModeResponse?`                             |      YES      |  **MISSING**  |
| `set_session_model` | `(model_id, session_id) -> SetSessionModelResponse?`                           |      YES      |  **MISSING**  |
| `set_config_option` | `(config_id, session_id, value) -> SetSessionConfigOptionResponse?`            |      YES      |  **MISSING**  |
| `authenticate`      | `(method_id) -> AuthenticateResponse?`                                         |      YES      |      YES      |
| `prompt`            | `(prompt, session_id) -> PromptResponse`                                       |      YES      |      YES      |
| `fork_session`      | `(cwd, session_id, mcp_servers?) -> ForkSessionResponse`                       |      YES      |  **MISSING**  |
| `resume_session`    | `(cwd, session_id, mcp_servers?) -> ResumeSessionResponse`                     |      YES      |  **MISSING**  |
| `cancel`            | `(session_id) -> None`                                                         |      YES      |      YES      |
| `ext_method`        | `(method, params) -> dict`                                                     |      YES      |  **MISSING**  |
| `ext_notification`  | `(method, params) -> None`                                                     |      YES      |  **MISSING**  |
| `on_connect`        | `(conn: Client) -> None`                                                       |      YES      |      YES      |

**Missing methods: 9 out of 15.** The bridge implements only the bare minimum: `initialize`, `new_session`, `prompt`, `cancel`, `authenticate`, `on_connect`.

### Capability Declaration Bug

```python

# gemini_bridge.py:192-206

agent_capabilities=AgentCapabilities(
    load_session=True,                              # <-- Claims support
    mcp_capabilities=McpCapabilities(http=True, sse=True),  # <-- McpCapabilities not imported
    session_capabilities=SessionCapabilities(
        fork=None,      # <-- Correctly advertises no fork
        list=None,      # <-- Correctly advertises no list
        resume=None,    # <-- Correctly advertises no resume
    ),
    ...
)
```

Issues:

- `load_session=True` claims support but no `load_session` method exists.
- `McpCapabilities` is referenced but never imported -- **will raise `NameError`**.
- Session capabilities correctly say `None` for fork/list/resume, but once implemented they should be set to their respective capability objects.

### Blueprint: Protocol Compliance

Priority implementation order:

1. **Fix `McpCapabilities` import** -- critical, runtime crash.
1. **Fix `load_session=True` claim** -- either implement `load_session` or set to `False`.
1. **Implement `ext_method`/`ext_notification`** -- trivial no-ops, matches Claude bridge pattern.
1. **Implement `set_session_mode`/`set_session_model`/`set_config_option`** -- store config, delegate to child if supported.
1. **Implement `list_sessions`** -- iterate `self._sessions`, return `SessionInfo` list.
1. **Implement `load_session`/`resume_session`** -- requires session resume infrastructure (see Section 2).
1. **Implement `fork_session`** -- clone config, spawn new child process.
1. **Update capability declaration** -- set `SessionForkCapabilities()`, `SessionListCapabilities()`, `SessionResumeCapabilities()` as methods are implemented.

______________________________________________________________________

## Summary: Gap Matrix

### Gemini ACP Bridge (`gemini_bridge.py`)

| Concern                          | Status                | Severity | Action                                        |
| -------------------------------- | --------------------- | -------- | --------------------------------------------- |
| `McpCapabilities` import         | **BROKEN**            | P0       | Add import or remove reference                |
| `load_session=True` with no impl | **LIE**               | P0       | Implement or set to False                     |
| `os.environ.copy()` env leak     | **SECURITY**          | P1       | Use `default_environment()` or let SDK handle |
| Synchronous `subprocess.run`     | **BLOCKS EVENT LOOP** | P1       | Remove or make async                          |
| Missing 7 Agent methods          | **INCOMPLETE**        | P2       | Implement per priority list above             |
| No session resume                | **MISSING**           | P2       | Add `gemini_session_id` tracking              |
| No subprocess recovery           | **FRAGILE**           | P2       | Add health monitoring + re-spawn              |
| Windows `cmd.exe /c` workaround  | **FRAGILE**           | P3       | Simplify via `shutil.which`                   |

### Gemini A2A Executor (`gemini_executor.py`)

| Concern                      | Status      | Severity | Action                                 |
| ---------------------------- | ----------- | -------- | -------------------------------------- |
| Cancel is no-op              | **BROKEN**  | P0       | Track running task, cancel on request  |
| No `CancelledError` handling | **BROKEN**  | P1       | Add try/except in execute()            |
| No streaming progress        | **MISSING** | P2       | Add incremental artifact emission      |
| No retry logic               | **MISSING** | P2       | Add configurable retry with backoff    |
| No session management        | **MISSING** | P3       | Stateless design is acceptable for A2A |

______________________________________________________________________

## Key Architectural Patterns to Adopt

### From Claude Bridge (Internal Gold Standard)

- DI pattern: `client_factory`, `options_factory` for testability
- Per-session `_SessionState` dataclass with all relevant state
- `cancel_event` per session, checked in streaming loop
- `claude_session_id` capture for multi-turn resume
- `MessageParseError` skip-and-continue pattern

### From ACP Python SDK (External Reference)

- `spawn_stdio_transport` with trimmed env and defensive shutdown
- `SessionAccumulator` for merged session state tracking
- `TaskSupervisor` for background task management with error handlers

### From A2A Python SDK (External Reference)

- `TaskUpdater` with terminal state guards and `asyncio.Lock`
- `DefaultRequestHandler._running_agents` for cancel support
- Background task tracking with `_track_background_task` pattern
- `EventConsumer` + `ResultAggregator` for streaming
