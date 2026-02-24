---
tags:
  - "#research"
  - "#cli"
  - "#protocol"
date: "2026-02-24"
related:
  - "[[2026-02-24-subagent-protocol-adr]]"
  - "[[2026-02-24-unified-a2a-rewrite-plan]]"
  - "[[2026-02-20-a2a-team-gemini-research]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# CLI Protocols Research: Gemini CLI & Claude Agent SDK

Authoritative reference for how the Gemini CLI and Claude Agent SDK are invoked,
what flags and modes they support, and how the unified A2A rewrite should wrap
them. This research directly backs the phased rewrite plan.

## 1. Gemini CLI

### 1.1 Invocation Model

The Gemini CLI (`gemini`) is a Node.js binary installed via npm. It provides an
interactive terminal agent and an experimental ACP mode for programmatic control.

**Current vaultspec invocation chain:**

```text
GeminiProvider.prepare_process()
  → ProcessSpec(executable=sys.executable,
                args=["-m", "vaultspec.protocol.acp.gemini_bridge", "--model", model])
    → gemini_bridge.py spawns: gemini --experimental-acp --model <model> [flags...]
      → ACP JSON-RPC over stdio
```

The bridge (`protocol/acp/gemini_bridge.py`, ~1382 LOC) wraps the CLI process
and maps ACP messages to/from the Gemini CLI's stdin/stdout.

### 1.2 Complete Flag Reference

| Group | Key Flags |
| :--- | :--- |
| General | `--debug`, `--version`, `--help` |
| Model | `--model`, `--prompt`, `--prompt-interactive` |
| Safety | `--sandbox`, `--approval-mode`, `--yolo` |
| ACP | `--experimental-acp`, `--allowed-mcp-server-names`, `--allowed-tools` |
| Extensions | `--extensions`, `--list-extensions` |
| Session | `--resume`, `--list-sessions`, `--delete-session` |
| Input | `--include-directories`, `--screen-reader` |
| Output | `--output-format`, `--raw-output`, `--accept-raw-output-risk` |

**Model aliases:**

| Shortcut | Maps to |
| :--- | :--- |
| `auto`, `pro` | `gemini-2.5-pro` or `gemini-3-pro-preview` |
| `flash` | `gemini-2.5-flash` |
| `flash-lite` | `gemini-2.5-flash-lite` |

### 1.3 Flags Used by Current Bridge

From `gemini_bridge.py` lines 598–610:

```python
args = ["--experimental-acp", "--model", model]
if mode == "read-only":
    args.append("--sandbox")
if resume_native_id:
    args.extend(["--resume", resume_native_id])
for tool in self._allowed_tools:
    args.extend(["--allowed-tools", tool])
if self._approval_mode:
    args.extend(["--approval-mode", self._approval_mode])
if self._output_format:
    args.extend(["--output-format", self._output_format])
for d in self._include_dirs:
    args.extend(["--include-directories", d])
```

Environment variables forwarded:

- `GEMINI_*` (all Gemini-specific vars)
- `GOOGLE_API_KEY`
- `GEMINI_SYSTEM_MD` (path to system prompt temp file)

### 1.4 A2A Server Capability

**No native A2A server mode exists.** The Gemini CLI cannot run as a persistent
HTTP server. [RFC #7822](https://github.com/google-gemini/gemini-cli/discussions/7822)
proposes this capability but it remains unimplemented.

**Implication for the rewrite:** The A2A executor must continue to wrap the
Gemini CLI as a subprocess. The key change is eliminating the ACP bridge layer
between the executor and the CLI. Two options:

1. **Keep `--experimental-acp`**: The executor spawns `gemini --experimental-acp`
   and communicates via ACP over stdio, but the *outer* protocol (between
   orchestrator and executor) is A2A over HTTP. This keeps the reliable ACP
   handshake for subprocess communication while exposing A2A to callers.

2. **Use `--prompt` mode**: The executor spawns `gemini -p "<prompt>"` for
   single-shot tasks, reading the result from stdout. Simpler but loses session
   resume and streaming capabilities.

**Recommendation:** Option 1 — keep `--experimental-acp` for Gemini CLI
communication *within* the executor, but expose A2A externally. This preserves
session resume, streaming, and tool interaction. The ACP usage is internal to
the executor, not exposed to callers.

### 1.5 Non-Interactive (`--prompt`) Mode

The `--prompt` (`-p`) flag allows non-interactive single-shot usage:

```bash
gemini -p "Explain this codebase" --model flash --output-format json
```

This exits after one response. For the A2A rewrite:

- Could be used for simple one-shot tasks (no session, no streaming)
- Does NOT support multi-turn conversation
- Does NOT support session resume
- Does NOT support real-time streaming progress

---

## 2. Claude Agent SDK

### 2.1 Invocation Model

The Claude Agent SDK (`claude-agent-sdk` on PyPI, v0.1.40) provides a Python
API that internally manages a Claude Code subprocess. Unlike Gemini, there is
**no need to invoke a CLI binary directly** — the SDK handles it.

**Current vaultspec invocation chain:**

```text
ClaudeA2AExecutor.__init__()
  → ClaudeAgentOptions(model=..., cwd=..., system_prompt=..., ...)
  → ClaudeSDKClient(options)
  → client.connect()  # spawns claude subprocess internally
  → client.query(prompt)
  → async for msg in client.receive_response(): ...
```

**Note:** The SDK bundles the Claude CLI binary — no separate installation
required. A custom path can be specified via `ClaudeAgentOptions(cli_path=...)`.

### 2.2 Key API Surface

**`ClaudeAgentOptions`** — configuration for the SDK client:

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `model` | `str` | Claude model identifier |
| `cwd` | `str` | Working directory for the agent |
| `system_prompt` | `str` | System prompt text |
| `permission_mode` | `str` | `"bypassPermissions"` for programmatic use |
| `mcp_servers` | `dict` | MCP server configurations |
| `can_use_tool` | `Callable` | Tool permission callback |
| `env` | `dict` | Environment variables for the subprocess |
| `cli_path` | `str` | Custom path to `claude` binary |
| `resume` | `str` | Session ID for conversation resume |
| `max_turns` | `int` | Maximum conversation turns |

**`ClaudeSDKClient`** — bidirectional, interactive client:

- `connect()` — start the Claude subprocess
- `query(prompt)` — send a prompt
- `receive_response()` — async iterator yielding `AssistantMessage` / `ResultMessage`
- `interrupt()` — interrupt current response
- `disconnect()` — terminate the subprocess

**Message types:**

- `AssistantMessage` — streaming content (has `.content` list of `TextBlock`)
- `ResultMessage` — terminal message (has `.result`, `.is_error`, `.session_id`)
- `TextBlock` — text content block within a message

**Error types:**

- `CLINotFoundError` — Claude Code not installed
- `CLIConnectionError` — connection issues
- `ProcessError` — process failed (has `.exit_code`)
- `CLIJSONDecodeError` — JSON parsing issues
- `MessageParseError` — unparseable SDK message

### 2.3 Current A2A Executor Implementation

The `ClaudeA2AExecutor` (`protocol/a2a/executors/claude_executor.py`, 554 LOC)
already uses the SDK directly — **no ACP bridge involved**:

```python
# Simplified flow
options = ClaudeAgentOptions(model=..., cwd=..., system_prompt=..., ...)
sdk_client = ClaudeSDKClient(options)
await sdk_client.connect()
await sdk_client.query(prompt)
async for msg in sdk_client.receive_response():
    # Stream artifacts back via A2A TaskUpdater
```

**Key features already implemented:**

- Session resume via `session_id` persistence
- Rate-limit retry with exponential back-off
- Cancel support via `interrupt()`
- Persistent client reuse across tasks on the same context
- Throttled incremental artifact streaming
- Proper cleanup on error/cancel/success

### 2.4 Implication for the Rewrite

**The Claude executor needs NO rewiring.** It already talks directly to the
Claude SDK without going through the ACP bridge layer. The `ClaudeProvider`
(`protocol/providers/claude.py`) currently builds a `ProcessSpec` pointing to
`vaultspec.protocol.acp.claude_bridge`, but this is only used by the ACP-based
`run_subagent()` flow. Once that flow is replaced by A2A, the `ClaudeProvider`
will generate config consumed by `ClaudeA2AExecutor` instead.

---

## 3. Comparison Table

| Aspect | Gemini CLI | Claude Agent SDK |
| :--- | :--- | :--- |
| **Type** | Node.js CLI binary | Python SDK (wraps CLI internally) |
| **Invocation** | `gemini [flags]` subprocess | `ClaudeSDKClient(options).connect()` |
| **ACP support** | `--experimental-acp` flag | Not applicable (SDK protocol) |
| **A2A server mode** | Not available (RFC only) | Not applicable |
| **Streaming** | Via ACP or text stream | Via `receive_response()` async iterator |
| **Session resume** | `--resume <id>` flag | `resume=<session_id>` option |
| **System prompt** | `GEMINI_SYSTEM_MD` env var | `system_prompt` parameter |
| **Sandbox** | `--sandbox` flag | `can_use_tool` callback |
| **Current A2A ready?** | No — executor delegates to ACP | Yes — executor uses SDK directly |
| **Rewrite effort** | Medium — must inline CLI | Minimal — already A2A-ready |

---

## 4. Impact on Unified A2A Rewrite Plan

### GeminiA2AExecutor (needs rewrite)

Current: delegates to `run_subagent()` → ACP bridge → Gemini CLI.
Target: directly spawns `gemini --experimental-acp` and manages the ACP stdio
communication internally, dropping the bridge abstraction.

**Key change:** The executor becomes the ACP client for the Gemini CLI subprocess,
replacing the bridge. The ACP protocol is used *internally* between the executor
and the CLI, while A2A is the *external* protocol for callers.

### ClaudeA2AExecutor (already done)

Current and target are the same: uses `claude-agent-sdk` directly.
Only change needed: update `ClaudeProvider.prepare_process()` to produce config
for the A2A server entry point instead of the ACP bridge `ProcessSpec`.

### ServerProcessManager (shared — subagents AND teams)

Must handle both patterns uniformly — **one component, zero duplication:**

| Responsibility | Logic Location | Note |
| :--- | :--- | :--- |
| Spawning | `ServerProcessManager` | `asyncio.create_subprocess_exec` |
| Port discovery | `ServerProcessManager` | Stdio monitoring for `PORT=...` |
| Readiness | `ServerProcessManager` | HTTP poll on `/.well-known/agent-card.json` |
| Cleanup | `ServerProcessManager` | `kill_process_tree` + SIGTERM/SIGKILL |
| Orphan prevention | `ServerProcessManager` | Parent-PID watchdog thread |

Server patterns per provider:

- **Claude:** Spawn A2A HTTP server with `ClaudeA2AExecutor` (process = Python uvicorn)
- **Gemini:** Spawn A2A HTTP server with `GeminiA2AExecutor` (process = Python uvicorn,
  which internally spawns Gemini CLI subprocess via `--experimental-acp`)

---

## Sources

- [Gemini CLI Reference](https://geminicli.com/docs/cli/cli-reference)
- [Gemini CLI A2A RFC #7822](https://github.com/google-gemini/gemini-cli/discussions/7822)
- [claude-agent-sdk PyPI](https://pypi.org/project/claude-agent-sdk/)
- [Claude Agent SDK GitHub](https://github.com/anthropics/claude-agent-sdk)
- Source: `protocol/acp/gemini_bridge.py` lines 598–610
- Source: `protocol/providers/gemini.py` (469 LOC)
- Source: `protocol/providers/claude.py` (359 LOC)
- Source: `protocol/a2a/executors/claude_executor.py` (554 LOC)
- Source: `protocol/a2a/executors/gemini_executor.py` (309 LOC)
