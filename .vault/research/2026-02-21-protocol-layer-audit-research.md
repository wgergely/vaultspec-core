---
tags:
  - "#research"
  - "#protocol-audit"
date: "2026-02-21"
related:
  - "[[2026-02-20-a2a-team-protocol-research]]"
  - "[[2026-02-07-protocol-architecture-research]]"
  - "[[2026-02-07-protocol-review-research]]"
---
# Protocol Layer Audit: Four-Path Agent Communication Stack

Comprehensive audit of vaultspec's four independent protocol paths for
communicating with LLM agents. Covers architecture, error propagation,
process boundaries, and cross-cutting fragility concerns.

## Architecture Overview

Vaultspec uses two protocol stacks (ACP and A2A) crossed with two providers
(Claude and Gemini), yielding four distinct code paths:

| Path | Entry Point | Transport | Process Boundaries |
|------|------------|-----------|-------------------|
| Claude ACP | `run_subagent()` → `ClaudeACPBridge` | ACP over stdin/stdout | 4 |
| Gemini ACP | `run_subagent()` → `gemini` CLI | ACP over stdin/stdout | 2 |
| Claude A2A | `ClaudeA2AExecutor.execute()` | A2A over HTTP → SDK | 3 |
| Gemini A2A | `GeminiA2AExecutor.execute()` → `run_subagent()` | A2A over HTTP → ACP | 3 |

## Findings

### 1. Claude ACP Path

**Call chain:**

```
run_subagent()                              orchestration/subagent.py:199
  ├── ClaudeProvider.prepare_process()      providers/claude.py:187
  │     returns: executable = sys.executable
  │              args = ["-m", "protocol.acp.claude_bridge", "--model", ...]
  └── acp.spawn_agent_process()             acp library
        ├── SubagentClient (Client side)    acp/client.py:78
        └── ClaudeACPBridge (Agent side)    acp/claude_bridge.py:161
              ├── ClaudeSDKClient           claude-agent-sdk
              │     └── SubprocessCLITransport
              │           └── claude CLI    Node.js binary
              │                 └── Anthropic HTTP API
```

**Process boundaries:** Python orchestrator → Python bridge process (ACP
JSON-RPC over stdin/stdout) → Python SDK → Node.js CLI (subprocess) →
Anthropic HTTP API. Four process boundaries.

**Error handling (critical weakness at `claude_bridge.py:438-452`):**

```python
try:
    async for message in self._sdk_client.receive_messages():
        ...
except Exception:
    logger.exception("Error streaming SDK messages")
    stop_reason = "refusal"  # ALL errors become "refusal"
```

This bare `except Exception` is the primary vulnerability. When the Claude
CLI emits a `rate_limit_event` (or any event type the Python SDK doesn't
recognize), `receive_messages()` raises `MessageParseError`. The bridge
catches it as a generic `Exception` and maps it to `stop_reason = "refusal"`,
which is semantically wrong — the agent wasn't refusing, it was rate-limited.

The caller (`run_subagent`) then receives a `PromptResponse(stop_reason="refusal")`
and has no way to distinguish rate limits from actual refusals, parse errors,
network failures, or SDK bugs. All error information is lost.

**Additional `run_subagent` wrapping at `subagent.py:384`:**

```python
except Exception as exc:
    logger.exception("Subagent execution failed")
    raise SubagentError(f"Subagent execution failed: {exc}") from exc
```

Second layer of generic exception flattening. Even if the bridge had
propagated a specific error type, `run_subagent` wraps everything into
`SubagentError`.

**Streaming fidelity:** The bridge does extensive streaming translation
(`_emit_stream_event`, `_emit_assistant`, `_emit_user_message`,
`_emit_system_message`, `_emit_result`) covering:
- `content_block_start` → tool use tracking (`_block_index_to_tool`)
- `content_block_delta` → text_delta, thinking_delta, input_json_delta
- `AssistantMessage` → `AgentMessageChunk`, `AgentThoughtChunk`, `ToolCallStart`
- `UserMessage` → `ToolCallProgress` (tool result correlation)
- `SystemMessage` → `SessionInfoUpdate`
- `ResultMessage` → `SessionInfoUpdate`

Unknown events are logged at debug level but not propagated. This is correct
behavior for unknown *streaming* deltas but masks genuinely important events.

**Windows concerns:** `_kill_process_tree()` in `subagent.py:49-68` uses
`taskkill /F /T` because `proc.terminate()` only kills the bridge Python
process — the Node.js children spawned by `claude-agent-sdk` become orphaned
on Windows. Unix relies on PID 1 reparenting for cleanup.

### 2. Gemini ACP Path

**Call chain:**

```
run_subagent()                              orchestration/subagent.py:199
  ├── GeminiProvider.prepare_process()      providers/gemini.py:235
  │     returns: executable = gemini (or cmd.exe /c gemini.cmd on Windows)
  │              args = ["--experimental-acp", "--model", ...]
  └── acp.spawn_agent_process()             acp library
        ├── SubagentClient (Client side)    acp/client.py:78
        └── gemini CLI (native ACP)         Gemini CLI binary
              └── Google Gemini API
```

**Process boundaries:** Python orchestrator → Gemini CLI process (native ACP
over stdin/stdout) → Google Gemini API. Two process boundaries.

**Key architectural advantage:** No bridge process. The Gemini CLI speaks ACP
natively, eliminating an entire Python intermediary and the `claude-agent-sdk`
parsing layer. This means:
- No `MessageParseError` vulnerability
- No `SubprocessCLITransport` indirection
- Rate limits handled by the CLI itself
- Errors propagated via ACP protocol directly

**Error handling:** Uses the same `run_subagent()` → `SubagentError` wrapping
as Claude ACP (`subagent.py:384`), but the errors that reach it are
structurally cleaner because they come through ACP JSON-RPC rather than
through SDK message parsing.

**Auth handling (`gemini.py:54-157`):** Proactive OAuth token refresh with
`_is_gemini_token_expired()` and `_refresh_gemini_oauth_token()`. Atomic
credential write-back. Falls back to `GEMINI_API_KEY` env var. More robust
than Claude's auth handling because refresh is attempted before process spawn.

**Version gating (`gemini.py:191-233`):** `check_version()` enforces minimum
CLI versions — v0.9.0 on Windows (ACP hang fix), v0.27.0 recommended (stable
agent skills). Cached version check avoids repeated subprocess calls.

**Windows .cmd wrapping:** `resolve_executable()` in `providers/base.py:145`
detects `.cmd`/`.bat` wrappers and prepends `cmd.exe /c` — npm-installed CLIs
on Windows can't be directly exec'd by asyncio.

### 3. Claude A2A Path

**Call chain:**

```
TeamCoordinator (httpx POST)                orchestration/team.py:122
  └── A2A HTTP endpoint (Starlette)         a2a/server.py:35
        └── ClaudeA2AExecutor.execute()     a2a/executors/claude_executor.py:95
              ├── ClaudeSDKClient            claude-agent-sdk
              │     └── SubprocessCLITransport
              │           └── claude CLI    Node.js binary
              │                 └── Anthropic HTTP API
```

**Process boundaries:** HTTP client → Starlette server (in-process) →
Node.js CLI (subprocess via SDK) → Anthropic HTTP API. Three process
boundaries (one fewer than ACP because no bridge process).

**Error handling (best of the four paths, `claude_executor.py:129-141`):**

```python
try:
    msg = await _stream.__anext__()
except StopAsyncIteration:
    break
except MessageParseError as exc:
    exc_str = str(exc)
    if "rate_limit_event" in exc_str:
        raise RuntimeError(
            "Claude CLI rate limited — retry after the rate-limit "
            "window expires."
        ) from exc
    logger.debug("Skipping unparseable SDK message: %s", exc)
    continue
```

This is the only path that:
- Catches `MessageParseError` specifically (imported from `claude_agent_sdk._errors`)
- Detects rate limits by string-matching the exception message
- Raises a descriptive `RuntimeError` for rate limits (propagates to `updater.failed()`)
- Gracefully skips other unparseable messages (unknown event types)

**Outer error handling (`claude_executor.py:182-188`):**

```python
except Exception as e:
    logger.exception("ClaudeA2AExecutor error for task %s", task_id)
    await updater.failed(
        message=updater.new_agent_message(
            parts=[Part(root=TextPart(text=str(e)))]
        )
    )
```

Maps all other exceptions to A2A `failed` state with the error message
preserved as text. This is correct A2A lifecycle behavior.

**Unexpected EOF handling (`claude_executor.py:168-181`):** If the stream
ends without a `ResultMessage`, the executor explicitly calls
`updater.failed()` with whatever text was collected. This handles cases
where the CLI process crashes mid-stream.

**CLAUDECODE env var (`claude_executor.py:121`):** Strips `CLAUDECODE` from
the environment before spawning the SDK — prevents the child `claude` process
from refusing to start inside an existing Claude Code session. Restored in
`finally` block.

**Streaming fidelity:** Much simpler than the ACP bridge — only collects
`TextBlock` content from `AssistantMessage` objects. No thinking blocks, no
tool call tracking, no streaming deltas. The final text is emitted as a
single artifact. Appropriate for the A2A model where the result is what
matters, not the intermediate process.

**Cancellation (`claude_executor.py:196-211`):** Tracks active clients in
`_active_clients` dict with an `asyncio.Lock`. Cancel interrupts the SDK
client and disconnects it.

### 4. Gemini A2A Path

**Call chain:**

```
TeamCoordinator (httpx POST)                orchestration/team.py:122
  └── A2A HTTP endpoint (Starlette)         a2a/server.py:35
        └── GeminiA2AExecutor.execute()     a2a/executors/gemini_executor.py:65
              └── run_subagent()            orchestration/subagent.py:199
                    └── (full Gemini ACP stack above)
```

**Process boundaries:** HTTP client → Starlette server (in-process) →
Python orchestrator → Gemini CLI (ACP over stdin/stdout) → Google Gemini API.
Three process boundaries.

**Double wrapping:** This is A2A-over-ACP. The executor calls `run_subagent()`
which goes through the entire ACP lifecycle:
1. A2A `TaskUpdater` state management (`start_work`, `add_artifact`, `complete`/`failed`)
2. `run_subagent()` lifecycle (provider selection, agent loading, process spec, ACP handshake)
3. Gemini CLI native ACP

Errors must propagate through both protocol layers. A failure in the Gemini CLI:
- Propagates via ACP protocol to `SubagentClient`
- Gets wrapped in `SubagentError` by `run_subagent()`
- Gets caught by `GeminiA2AExecutor`'s `except Exception`
- Gets mapped to A2A `failed` state via `updater.failed()`

**Error handling (`gemini_executor.py:100-106`):**

```python
except Exception as e:
    logger.error("GeminiA2AExecutor error for task %s", task_id, exc_info=True)
    await updater.failed(
        message=updater.new_agent_message(
            parts=[Part(root=TextPart(text=str(e)))]
        )
    )
```

Bare `except Exception` — adequate since the underlying `run_subagent()` has
already done its own error handling and wrapping. The original error is
preserved as `SubagentError(original_exception)`.

**Cancellation:** `cancel()` only calls `updater.cancel()` — does NOT
interrupt the underlying `run_subagent()` call. If the ACP subprocess is
running, it continues until natural completion. This is a gap: cancellation
is acknowledged at the A2A level but not propagated to the ACP level.

## Cross-Cutting Concerns

### Error Handling Consistency

| Path | parse_message crash | Rate limit | Generic error | Error preserved? |
|------|-------------------|------------|---------------|-----------------|
| Claude ACP | → "refusal" | → "refusal" | → "refusal" | No |
| Gemini ACP | N/A | CLI handles | → SubagentError | Partially |
| Claude A2A | → skip (continue) | → RuntimeError | → updater.failed(str(e)) | Yes |
| Gemini A2A | N/A | CLI handles | → updater.failed(str(e)) | Yes |

The Claude ACP path is the weakest. All three error categories collapse
into `stop_reason = "refusal"` with no recovery path. The Claude A2A path
is the strongest with specific `MessageParseError` handling.

### The `parse_message` Vulnerability

Affects only Claude paths. The Python SDK (`claude-agent-sdk`) spawns the
Claude Code CLI as a Node.js subprocess and parses its stdout line by line.
The CLI is a full IDE-grade application that may emit event types the SDK
doesn't know about:

- `rate_limit_event` — known to cause `MessageParseError`
- Future event types added by Claude Code updates
- Error/diagnostic events emitted by the CLI

The SDK's `_errors.MessageParseError` is the symptom. The root cause is that
the SDK hardcodes expected event types and raises on anything else, rather
than treating unknown events as ignorable.

**ACP path impact:** Fatal — terminates the entire streaming loop, response
is marked "refusal".

**A2A path impact:** Recoverable — rate limits are detected and raised
specifically; other unknown events are logged and skipped.

### Rate Limit Handling

| Path | Detection | Behavior | Recovery |
|------|-----------|----------|----------|
| Claude ACP | None | Becomes "refusal" | None — caller cannot retry |
| Gemini ACP | CLI internal | CLI retries or fails | ACP error if CLI gives up |
| Claude A2A | String match on MessageParseError | RuntimeError raised | Caller sees "rate limited" in error |
| Gemini A2A | CLI internal (via ACP) | CLI retries or fails | SubagentError wrapping |

### Process Boundary Failure Modes

**Claude ACP (4 boundaries):**
1. Orchestrator → Bridge: bridge process crash → `SubagentError`
2. Bridge → SDK: SDK initialization failure → bridge catches, returns "refusal"
3. SDK → CLI: Node.js process crash → SDK raises → bridge catches
4. CLI → API: HTTP errors → CLI event → SDK parse → bridge

Each boundary is a potential failure point. The bridge's bare `except Exception`
collapses all of them into one undifferentiated signal.

**Gemini ACP (2 boundaries):**
1. Orchestrator → CLI: CLI process crash → ACP protocol error
2. CLI → API: HTTP errors → CLI handles or propagates via ACP

Simpler stack means fewer failure modes and cleaner error propagation.

**Claude A2A (3 boundaries):**
1. HTTP → Executor: Starlette handles HTTP errors
2. Executor → CLI: Same SDK→CLI stack as ACP but with better exception handling
3. CLI → API: Same as above

One fewer boundary than Claude ACP (no bridge process). The executor IS the
bridge, running in-process.

**Gemini A2A (3 boundaries):**
1. HTTP → Executor: Starlette handles HTTP errors
2. Executor → CLI: Via `run_subagent()` → ACP
3. CLI → API: Gemini CLI handles

Double-wrapped but the inner ACP layer is clean (native Gemini ACP).

### Streaming Event Translation Fidelity

| Path | Text | Thinking | Tool calls | Tool results | Partial streaming |
|------|------|----------|------------|-------------|-------------------|
| Claude ACP | Full | Full | Full | Full | Full (deltas) |
| Gemini ACP | Full (native) | N/A | Full (native) | Full (native) | Full (native) |
| Claude A2A | Text only | Dropped | Dropped | Dropped | None (batch) |
| Gemini A2A | Via ACP | N/A | Via ACP | Via ACP | Via ACP |

Claude A2A is the most lossy — it only collects `TextBlock` content and
discards thinking, tool use, and streaming events. This is by design (A2A
consumers only need the final result) but means debugging and observability
are limited compared to the ACP path.

### Authentication Handling

| Path | Mechanism | Proactive refresh | Fallback |
|------|-----------|-------------------|----------|
| Claude ACP/A2A | OAuth token from `~/.claude/.credentials.json` | Yes (5-min buffer) | `ANTHROPIC_API_KEY` env var |
| Gemini ACP/A2A | OAuth from `~/.gemini/oauth_creds.json` | Yes (5-min buffer) | `GEMINI_API_KEY` env var |

Both providers have proactive token refresh with atomic credential write-back.
Claude's refresh is in `ClaudeProvider` (`_load_claude_oauth_token`). Gemini's
is in `GeminiProvider` (`_refresh_gemini_oauth_token`). Both handle missing
credentials gracefully with warnings.

### Sandbox Consistency

Both stacks share `protocol/sandbox.py` as the single source of truth for
sandboxing callbacks. The `_make_sandbox_callback()` function is used by:
- Claude ACP bridge (`claude_bridge.py` via direct import)
- Claude A2A executor (`claude_executor.py` via `executors/base.py` re-export)
- A2A base (`executors/base.py` re-exports for both executors)

ACP client (`client.py`) has its own file I/O sandboxing for `read_text_file`
and `write_text_file` using path resolution and `.vault/` prefix checking.

Gemini ACP uses `--sandbox` CLI flag instead of a callback — the sandboxing
is done by the CLI, not by vaultspec code.

## Risk Assessment

**High risk:**
- Claude ACP `except Exception` → "refusal" mapping. Rate limits, transient
  errors, and SDK bugs are all indistinguishable from actual refusals. This
  will mislead callers and prevent any retry logic.

**Medium risk:**
- Gemini A2A cancellation gap: `cancel()` doesn't propagate to the underlying
  `run_subagent()` call. Long-running Gemini tasks may continue consuming
  resources after A2A cancellation.
- Process tree cleanup on Windows: `_kill_process_tree()` depends on
  `taskkill` which may fail for elevated processes.

**Low risk:**
- Claude A2A string-matching `"rate_limit_event"` in exception messages is
  fragile — SDK internal error messages may change. But it's currently the
  only working rate limit detection.
- `claude-agent-sdk` imports from `_errors` (private module) — API stability
  not guaranteed.

## Summary

The four protocol paths have fundamentally different error handling quality.
Claude A2A is the most robust (specific exception handling, rate limit
detection, proper A2A lifecycle mapping). Claude ACP is the most fragile
(all errors collapse into "refusal"). Gemini paths benefit from native ACP
support, eliminating the entire SDK message parsing layer.

The core architectural tension: the Claude SDK doesn't talk to the Anthropic
API directly — it spawns a full IDE-grade Node.js CLI as a subprocess and
parses its stdout. Every rate limit, every error, every streaming event goes
through this Node.js intermediary that may emit message types the Python SDK
doesn't know about. The Gemini stack avoids this entirely by having the CLI
speak ACP natively.
