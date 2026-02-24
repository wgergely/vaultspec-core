---
tags:
  - "#adr"
  - "#gemini-overhaul"
date: "2026-02-22"
related:
  - "[[2026-02-22-gemini-acp-bridge-adr]]"
  - "[[2026-02-22-gemini-acp-audit-research]]"
  - "[[2026-02-22-gemini-acp-audit-expanded]]"
  - "[[2026-02-22-gemini-overhaul-reference]]"
  - "[[2026-02-20-a2a-team-gemini-research]]"
  - "[[2026-02-21-gemini-bridge-auth-research]]"
  - "[[2026-02-21-gemini-provider-auth-strategy-adr]]"
  - "[[2026-02-21-claude-a2a-overhaul-adr]]"
  - "[[2026-02-22-gemini-acp-bridge-review]]"
  - "[[2026-02-22-gemini-a2a-review]]"
---

# `gemini-overhaul` adr: Gemini ACP Bridge Rewrite and A2A Executor Hardening | (**status:** `superseded`)

**SUPERSEDED** — This ADR is fully superseded by
`[[2026-02-24-subagent-protocol-adr]]` (Unified A2A Protocol Stack — Full
Rewrite). The Gemini ACP bridge rewrite decided here is moot — all ACP bridges
are being deleted. A2A executor hardening patterns remain valid as
implementation guidance. Do not treat this document as authoritative.

**Supersedes:** `[[2026-02-22-gemini-acp-bridge-adr]]`

## Problem Statement

The Gemini provider has two broken components that prevent it from participating in multi-agent teams or providing ACP feature parity with Claude.

**Component 1: Gemini ACP Bridge** (`src/vaultspec/protocol/acp/gemini_bridge.py`) -- a partially-complete scaffold with 4 CRITICAL and 6 HIGH issues identified in `[[2026-02-22-gemini-acp-bridge-review]]`. The bridge does not compile (`McpCapabilities` is referenced but never imported, causing `NameError` at runtime), has a protocol-violating `authenticate()` signature, implements only 6 of 15 required `Agent` protocol methods, has no DI mechanism (all 7 tests fail at fixture setup), is never wired into the provider (dead code), has 17 unused imports, leaks asyncio tasks, and silently drops `TodoWrite` events instead of converting them to `AgentPlanUpdate` notifications. The `[[2026-02-22-gemini-acp-bridge-review]]` status is `FAIL`.

**Component 2: Gemini A2A Executor** (`src/vaultspec/protocol/a2a/executors/gemini_executor.py`) -- functional for basic single-turn tasks but lacking the hardening that `ClaudeA2AExecutor` received in `[[2026-02-21-claude-a2a-overhaul-adr]]`. Five HIGH issues identified in `[[2026-02-22-gemini-a2a-review]]`: no retry on transient errors, no streaming progress events, no session resume via `context_id`, cancel is a no-op (emits A2A status but never terminates the subprocess), and no concurrency protection. The review status is `REVISION REQUIRED`.

The auth layer (`src/vaultspec/protocol/providers/gemini.py`) is production-ready and fully compliant with `[[2026-02-21-gemini-provider-auth-strategy-adr]]`. It is not modified by this ADR.

## Considerations

### Current State of the Bridge (Code Audit)

The bridge at `src/vaultspec/protocol/acp/gemini_bridge.py` (383 lines) was written against `[[2026-02-22-gemini-acp-bridge-adr]]` but the implementation diverged from the plan:

- **Lines 27-59**: Import 17 symbols from `acp.schema` that are never used (`AgentMessageChunk`, `AgentPlanUpdate`, `AgentThoughtChunk`, `ForkSessionResponse`, `ListSessionsResponse`, `LoadSessionResponse`, `ResumeSessionResponse`, `SessionForkCapabilities`, `SessionInfo`, `SessionInfoUpdate`, `SessionListCapabilities`, `SessionResumeCapabilities`, `TerminalToolCallContent`, `ToolCallUpdate`, `UserMessageChunk`, `AvailableCommandsUpdate`, `CurrentModeUpdate`). These are the imports for the 9 missing methods.
- **Line 170**: Constructor accepts only `model` and `debug`. No `spawn_fn` or equivalent DI parameter. The test file was written expecting `spawn_fn=mock_spawn_fn` but this was never added.
- **Line 194**: `McpCapabilities(http=True, sse=True)` -- `McpCapabilities` is never imported. Runtime `NameError`.
- **Lines 192-206**: Declares `load_session=True` and `SessionCapabilities(fork=None, list=None, resume=None)`. Claims load support but has no `load_session` method. Advertises no fork/list/resume.
- **Lines 215-221**: Synchronous `subprocess.run(["gemini", "--version"], ...)` blocks the event loop.
- **Lines 223-238**: Windows-specific `cmd.exe /c` workaround is fragile. The SDK's `spawn_stdio_transport` already handles platform differences.
- **Line 259**: `env=os.environ.copy()` defeats the SDK's env trimming (`default_environment()` only inherits safe variables).
- **Lines 265-279**: Two `asyncio.create_task` calls for `_read_stderr` and `_monitor_exit` with no task tracking. Resource leak on session cleanup.
- **Lines 131-143**: `GeminiProxyClient._worker` infinite loop with no clean shutdown path. Never cancelled by `close()`.
- **Lines 333-335**: `TodoWrite` interception drops the event silently instead of converting to `AgentPlanUpdate`.
- **Line 360**: `authenticate(self, **kwargs)` drops the required `method_id` positional parameter. Protocol violation.

**Conclusion**: The scaffold is not salvageable through patching. The number of structural issues (wrong constructor, wrong protocol signatures, missing DI, missing 9 methods, no cleanup) means every public method needs rewriting. A clean rewrite following `claude_bridge.py` patterns is less risky and less effort than incremental patches.

### Current State of the Executor (Code Audit)

The executor at `src/vaultspec/protocol/a2a/executors/gemini_executor.py` (114 lines) is a correct minimal implementation matching the original `[[2026-02-15-a2a-adr]]` Phase 4 skeleton. Its DI pattern (`run_subagent` constructor parameter) follows project conventions. The issue is not correctness but missing hardening features that `ClaudeA2AExecutor` now has, creating a significant parity gap for team readiness.

### Claude Implementations as Gold Standard

The Claude ACP bridge (`claude_bridge.py`) implements all 15 Agent protocol methods, uses DI via `client_factory` and `options_factory`, captures `claude_session_id` for multi-turn resume, converts `TodoWrite` to `AgentPlanUpdate` with proper `PlanEntry` objects, handles `MessageParseError` via skip-and-continue, and manages per-session `_SessionState` dataclasses with `cancel_event` for non-destructive cancellation.

The Claude A2A executor (`claude_executor.py`) provides bounded retry (max 3, exponential backoff), streaming progress (throttled `TaskState.working` updates), session resume via `context_id` -> `session_id` mapping, non-destructive cancel via `_cancel_events` and `sdk_client.interrupt()`, and concurrency protection via `asyncio.Lock` on `_active_clients` and `_session_ids`.

### Reference Architecture

Per `[[2026-02-22-gemini-overhaul-reference]]`:

- **ACP Python SDK** (`tmp-ref/acp-python-sdk`): `spawn_stdio_transport` with trimmed env and defensive shutdown (close stdin -> wait -> terminate -> kill). `SessionAccumulator` for state tracking.
- **ACP SDK Gemini Example** (`tmp-ref/acp-python-sdk/examples/gemini.py`): Three-step CLI resolution via explicit path, `ACP_GEMINI_BIN` env var, then `shutil.which("gemini")`. Spawn via `asyncio.create_subprocess_exec` with `--experimental-acp`, PIPE stdin/stdout.
- **A2A Python SDK** (`tmp-ref/a2a-python-sdk`): `TaskUpdater` with terminal state guards and `asyncio.Lock`. `DefaultRequestHandler._running_agents` dict for cancel support with `asyncio.Task` tracking.

### Subprocess Lifecycle

The Gemini CLI in `--experimental-acp` mode is a subprocess that speaks ACP over stdio. Per `[[2026-02-20-a2a-team-gemini-research]]`, each ACP session spawns a fresh process. The `--resume` flag restores session context from `~/.gemini/tmp/<project_hash>/chats/`, but ACP session resume restores configuration, not conversation context. For the bridge, per-session spawning (matching the Claude bridge pattern) is the correct approach -- `spawn_agent_process` from the ACP SDK handles the connection lifecycle.

### No-Mocking Constraint

The project bans all mocking. Both the bridge and executor must use constructor-injected DI for testability. The Claude bridge accepts `client_factory` and `options_factory`. The Gemini executor already accepts `run_subagent`. The Gemini bridge must accept a `spawn_fn` callable that defaults to `spawn_agent_process` from the ACP SDK.

## Constraints

- **No mocking** -- DI-injected test doubles only. Constructor injection for all external dependencies.
- **Auth layer unchanged** -- `GeminiProvider` auth wrangling in `gemini.py` is compliant with `[[2026-02-21-gemini-provider-auth-strategy-adr]]` and must not be modified.
- **Follow Claude patterns** -- the Claude bridge and executor are the gold standard. Deviations require explicit justification.
- **Backward compatibility** -- `GeminiA2AExecutor` public API (`__init__` signature, `execute`, `cancel`) must not break. New parameters are keyword-only with defaults.
- **This ADR supersedes** `[[2026-02-22-gemini-acp-bridge-adr]]`. The previous ADR led to the broken implementation. This ADR replaces all its decisions.
- **Test baseline** -- all existing non-E2E tests must continue passing. New tests must cover all new functionality.

## Implementation

Seven decisions addressing the bridge rewrite, executor hardening, and integration.

### Decision 1: Full Rewrite of the ACP Bridge

**Decision**: Rewrite `src/vaultspec/protocol/acp/gemini_bridge.py` from scratch, using `claude_bridge.py` as the structural template.

**Rationale**: The current scaffold has 4 CRITICAL issues (runtime crash, protocol violation, test failure, missing 9/15 methods) and 6 HIGH issues. Every public method has defects. Patching would require rewriting every method anyway while carrying the risk of inheriting structural problems (wrong `_SessionState` fields, missing DI, leaked tasks). A clean rewrite using the Claude bridge as a template is faster, safer, and produces a more maintainable result.

**What the rewrite preserves from the scaffold**:

- `_map_tool_kind()` function (lines 71-85) -- correct and matches Claude bridge.
- `_get_tool_call_content()` function (lines 88-108) -- correct for structured diffs.
- `GeminiProxyClient` pattern (lines 127-166) -- structurally correct, needs cleanup path added.
- `_SessionState` dataclass concept (lines 111-124) -- needs additional fields.

**What the rewrite replaces**:

- Constructor: add `spawn_fn` DI parameter, remove `get_config()` coupling.
- `initialize()`: fix `McpCapabilities` import, set correct session capabilities.
- `new_session()`: remove synchronous version check, remove Windows `cmd.exe` workaround (use `shutil.which` + SDK `spawn_agent_process`), remove `os.environ.copy()` (let SDK handle env trimming), add task tracking for background tasks.
- `prompt()`: add `cancel_event` check in the response wait path, add timeout.
- `cancel()`: add forced close on timeout if child does not honor cancel.
- `authenticate()`: fix signature to `(self, method_id: str, **kwargs)`.
- `close()`: cancel proxy client worker tasks, clean up background tasks.
- Add all 9 missing methods.

### Decision 2: ACP Agent Protocol Method Coverage

**Decision**: Implement all 15 Agent protocol methods. 6 methods (`initialize`, `new_session`, `prompt`, `cancel`, `authenticate`, `on_connect`) have real logic. 5 methods (`load_session`, `resume_session`, `list_sessions`, `fork_session`, `close`) have session management logic. 4 methods (`set_session_mode`, `set_session_model`, `set_config_option`, `ext_method`, `ext_notification`) are minimal implementations.

Method implementation strategy:

| Method | Implementation | Notes |
|--------|---------------|-------|
| `on_connect` | Store connection reference | Same as current |
| `initialize` | Return capabilities with correct imports | Fix `McpCapabilities`, advertise real capabilities |
| `new_session` | Spawn child via `spawn_fn`, ACP handshake | Remove sync version check, use SDK env trimming |
| `prompt` | Proxy to child, check `cancel_event` | Add timeout and cancel check |
| `cancel` | Set event, delegate to child, force-close on timeout | Follow Claude bridge: interrupt, not disconnect |
| `authenticate` | Fix signature `(self, method_id, **kwargs)`, return `AuthenticateResponse()` | Gemini auth is env-based, not ACP-negotiated |
| `load_session` | Look up stored state, rebuild child connection | Mirror Claude bridge lines 782-861 |
| `resume_session` | Thin wrapper over `load_session` logic | Mirror Claude bridge lines 904-905 |
| `list_sessions` | Iterate `self._sessions`, return `SessionInfo` list | Mirror Claude bridge lines 982-1013 |
| `fork_session` | Clone config into new child process | Mirror Claude bridge lines 924-980 |
| `set_session_mode` | Store mode, delegate to child if supported | Sandbox -> `--sandbox` on next spawn |
| `set_session_model` | Store model, delegate to child if supported | Model -> `--model` on next spawn |
| `set_config_option` | No-op with debug log | Same as Claude bridge lines 1059-1066 |
| `ext_method` | Return empty dict | Same as Claude bridge |
| `ext_notification` | No-op | Same as Claude bridge |
| `close` | Cancel all proxy workers, close all exit stacks, clear sessions | Fix resource leaks |

**Capability declaration** (correcting the current false claims):

```python
agent_capabilities=AgentCapabilities(
    load_session=True,
    session_capabilities=SessionCapabilities(
        fork=SessionForkCapabilities(),
        list=SessionListCapabilities(),
        resume=SessionResumeCapabilities(),
    ),
    prompt_capabilities=PromptCapabilities(
        image=True,
        audio=True,
        embedded_context=True,
    ),
)
```

Note: `McpCapabilities` is removed entirely. It was incorrectly used in the scaffold. The Claude bridge does not advertise `McpCapabilities` in its `initialize()` response -- MCP server configuration is passed via `new_session(mcp_servers=...)`, not declared as a static capability.

### Decision 3: Gemini Subprocess Lifecycle

**Decision**: Spawn per-session via `spawn_agent_process` from the ACP SDK. Use `shutil.which("gemini")` for CLI resolution. Let the SDK handle env trimming. No synchronous version check.

**Spawn flow**:

1. Resolve CLI path: `shutil.which("gemini")`. If `None`, raise `FileNotFoundError` with actionable message.
2. Build args: `[gemini_path, "--experimental-acp", "--model", model]` plus optional `--sandbox`, `--allowed-tools`, `--approval-mode`, `--output-format`.
3. Call `spawn_fn(proxy_client, gemini_path, *args, cwd=cwd)`. The default `spawn_fn` is `spawn_agent_process` which internally calls `spawn_stdio_transport` with trimmed env and defensive shutdown.
4. Store the returned `(child_conn, proc)` in `_SessionState`.
5. Track background tasks (`_read_stderr`, `_monitor_exit`) in `_SessionState.background_tasks: list[asyncio.Task]` for cleanup.

**What is removed**:

- Synchronous `subprocess.run(["gemini", "--version"], ...)` (lines 215-221). Blocks the event loop and provides no value -- if Gemini is missing, the spawn will fail with a clear error.
- Windows `cmd.exe /c` workaround (lines 223-238). `shutil.which("gemini")` resolves to `gemini.cmd` on Windows. `spawn_agent_process` handles it.
- `env=os.environ.copy()` (line 259). The SDK's `spawn_stdio_transport` uses `default_environment()` which only inherits platform-safe variables. Passing the full env defeats this security measure.

**DI for the spawn callable**:

```python
def __init__(
    self,
    *,
    model: str = GeminiModels.LOW,
    debug: bool = False,
    spawn_fn: Callable[..., Any] | None = None,
) -> None:
    self._spawn_fn = spawn_fn or spawn_agent_process
```

Tests inject a `spawn_fn` that returns a `(MockChildConn, MockChildProc)` tuple without spawning a real subprocess.

### Decision 4: Session Resume for Gemini

**Decision**: Track the child's native session ID in `_SessionState.gemini_session_id`. Use it for session reconstruction on `load_session` and `resume_session`. Do not use Gemini CLI's `--resume` flag (it operates on file-based session history, not ACP session state).

**`_SessionState` additions**:

```python
@dataclasses.dataclass
class _SessionState:
    session_id: str
    cwd: str
    model: str
    mode: str
    child_conn: ClientSideConnection
    child_proc: asyncio.subprocess.Process
    child_session_id: str
    exit_stack: contextlib.AsyncExitStack
    gemini_session_id: str | None = None       # Native session ID from child
    mcp_servers: list[Any] | None = None        # For session reconstruction
    background_tasks: list[asyncio.Task] = ...  # For cleanup
    created_at: str = ...
    cancel_event: asyncio.Event = ...
    tool_call_contents: dict[str, list[Any]] = ...
    todo_write_tool_call_ids: set[str] = ...
```

**`load_session` flow** (mirroring Claude bridge):

1. Look up `session_id` in `self._sessions`.
2. If found and child process is alive, return the existing session.
3. If found but child process has exited, reconstruct: spawn a new child using stored config (`cwd`, `model`, `mode`, `mcp_servers`), perform ACP handshake, create new child session, update `_SessionState` with new `child_conn` and `child_proc`.
4. If not found, raise appropriate error.

**`resume_session` flow**: Same as `load_session` but semantically signals intent to continue conversation. Delegates to `load_session` internally.

**`list_sessions` flow**: Iterate `self._sessions`, filter by `cwd` if provided, return `SessionInfo` objects with `session_id`, `created_at`, and `cwd`.

**`fork_session` flow**: Clone the stored config from the source session, spawn a new child process with the same parameters, create a new `_SessionState` with a fresh `session_id`, return the new session ID.

### Decision 5: Harden the A2A Executor

Five changes to `GeminiA2AExecutor`, mirroring the `ClaudeA2AExecutor` hardening in `[[2026-02-21-claude-a2a-overhaul-adr]]`.

**5a. Bounded retry with exponential backoff**:

Add `max_retries: int = 3` and `retry_base_delay: float = 1.0` constructor parameters. Wrap the `run_subagent()` call in a retry loop. On failure, classify the exception:

- **Retryable**: `subprocess.TimeoutExpired`, `ConnectionError`, `OSError`, and any exception whose string representation contains "rate_limit", "timeout", or "connection".
- **Non-retryable**: `FileNotFoundError` (missing executable), `ValueError`, `TypeError`, and all other exceptions.

On retryable failure, emit `TaskState.working` status with retry count, sleep for `retry_base_delay * 2^attempt` seconds, and retry. After `max_retries` exhausted, fail the task.

**5b. Streaming progress events**:

The current `run_subagent()` interface is blocking (returns `SubagentResult` after full completion). True streaming requires changes to `run_subagent()` which is out of scope.

Interim solution: spawn a background `asyncio.Task` that emits periodic `TaskState.working` heartbeat updates (every 5 seconds) while `run_subagent()` is running. This prevents A2A client timeouts and provides observability. The heartbeat task is cancelled when `run_subagent()` completes.

```python
async def _heartbeat(self, updater: TaskUpdater, cancel_event: asyncio.Event) -> None:
    while not cancel_event.is_set():
        await asyncio.sleep(5.0)
        with contextlib.suppress(RuntimeError):
            await updater.update_status(TaskState.working)
```

**5c. Non-destructive cancel with subprocess termination**:

Add `_running_tasks: dict[str, asyncio.Task]` and `_cancel_events: dict[str, asyncio.Event]` instance variables protected by `asyncio.Lock`.

In `execute()`:

- Wrap the `run_subagent()` call in `asyncio.create_task()` and store in `_running_tasks[task_id]`.
- Register a per-task `asyncio.Event` in `_cancel_events[task_id]`.
- Handle `asyncio.CancelledError` in the try/except to mark the task as cancelled.

In `cancel()`:

- Set `_cancel_events[task_id]` to signal the heartbeat to stop.
- Call `_running_tasks[task_id].cancel()` to cancel the in-flight asyncio task.
- Emit `updater.cancel()` after the task is cancelled.

```python
async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
    task_id = context.task_id or ""
    context_id = context.context_id or ""
    updater = TaskUpdater(event_queue, task_id, context_id)
    async with self._tasks_lock:
        if event := self._cancel_events.get(task_id):
            event.set()
        if task := self._running_tasks.get(task_id):
            task.cancel()
    await updater.cancel()
```

**5d. Concurrency protection**:

Add `asyncio.Lock` instances for all shared mutable state:

- `_tasks_lock` protects `_running_tasks` and `_cancel_events`.
- `_session_ids_lock` protects `_session_ids` (once session resume is added).

**5e. Session resume via context_id**:

Add `_session_ids: dict[str, str]` mapping `context_id` to a session identifier. Currently, `run_subagent()` does not accept a `resume_session_id` parameter, so full session resume requires upstream changes. For now:

- Store the `context_id` -> task mapping for future use.
- Document this as a known limitation that will be resolved when `run_subagent()` gains a `resume_session_id` parameter.
- The infrastructure (locks, dict, lookup in `execute()`) is built now so it is ready when the upstream change lands.

### Decision 6: Provider Integration

**Decision**: Update `GeminiProvider.prepare_process()` to spawn the bridge instead of the raw CLI.

The provider currently builds a `ProcessSpec` with `executable=gemini` and `args=["--experimental-acp", ...]`. After this change:

```python
executable = sys.executable  # Python interpreter
args = [
    "-m", "vaultspec.protocol.acp.gemini_bridge",
    "--model", model,
]
if debug:
    args.append("--debug")
```

Environment variables for the bridge to read:

- `VAULTSPEC_AGENT_MODE`: sandbox mode (`"read-only"` or `"read-write"`)
- `VAULTSPEC_ROOT_DIR`: workspace root
- `VAULTSPEC_ALLOWED_TOOLS`: comma-separated tool names
- `VAULTSPEC_GEMINI_APPROVAL_MODE`: Gemini approval mode
- `VAULTSPEC_OUTPUT_FORMAT`: output format

The bridge reads these from the environment in its `__init__` rather than calling `get_config()` directly -- this decouples the bridge from the config system and makes it testable.

Export `GeminiACPBridge` from `src/vaultspec/protocol/acp/__init__.py`:

```python
from .gemini_bridge import GeminiACPBridge

__all__ = [
    "ClaudeACPBridge",
    "GeminiACPBridge",
    "SessionLogger",
    "SubagentClient",
    "SubagentError",
    "SubagentResult",
]
```

### Decision 7: DI Pattern for Testing

**Decision**: Both the bridge and executor accept constructor-injected callables for all external dependencies. Test doubles are plain classes or functions passed via constructor -- no mocking.

**Bridge DI**:

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `model` | `str` | `GeminiModels.LOW` | Gemini model identifier |
| `debug` | `bool` | `False` | Enable debug logging |
| `spawn_fn` | `Callable` | `spawn_agent_process` | Subprocess spawner |

The `spawn_fn` callable receives `(client, executable, *args, cwd=cwd)` and returns an async context manager yielding `(ClientSideConnection, Process)`. Test doubles return a `(FakeChildConn, FakeChildProc)` pair.

Bridge no longer reads `get_config()` in `__init__`. Configuration comes from environment variables (set by the provider) or constructor parameters. This eliminates the config-system dependency in tests.

**Executor DI** (unchanged from current, plus new parameters):

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `root_dir` | `pathlib.Path` | required | Workspace root |
| `model` | `str` | `GeminiModels.LOW` | Model identifier |
| `agent_name` | `str` | `"vaultspec-researcher"` | Agent definition name |
| `run_subagent` | `Callable` | `_default_run_subagent` | Subagent spawner |
| `max_retries` | `int` | `3` | Max retry attempts |
| `retry_base_delay` | `float` | `1.0` | Base delay for backoff |

**Test double pattern** (matching the existing `_RunSubagentRecorder` in `test_gemini_executor.py`):

```python
class _FakeSpawnFn:
    """Records spawn calls and returns a fake connection."""
    def __init__(self, child_conn, child_proc):
        self.calls = []
        self._conn = child_conn
        self._proc = child_proc

    @contextlib.asynccontextmanager
    async def __call__(self, client, executable, *args, **kwargs):
        self.calls.append((executable, args, kwargs))
        yield self._conn, self._proc
```

This follows the exact pattern established by `ClaudeACPBridge`'s test infrastructure and the existing `GeminiA2AExecutor` DI pattern.

## Rationale

### Why Rewrite Instead of Patch

The scaffold has structural defects at every layer: wrong constructor (no DI), wrong protocol signatures (`authenticate` missing `method_id`), wrong capability declarations (`load_session=True` with no implementation, `McpCapabilities` not imported), wrong subprocess management (`os.environ.copy()`, sync version check, Windows workaround), missing 9 of 15 protocol methods, and resource leaks (untracked tasks, uncancelled workers). Patching each defect individually would touch every method, every import, and the constructor -- effectively a rewrite but with the cognitive overhead of working around existing broken code. A clean rewrite from the Claude bridge template is faster, produces cleaner code, and eliminates the risk of inheriting subtle structural issues.

### Why Follow Claude Patterns Exactly

The Claude bridge and executor are battle-tested: they pass all unit tests, integration tests, and E2E tests. Their DI patterns, session management, cancel semantics, and streaming strategies are proven. Diverging from these patterns without justification introduces unnecessary risk and makes cross-provider maintenance harder. Where Gemini's architecture differs (subprocess-based vs SDK-based), the patterns are adapted to fit, but the structural decisions (per-session state dataclass, cancel event semantics, DI constructors, capability declaration) are replicated exactly.

### Why Heartbeat Instead of True Streaming

The Gemini executor wraps `run_subagent()` which returns a `SubagentResult` after full completion -- there is no streaming callback interface. Adding streaming to `run_subagent()` is a larger scope change that affects the orchestration layer. The heartbeat approach provides immediate value (prevents A2A client timeouts, gives observability) with minimal code change. True streaming can be added later when `run_subagent()` gains a callback interface.

### Why `McpCapabilities` is Removed

The scaffold used `McpCapabilities(http=True, sse=True)` in `initialize()` but the import was missing. Investigation of the Claude bridge reveals it does not advertise `McpCapabilities` in its initialization response either. MCP server configuration is passed dynamically via `new_session(mcp_servers=...)`, not declared as a static capability. The scaffold's use of `McpCapabilities` was incorrect -- it is not part of the standard `AgentCapabilities` initialization pattern used by the ACP SDK.

### Why Session Resume Uses State Reconstruction, Not `--resume`

Gemini CLI's `--resume` flag operates on file-based session history at `~/.gemini/tmp/<project_hash>/chats/`. This is a CLI convenience feature, not an ACP protocol mechanism. The ACP session resume model requires the bridge to reconstruct the child connection with stored configuration and re-establish the ACP handshake. Per `[[2026-02-20-a2a-team-gemini-research]]`, "ACP protocol does not persist conversation history across client instances -- each new ACP connection creates a fresh SDK/CLI client. Session 'resume' restores configuration, not conversation context." The bridge's `load_session` reconstructs the child process with the same `model`, `mode`, `cwd`, and `mcp_servers`, which is the correct ACP semantic.

## Consequences

### Positive

- **Feature parity**: Gemini ACP bridge implements all 15 Agent protocol methods, matching Claude.
- **Team readiness**: Gemini executor gains retry, cancel, and concurrency protection needed for `TeamCoordinator` multi-agent dispatch.
- **Observability**: Heartbeat progress events prevent A2A client timeouts for long-running Gemini tasks.
- **Testability**: Full DI on both components enables thorough testing without mocking.
- **Security**: SDK env trimming replaces `os.environ.copy()`, preventing env variable leakage to child processes.
- **Production integration**: Bridge is wired into `GeminiProvider.prepare_process()` and exported from `acp/__init__.py`. No more dead code.
- **Consistency**: Both providers follow the same bridge pattern, making maintenance and debugging uniform.

### Negative

- **Full rewrite risk**: Discarding the scaffold means all bridge code is new and unproven. Mitigated by following the Claude bridge template line-by-line and comprehensive test coverage.
- **Session resume is configuration-only**: Conversation context is not preserved across child process restarts. This is an ACP protocol limitation, not a bridge limitation. Documenting this prevents false expectations.
- **Heartbeat is not true streaming**: A2A clients see periodic "working" updates, not incremental content. This is an interim measure until `run_subagent()` gains a streaming interface.
- **`run_subagent()` upstream dependency**: Full session resume and true streaming in the executor require changes to `orchestration/subagent.py`. These are tracked as separate work items.
- **Maintenance overhead**: Two bridge implementations (`claude_bridge.py` and `gemini_bridge.py`) must be kept in sync as the ACP protocol evolves. Mitigated by the shared patterns and structural similarity.
- **Provider change**: `GeminiProvider.prepare_process()` now spawns `python -m vaultspec.protocol.acp.gemini_bridge` instead of the raw `gemini` binary. This adds one layer of indirection. The performance impact is negligible (Python process startup is ~50ms).
