---
tags:
  - "#research"
  - "#uncategorized"
date: 2026-02-18
---
# ACP Protocol Compliance Brief

**Date:** 2026-02-07
**Author:** ACP Protocol Expert (acp-expert)
**Scope:** Comprehensive analysis of how our dispatch system implements (and diverges from) the ACP standard.

---

## 1. ACP Core Concepts

### 1.1 Sessions

ACP sessions are the fundamental unit of interaction. The lifecycle is:

```
initialize -> authenticate -> session/new -> session/prompt (repeatable) -> session/cancel
```

**What ACP defines:**

- Sessions are identified by a `SessionId` (opaque string, typically UUID).
- Each session is created with a working directory (`cwd`) and optional MCP server configurations.
- Sessions support modes (e.g., "code", "plan") that can be changed via `session/set_mode` or agent-initiated `session/update` with `current_mode_update`.
- Sessions can optionally be persisted and reloaded (`session/load`) if the agent advertises `loadSession: true`.

**What we implement:**

- `run_dispatch()` (`acp_dispatch.py:489-722`) creates exactly one session per dispatch invocation.
- Session creation at line 622: `await conn.new_session(cwd=str(ROOT_DIR), mcp_servers=[], **getattr(spec, "session_meta", {}))`.
- The `session_meta` is only populated by `ClaudeProvider` (line 172-174 of `claude.py`) with a `systemPrompt` key -- this is a provider-specific extension, not part of the ACP `NewSessionRequest` schema.
- Sessions are never loaded, forked, resumed, or mode-switched. Each dispatch creates a fresh session that runs one or more prompt turns, then terminates.

### 1.2 spawn_agent_process

The primary entry point for launching ACP agents. Imported from `acp` SDK:

```python
from acp import spawn_agent_process
```

**What it does:**

- Spawns the agent as a subprocess with stdio transport.
- Sets up `ClientSideConnection` with the provided `Client` implementation.
- Returns a context manager yielding `(conn, proc)` -- the ACP connection and the subprocess handle.
- The connection object implements the `Agent` trait, allowing calls to `initialize()`, `new_session()`, `prompt()`, `cancel()`.

**Our usage** (`acp_dispatch.py:605-614`):

```python
async with spawn_agent_process(
    client,
    spec.executable,
    *spec.args,
    env=spec.env,
    transport_kwargs={
        "limit": 100 * 1024 * 1024,      # 100MB buffer
        "shutdown_timeout": 5.0,
    },
) as (conn, _proc):
```

This is correct ACP usage. The `transport_kwargs` configure the underlying asyncio stream reader limits and shutdown behavior.

### 1.3 Prompts and Responses

**ACP defines prompts as:**

- An array of `ContentBlock` objects (text, images, audio, resource links, embedded resources).
- Sent via `session/prompt` with a `sessionId`.
- Response contains a `StopReason`: `end_turn`, `max_tokens`, `max_turn_requests`, `refusal`, `cancelled`.

**Our usage** (`acp_dispatch.py:746-749`):

```python
response = await conn.prompt(
    prompt=[TextContentBlock(type="text", text=current_prompt)],
    session_id=session_id,
)
```

We only send `TextContentBlock` prompts. The ACP spec supports images, audio, resource links, and embedded resources, but our dispatch system never uses these richer content types. This is compliant (text is the baseline) but underutilizes the protocol.

### 1.4 Content Blocks

ACP defines 5 content block types:

| Type | Gate | Our Support |
|---|---|---|
| `Text` | Baseline (always) | Full -- used for prompts and response capture |
| `ResourceLink` | Baseline (always) | Ignored in `session_update` handler |
| `Image` | `promptCapabilities.image` | Not used |
| `Audio` | `promptCapabilities.audio` | Not used |
| `EmbeddedResource` | `promptCapabilities.embeddedContext` | Not used |

### 1.5 Permissions

See Section 2 below for detailed analysis.

---

## 2. Permission Model

### 2.1 What ACP Defines

The permission system (`session/request_permission`) is a core ACP requirement. It enables the agent to request human approval before executing dangerous operations.

**Full ACP Permission Flow:**

1. Agent encounters an operation requiring permission.
2. Agent sends `session/request_permission` to the client with:
   - `sessionId`: The active session.
   - `toolCall`: Description of the pending operation (title, kind, status).
   - `options`: Array of permission options, each with:
     - `optionId`: Unique identifier (e.g., "allow-once").
     - `name`: Human-readable label (e.g., "Allow once").
     - `kind`: One of `allow_once`, `allow_always`, `reject_once`, `reject_always`.
3. Client (human) selects an option.
4. Client responds with `RequestPermissionResponse`:
   - `outcome.outcome`: `"selected"` (user chose) or `"cancelled"` (turn was cancelled).
   - `outcome.optionId`: The selected option's ID (only if `"selected"`).

**ACP Permission Semantics:**

- `allow_once`: Permit this specific operation only.
- `allow_always`: Permit this and all future operations of this kind.
- `reject_once`: Deny this specific operation.
- `reject_always`: Deny this and all future operations of this kind.
- `cancelled`: The prompt turn was cancelled; the agent should stop.

### 2.2 What We Implement

Our implementation (`acp_dispatch.py:218-249`) is a **YOLO auto-approve**:

```python
async def request_permission(
    self, options: Any, session_id: str, tool_call: Any, **kwargs: Any
) -> Dict[str, Any]:
    """Auto-approves tool call permissions (Emulates YOLO mode)."""
    selected_id = "allow"
    if options:
        for opt in options:
            opt_kind = getattr(opt, "kind", None)
            if opt_kind in ("allow_once", "allow_always"):
                selected_id = getattr(opt, "option_id", selected_id)
                break
        else:
            selected_id = getattr(options[0], "option_id", selected_id)

    return {"outcome": {"outcome": "selected", "optionId": selected_id}}
```

**Behavior:**

1. Iterates through provided options looking for an `allow_once` or `allow_always` kind.
2. If found, selects that option.
3. If no allow option exists, falls back to the first option (regardless of kind).
4. Never returns `"cancelled"` outcome.
5. Never returns `reject_once` or `reject_always`.
6. Logs the permission request but takes no enforcement action.

### 2.3 What's Lost

| ACP Feature | Our Implementation | Impact |
|---|---|---|
| Human approval loop | Auto-approve | No safety gate between agent actions and workspace |
| `reject_once` / `reject_always` | Never used | Cannot deny dangerous operations |
| `cancelled` outcome | Never returned | Cannot signal turn cancellation via permissions |
| `allow_always` scoped memory | Not tracked | Each permission request is independent |
| Custom option kinds | Ignored | Agent-specific permission types are not handled |

### 2.4 How to Add Real Permission Callbacks

To implement proper permission handling, three approaches are viable:

**Option A: Proxy to team lead** -- When `request_permission` fires, serialize the request into a `SendMessage` to the team lead agent, wait for a response, and relay the human's decision back. This preserves the ACP contract but adds latency and requires the team lead to implement a permission handler.

**Option B: Policy-based auto-decisions** -- Implement a policy engine that maps `tool_call.kind` and path patterns to automatic decisions:

- `read` operations: always allow.
- `edit` / `delete` on source code: reject if mode is `read-only`.
- `execute` terminal commands: allow only whitelisted commands.
- Everything else: prompt upward.

**Option C: MCP permission forwarding** -- When running under the MCP server, forward permission requests to the MCP client (Claude Code) as tool call progress updates. The MCP client can then decide and respond. This is architecturally clean but requires MCP protocol extensions that don't exist today.

### 2.5 MCP Layer Permission Enforcement

The MCP layer (`mcp_dispatch.py:82-108`) adds a separate permission mechanism **on top of** ACP auto-approve:

```python
_READONLY_PERMISSION_PROMPT = (
    "PERMISSION MODE: READ-ONLY\n"
    "You MUST only write files within the `.docs/` directory. "
    "Do not modify any source code files.\n\n"
)
```

This is **prompt-level enforcement** -- it instructs the agent via natural language, not protocol enforcement. The advisory lock system (`task_engine.py:143-276`) provides conflict detection but not prevention. A non-compliant agent can still write outside `.docs/` because the ACP `write_text_file` handler (`acp_dispatch.py:341-353`) only enforces workspace boundaries, not permission mode boundaries.

---

## 3. Interactive Mode

### 3.1 How _interactive_loop() Works

The interactive loop (`acp_dispatch.py:724-811`) implements a multi-turn conversation pattern:

```python
async def _interactive_loop(
    conn, session_id, agent_name, initial_prompt,
    debug, interactive, proc, logger,
) -> None:
```

**Flow:**

1. Send the `initial_prompt` (or `spec.initial_prompt_override`) as the first `session/prompt`.
2. Wait for the response. Log it.
3. **Decision point:**
   - If `interactive=False` (line 765): break immediately after one turn. This is the "one-shot" mode used by all automated dispatch.
   - If `interactive=True`: check if the process is still alive (line 771), check if stdin is a TTY (line 777).
4. If interactive and TTY: prompt the user for input on stderr (line 782-783).
5. Race between user input (`sys.stdin.readline` via executor) and process exit (line 790-793).
6. If user input arrives: use it as the next prompt. If empty/Enter: break.
7. If process exits first: break.

**Key implementation detail at line 738-741:**

```python
async def _get_user_input() -> str | None:
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, sys.stdin.readline)
    except EOFError:
        return None
```

This uses `run_in_executor` (thread pool) to make blocking `sys.stdin.readline` async-compatible.

### 3.2 Why interactive=False is Hardcoded in MCP

In `mcp_dispatch.py:421-427`:

```python
response_text = await run_dispatch(
    agent_name=agent,
    initial_task=task_content,
    model_override=model,
    interactive=False,     # <--- hardcoded
    debug=False,
    quiet=True,            # <--- stdout suppressed for JSON-RPC
)
```

**Why:**

1. **stdout is reserved:** MCP uses stdout for JSON-RPC messages. The ACP client's response text goes to stdout by default, which would corrupt the MCP transport. `quiet=True` fixes this, but interactive prompts write to stderr which would confuse the MCP client.
2. **No TTY available:** MCP servers run as background processes with no terminal attached. `sys.stdin.isatty()` (line 777) would return False, breaking the interactive path anyway.
3. **Asynchronous dispatch model:** The MCP server returns immediately with a `taskId` (line 393-408). The background task runs to completion without human interaction. There's no mechanism for the MCP client to inject additional prompts mid-task.
4. **`stdin.readline` blocks:** Even if interactive mode were enabled, the `run_in_executor` call would block a thread pool worker indefinitely since there's no terminal to type into.

### 3.3 What Alternatives Exist for MCP-Based Interactivity

**Alternative 1: ACP session/cancel + re-prompt** -- The MCP server could expose a `send_message` tool that cancels the current prompt turn and re-issues with the new message appended. This simulates multi-turn by creating sequential single turns.

**Alternative 2: Task engine `input_required` state** -- The task engine already defines an `INPUT_REQUIRED` state (`task_engine.py:41`) with valid transitions back to `WORKING`. An agent could signal it needs input, the task engine would surface this via `get_task_status`, and a new MCP tool (e.g., `resume_task`) could inject the response and re-prompt.

**Alternative 3: ACP proxy chain with input injection** -- An ACP proxy component could intercept the agent's `session/update` stream, detect when the agent requests input, and hold the prompt turn open while soliciting input through a side channel (e.g., another MCP tool call).

None of these are implemented today.

---

## 4. Session Lifecycle

### 4.1 Full ACP Session Lifecycle

```
Client                              Agent
  |                                   |
  |--- initialize ------------------>| Version + capability negotiation
  |<-- initialize response ----------|
  |                                   |
  |--- authenticate ---------------->| (optional, if auth required)
  |<-- authenticate response --------|
  |                                   |
  |--- session/new ----------------->| Create new session
  |<-- session response (sessionId) -|
  |                                   |
  |--- session/prompt -------------->| User message
  |<-- session/update (plan) --------| Streaming updates
  |<-- session/update (tool_call) ---|
  |<-- request_permission -----------| Agent needs approval
  |--- permission response --------->|
  |<-- session/update (text) --------|
  |<-- prompt response --------------|
  |                                   |
  |--- session/cancel -------------->| (notification, no response)
  |<-- prompt response (cancelled) --|
```

### 4.2 What We Implement

**Spawn** (`acp_dispatch.py:605`): `spawn_agent_process()` launches the subprocess and establishes the stdio transport. Uses an `async with` context manager for lifecycle management.

**Initialize** (`acp_dispatch.py:620`): `await conn.initialize(protocol_version=1)`.

> **[CORRECTED 2026-02-07]** This section is outdated. The current implementation at `acp_dispatch.py:634-647` DOES send `client_capabilities` (`fs.read_text_file`, `fs.write_text_file`, `terminal`) and `client_info` (`name='pp-dispatch'`, `version='0.5.0'`) during the ACP initialize handshake. See commit `eceb472`. The original text below described the state before that fix.

~~We don't send `client_capabilities` or `client_info`, which means:~~
~~- The agent doesn't know our filesystem and terminal capabilities.~~
~~- The agent may not attempt to use `fs/read_text_file`, `fs/write_text_file`, or `terminal/*` because it doesn't know we support them.~~
~~- This is a **compliance gap** -- ACP clients SHOULD declare their capabilities.~~

**Authenticate** (`acp_dispatch.py`): Never called. Neither Gemini nor Claude ACP adapters require authentication over stdio.

**Session/new** (`acp_dispatch.py:622`): Creates a session with `cwd` and empty `mcp_servers`. The `session_meta` from `ClaudeProvider` is passed as `**kwargs` but may not map to the standard `NewSessionRequest` fields.

**Prompt** (`acp_dispatch.py:746-749`): Sends text prompts. Handles responses.

**Cancel** (`acp_dispatch.py:754-755`): Only called on prompt failure (exception path), not on external cancellation signals. The MCP `cancel_task` (`mcp_dispatch.py:530-565`) cancels the asyncio Task but does NOT send `session/cancel` to the ACP agent -- it relies on process termination instead.

### 4.3 What the MCP Server Wraps

| ACP Step | MCP Tool | MCP Behavior |
|---|---|---|
| Spawn + Initialize + Session/new | `dispatch_agent` | All three happen inside `_run_dispatch_background()` |
| Prompt | `dispatch_agent` | Single prompt, result captured asynchronously |
| Response | `get_task_status` | Polls task engine for completion |
| Cancel | `cancel_task` | Cancels asyncio.Task, does NOT send ACP `session/cancel` |
| Session/load | (none) | Not exposed |
| Session/set_mode | (none) | Not exposed |

### 4.4 What's Lost in Translation

1. **No streaming to MCP client:** ACP `session/update` notifications (plan updates, tool calls, text chunks) are consumed by `GeminiDispatchClient.session_update()` and written to stderr/stdout. The MCP client sees none of this. It only gets the final accumulated `response_text`.

2. **No graceful cancellation:** `cancel_task` kills the asyncio.Task, which may leave the agent subprocess running until the context manager exits. ACP defines `session/cancel` as the graceful cancellation mechanism, but we never send it from the MCP path.

3. **No multi-turn:** The MCP layer wraps the entire ACP session as a single fire-and-forget operation. The rich multi-turn conversation model of ACP is reduced to one-shot task delegation.

4. **No capability advertisement:** The MCP `dispatch_agent` tool returns `{taskId, status, agent, model, mode}` -- no information about what the agent can do, what content blocks it supports, or what modes it offers.

5. **No session persistence:** Each dispatch creates and destroys a session. No session IDs are returned to the MCP client. No mechanism to resume a previous session.

---

## 5. Unutilized ACP Features

### 5.1 Session Persistence (`session/load`)

**What ACP provides:** Agents that advertise `loadSession: true` can reload a previous conversation. The agent replays history via `session/update` notifications before responding.

**Our status:** Never used. Sessions are ephemeral. The `SessionLogger` (`acp_dispatch.py:173-187`) writes JSONL logs to `.rules/logs/{sessionId}.log`, which could theoretically be used for session replay, but no load mechanism exists.

**Potential:** Session persistence would enable long-running sub-agent tasks that survive process restarts. Combined with the task engine's `INPUT_REQUIRED` state, a sub-agent could checkpoint its progress and resume later.

### 5.2 Multi-Turn Conversation

**What ACP provides:** The `session/prompt` method can be called repeatedly within a session. The agent maintains conversation context across turns.

**Our status:** `_interactive_loop()` supports multi-turn when `interactive=True`, but this is only available via CLI (`--interactive` flag). The MCP server hardcodes `interactive=False`. All automated dispatch is one-shot.

**Potential:** Multi-turn would enable iterative refinement -- the team lead could review sub-agent output and provide corrections within the same ACP session, preserving context.

### 5.3 Streaming Content Updates

**What ACP provides:** `session/update` notifications deliver real-time streaming of:

- `agent_message_chunk`: Incremental text output.
- `agent_thought_chunk`: Internal reasoning (if exposed).
- `tool_call` / `tool_call_update`: Tool execution progress.
- `plan`: Agent's work plan with entry statuses.

**Our status:** `GeminiDispatchClient.session_update()` (`acp_dispatch.py:251-298`) handles all update types, printing them to stderr/stdout. But this is a terminal-only display. The MCP server sees none of it. The only result is the accumulated `response_text` string.

**Potential:** Streaming updates could be forwarded as MCP `progress` notifications or exposed via a `get_task_stream` tool. This would give the team lead real-time visibility into sub-agent work.

### 5.4 Permission Callbacks

See Section 2 for detailed analysis. Summary: we auto-approve everything. The full callback model (allow/reject once/always, cancelled outcome) is unused.

### 5.5 Session Logging

**What ACP supports implicitly:** All protocol messages can be captured for debugging and audit.

**Our status:** `SessionLogger` (`acp_dispatch.py:173-187`) captures:

- `permission_request` events
- `session_update` events (raw model dumps)
- `read_text_file` / `write_text_file` operations
- `create_terminal` operations
- `prompt_response` events

Logs go to `.rules/logs/{sessionId}.log` as JSONL. This is our own addition, not part of the ACP spec, but it provides a useful audit trail.

**Gap:** Log files are never cleaned up. The MCP server doesn't expose log access. There's no way to correlate task engine task IDs with session log files.

### 5.6 Session Modes and Config

**What ACP provides:**

- `session/set_mode`: Client can switch agent modes (e.g., "code" to "plan").
- Agent can switch modes via `current_mode_update` in `session/update`.
- `session/set_config_option`: Client can modify agent configuration mid-session.

**Our status:** Never used. We don't query available modes from `new_session` response, and we don't set modes or config options.

### 5.7 MCP Server Provisioning

**What ACP provides:** `session/new` accepts `mcp_servers` -- a list of MCP server configurations (stdio or HTTP) that the agent should connect to for tool access.

**Our status:** We always pass `mcp_servers=[]` (`acp_dispatch.py:622`). Sub-agents get no MCP tools from the dispatcher. If they need tools, they must bring their own (e.g., Gemini CLI has built-in tools, Claude Code has its own MCP config).

**Potential:** We could pass the team lead's MCP server configurations to sub-agents, giving them access to the same tooling. This would enable shared tool access without duplicating configuration.

### 5.8 Unstable Features

ACP SDK offers several unstable features behind feature flags:

- `session/set_model`: Change the model mid-session.
- `session/list`: List available sessions.
- `session/fork`: Fork a session.
- `session/resume`: Resume a suspended session.

None are used in our implementation.

---

## 6. Provider Abstraction

### 6.1 Architecture

The provider system is a three-layer abstraction:

```
AgentProvider (base.py)        -- Abstract interface
    |
    +-- GeminiProvider (gemini.py)  -- Gemini CLI ACP adapter
    +-- ClaudeProvider (claude.py)  -- @zed-industries/claude-code-acp
```

`AgentProvider` (`base.py:25-77`) defines:

- `name`: Provider identifier string.
- `supported_models`: List of model name strings.
- `get_model_capability(model)`: Maps model name to `CapabilityLevel` (LOW/MEDIUM/HIGH).
- `get_best_model_for_capability(level)`: Reverse mapping.
- `prepare_process(...)`: Creates a `ProcessSpec` for subprocess launch.

### 6.2 GeminiProvider

**Executable:** `gemini` CLI with `--experimental-acp` flag (`gemini.py:166-167`).

**System prompt delivery:** Written to a temp file, path stored in `GEMINI_SYSTEM_MD` environment variable (`gemini.py:153-163`). The Gemini CLI reads this at startup.

**Include resolution:** `resolve_includes()` (`gemini.py:57-117`) recursively resolves `@path/to/file.md` directives. Tries base_dir first, then root_dir. Security: resolved paths must be within root_dir.

**Rules loading:** Reads `.gemini/GEMINI.md` and resolves all includes (`gemini.py:119-133`).

**Model mapping:**

| Model | Capability |
|---|---|
| `gemini-3-pro-preview` | HIGH |
| `gemini-3-flash-preview` | MEDIUM |
| `gemini-2.5-pro` | LOW |
| `gemini-2.5-flash` | LOW |

**Cleanup:** Temp file is added to `cleanup_paths` and deleted after dispatch (`acp_dispatch.py:714-721`).

### 6.3 ClaudeProvider

**Executable:** `npx -y @zed-industries/claude-code-acp` (`claude.py:148-156`). Falls back to `npx.cmd` on Windows.

**System prompt delivery:** Two channels:

1. `session_meta["systemPrompt"]` (`claude.py:172-174`) -- passed as kwargs to `conn.new_session()`. This relies on the `claude-code-acp` adapter reading `_meta` or custom session fields.
2. `initial_prompt_override` (`claude.py:170`) -- the system prompt is **prepended to the task** in the first prompt message. This is a belt-and-suspenders approach.

**Include resolution:** Identical logic to GeminiProvider (duplicated code, `claude.py:47-107`).

**Rules loading:** Reads `.claude/CLAUDE.md` instead of `.gemini/GEMINI.md` (`claude.py:109-122`).

**Model mapping:**

| Model | Capability |
|---|---|
| `claude-opus-4-6` | HIGH |
| `claude-sonnet-4-5` | MEDIUM |
| `claude-haiku-4-5` | LOW |

**Cleanup:** No temp files (empty `cleanup_paths`). The system prompt goes into the session/prompt message, not a file.

### 6.4 Provider Selection and Fallback

`get_provider_for_model()` (`acp_dispatch.py:471-486`) does simple prefix matching:

- Starts with `"gemini"` -> GeminiProvider
- Starts with `"claude"` -> ClaudeProvider
- Default/unknown -> GeminiProvider

**Fallback chain** (`acp_dispatch.py:682-712`):

1. If provider_override is set: **no fallback** -- fail immediately.
2. If primary is Gemini and fails: determine capability level of failed model, select Claude equivalent, retry.
3. If Claude fails after Gemini fallback: raise `DispatchError` (no further fallbacks).
4. Fallback is **one-directional**: Gemini -> Claude only. Claude -> Gemini is not implemented.

### 6.5 Gaps

1. **Code duplication:** `resolve_includes()` is duplicated verbatim between GeminiProvider and ClaudeProvider. Should be extracted to a shared utility.

2. **No capability advertisement:** Neither provider queries the agent's `AgentCapabilities` from the `initialize` response. We don't know if the agent supports images, embedded context, or session loading.

3. **No client capability declaration:** `conn.initialize(protocol_version=1)` sends no `client_capabilities`. The agent doesn't know we support filesystem and terminal operations.

4. **Model-provider coupling:** Model names are used as proxy for provider selection. If a model name doesn't start with "gemini" or "claude", it silently falls back to Gemini. No validation against `supported_models`.

5. **No Antigravity provider:** The `AGENT_DIRS` map includes an `"antigravity"` entry, and the CLI `--provider` flag accepts it, but no `AntigravityProvider` class exists. Selecting it would crash.

6. **Session metadata injection:** `ClaudeProvider` injects `systemPrompt` into `session_meta`, which is passed as `**kwargs` to `conn.new_session()`. This is non-standard -- `NewSessionRequest` only defines `cwd` and `mcp_servers`. The `_meta` field is the correct ACP extension point, but it's unclear whether the `claude-code-acp` adapter reads it.

---

## 7. Summary of Compliance Status

### Compliant

- Correct use of `spawn_agent_process` for subprocess lifecycle.
- Proper `initialize` -> `session/new` -> `session/prompt` sequencing.
- `TextContentBlock` usage for prompts (baseline requirement).
- `session/update` handling for all defined update types.
- File I/O with workspace boundary enforcement.
- Terminal management (create, output, wait, kill, release).
- Graceful subprocess cleanup with Windows-specific workarounds.

### Partially Compliant

- **Permission handling:** Structurally correct (returns `AllowedOutcome` schema) but semantically hollow (always approves).
- **Interactive mode:** Implemented but disabled in production path (MCP).
- **Session lifecycle:** Correct single-turn, but no multi-turn, persistence, or mode switching.

### Non-Compliant

- **Missing client capabilities:** `initialize()` sends no capabilities, violating the spirit of capability negotiation.
- **Missing ACP cancel on MCP cancel:** `cancel_task` kills the asyncio.Task but never sends `session/cancel` to the agent.
- **Non-standard session metadata:** `ClaudeProvider` passes custom fields outside the `_meta` extension point.

### Architecturally Misaligned

- **Human-agent protocol for agent-agent use:** ACP is designed for editor-to-agent communication with a human in the loop. We use it for headless agent-to-agent delegation, which is A2A's domain.
- **One-shot where multi-turn exists:** ACP's conversation model is reduced to fire-and-forget task dispatch.
- **No streaming exposure:** Rich ACP streaming updates are consumed internally, never surfaced to the MCP client.

---

## Sources

- ACP Protocol Reference: `.rules/scripts/docs/2026-02-07-acp-protocol-reference.md`
- Protocol Architecture: `.rules/scripts/docs/2026-02-07-protocol-architecture.md`
- Protocol Review: `.rules/scripts/docs/2026-02-07-protocol-review.md`
- Implementation: `.rules/scripts/acp_dispatch.py`
- MCP Wrapper: `.rules/scripts/mcp_dispatch.py`
- Task Engine: `.rules/scripts/task_engine.py`
- Providers: `.rules/scripts/agent_providers/{base,gemini,claude}.py`
