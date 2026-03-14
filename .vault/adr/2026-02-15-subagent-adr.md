---
tags:
  - "#adr"
  - "#protocol"
date: "2026-02-15"
---
## ADR: Subagent Architecture Refactor — Protocol Convergence

## Status

**SUPERSEDED** — This ADR is fully superseded by
`[[2026-02-24-subagent-protocol-adr]]` (Unified A2A Protocol Stack — Full
Rewrite). Option E (Python ACP bridge) chosen here is eliminated by the full
rewrite decision. Do not implement any decisions from this document.

## Context

### The Problem

The vaultspec subagent system is built around the ACP (Agent Communication Protocol), an editor-to-agent JSON-RPC protocol over stdio. The orchestration layer (`orchestration/subagent.py`) uses `acp.spawn_agent_process` to launch agents and communicates via `initialize`, `session/new`, and `session/prompt` RPC methods. This works correctly for Gemini (which speaks ACP natively via `--experimental-acp`), but is **broken for Claude**.

**Root cause**: `ClaudeProvider.prepare_process()` returns `args=["mcp", "serve"]`, which starts Claude as an MCP server — a completely different protocol. When the ACP handshake sends `session/new` or `session/prompt`, Claude responds with "Method not found" because it is speaking MCP, not ACP.

Claude CLI has **no native ACP support**. GitHub issue [#6686](https://github.com/anthropics/claude-code/issues/6686) is an open feature request with no timeline.

### Current Architecture

```
subagent.py CLI
    └── orchestration/subagent.py::run_subagent()
            ├── provider.prepare_process() → ProcessSpec (executable, args, env)
            ├── acp.spawn_agent_process(client, executable, *args)
            ├── conn.initialize() → ACP handshake
            ├── conn.new_session() → session_id
            └── conn.prompt() → send task, receive streamed response
                    └── SubagentClient (acp/client.py) handles callbacks
```

Key components:

- **`SubagentClient`** (`protocol/acp/client.py`, 450 lines): Full ACP Client implementation with file I/O, terminal management, permission handling, session logging. Well-written and functional — the problem is not here.
- **`ClaudeProvider`** (`protocol/providers/claude.py`): Returns `args=["mcp", "serve"]` — wrong protocol.
- **`GeminiProvider`**: Returns `args=["--experimental-acp"]` — correct, works.
- **`run_subagent`** (`orchestration/subagent.py`): Protocol-agnostic orchestrator that assumes all providers speak ACP.

### Technology Landscape (February 2026)

| Technology | Protocol | Language | Claude Support | Gemini Support |
|---|---|---|---|---|
| ACP (native) | JSON-RPC stdio | Any | No | Yes (`--experimental-acp`) |
| `claude-agent-sdk` | Subprocess JSON-lines | Python | Yes (bundled CLI) | No |
| `@zed-industries/claude-code-acp` | ACP bridge | Node.js/TypeScript | Yes (wraps SDK) | N/A |
| Claude headless mode | `--output-format stream-json` | Raw subprocess | Yes | No |
| Claude Code Teams | File-based JSON | Claude CLI processes | Yes (experimental) | No |

### Additional Constraints

- `CLAUDECODE` environment variable blocks nested Claude sessions — relevant for any subprocess-based approach.
- The ACP `acp` Python package provides `spawn_agent_process`, `Client`, and all schema types — a significant existing dependency.
- `SubagentClient` implements file sandboxing (read-only mode restricts writes to `.vault/`) and terminal management — any replacement must preserve these capabilities.

## Decision Options

### Option A: Dual-Protocol — `claude-agent-sdk` for Claude, ACP for Gemini

Replace the Claude path with the official `claude-agent-sdk` Python package while keeping ACP for Gemini.

**Architecture:**

```
run_subagent()
    ├── if provider == "gemini":
    │       └── acp.spawn_agent_process() → existing ACP flow (unchanged)
    └── if provider == "claude":
            └── claude_agent_sdk.query() or ClaudeSDKClient()
                    → subprocess JSON-lines protocol
                    → custom adapter maps responses to SubagentResult
```

**Implementation sketch:**

```python
# New file: protocol/claude_sdk/adapter.py
from claude_agent_sdk import ClaudeSDKClient

class ClaudeSubagentAdapter:
    """Bridges claude-agent-sdk to vaultspec's SubagentResult contract."""

    def __init__(self, root_dir, model, mode="read-write", debug=False):
        self.client = ClaudeSDKClient()
        self.root_dir = root_dir
        self.model = model
        # ...

    async def run(self, prompt: str) -> SubagentResult:
        response = self.client.query(
            prompt=prompt,
            model=self.model,
            cwd=str(self.root_dir),
            permission_mode="bypassPermissions",  # or map from mode
        )
        return SubagentResult(
            session_id=response.session_id,
            response_text=response.text,
            written_files=[],  # SDK doesn't expose this directly
        )
```

**Pros:**

- Official Anthropic SDK — best long-term support for Claude
- Python-only (no Node.js dependency)
- `claude-agent-sdk` bundles the CLI, simplifying installation
- Multi-turn sessions supported via `ClaudeSDKClient`
- MCP tool injection supported (can expose vault tools in-process)

**Cons:**

- Two completely different code paths to maintain
- `SubagentClient`'s file sandboxing and terminal management don't apply to the SDK path — Claude handles its own tools
- Loss of unified permission model — SDK uses its own permission modes
- `written_files` tracking requires parsing tool_use events from the stream
- New dependency: `claude-agent-sdk` (~v0.1.36, relatively new)

### Option B: ACP Bridge — Unify on ACP via `@zed-industries/claude-code-acp`

Use the Node.js ACP bridge to make Claude speak ACP, keeping the entire orchestration layer unchanged.

**Architecture:**

```
run_subagent()
    └── acp.spawn_agent_process()
            ├── Gemini: gemini --experimental-acp (native)
            └── Claude: npx @zed-industries/claude-code-acp (bridge)
                    └── internally uses claude-agent-sdk
                    └── translates ACP ↔ Claude subprocess protocol
```

**Implementation:** Only `ClaudeProvider.prepare_process()` changes:

```python
def prepare_process(self, ...):
    return ProcessSpec(
        executable="npx",
        args=["@zed-industries/claude-code-acp", "--model", model],
        env=env,
        # ...
    )
```

**Pros:**

- Minimal code change — only the ProcessSpec args change
- `SubagentClient` works unchanged (file sandboxing, terminals, permissions all preserved)
- Single protocol path through orchestration
- ACP is a documented, versioned protocol spec

**Cons:**

- **Adds Node.js runtime dependency** — project is currently pure Python
- Bridge is maintained by Zed Industries, not Anthropic — may lag behind SDK changes
- Extra process layer (Node.js bridge → Claude subprocess) adds latency and failure modes
- `npx` cold-start overhead on first invocation
- Bridge version must track both ACP spec and claude-agent-sdk versions

### Option C: Drop ACP — Raw Subprocess for Both Providers

Abandon ACP entirely. Use Claude's headless mode (`--output-format stream-json`) directly and implement an equivalent for Gemini (or drop Gemini).

**Architecture:**

```
run_subagent()
    └── SubprocessAgent(executable, args)
            ├── spawn subprocess with stdin/stdout pipes
            ├── write JSON-lines input
            ├── parse JSON-lines output (streaming)
            └── map to SubagentResult
```

**Implementation sketch:**

```python
# Claude: claude -p --output-format stream-json --model <model>
# Gemini: gemini-cli --print --json (hypothetical; Gemini has no equivalent)

class SubprocessAgent:
    async def run(self, prompt: str) -> SubagentResult:
        proc = await asyncio.create_subprocess_exec(
            *self.cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE
        )
        proc.stdin.write(prompt.encode())
        proc.stdin.close()
        # Parse stream-json events...
```

**Pros:**

- No external protocol dependency (no `acp` package, no `claude-agent-sdk`)
- Full control over subprocess lifecycle
- Minimal abstraction — easy to debug

**Cons:**

- Must reimplement streaming JSON parsing, permission handling, file I/O tracking
- Loses `SubagentClient`'s 450 lines of battle-tested ACP implementation
- Gemini has no documented equivalent to Claude's `--output-format stream-json` — would need to keep ACP for Gemini anyway, defeating the purpose
- No multi-turn session support without reimplementing session management
- Most maintenance burden of all options

### Option D: SDK-Primary with ACP Fallback Interface

Use `claude-agent-sdk` as the primary engine, but wrap it behind an interface compatible with the existing `SubagentClient` contract. Keep ACP only as a thin fallback for Gemini.

**Architecture:**

```
run_subagent()
    └── AgentRunner (protocol-agnostic interface)
            ├── ACPRunner (Gemini) — wraps existing acp.spawn_agent_process flow
            └── SDKRunner (Claude) — wraps claude-agent-sdk
            Both return SubagentResult
```

**Implementation:**

```python
class AgentRunner(abc.ABC):
    @abc.abstractmethod
    async def run(self, prompt: str, interactive: bool) -> SubagentResult: ...

    @abc.abstractmethod
    async def cancel(self) -> None: ...

class ACPRunner(AgentRunner):
    """Existing ACP flow, extracted from run_subagent()."""
    # Wraps spawn_agent_process + SubagentClient

class SDKRunner(AgentRunner):
    """Claude-agent-sdk flow."""
    # Wraps ClaudeSDKClient with SubagentResult mapping
```

**Pros:**

- Clean separation of concerns — each provider gets its own runner
- `run_subagent()` becomes a thin dispatcher, easy to test
- Adding new providers (e.g., OpenAI Codex) only requires a new Runner
- Preserves ACP investment for Gemini
- SDK path gets first-class treatment for Claude

**Cons:**

- Still two code paths (though behind a clean interface)
- `SubagentClient`'s capabilities (sandboxing, terminal management) only apply to ACP path
- Slightly more abstraction than Option A

### Option E: Python ACP Bridge — Reimplement Zed Bridge in Python (RECOMMENDED)

Port the `@zed-industries/claude-code-acp` TypeScript bridge to Python. This creates a Python process that speaks ACP on stdio (to our orchestrator) and internally uses `claude-agent-sdk` to drive Claude. The result: both Gemini (native ACP) and Claude (bridged ACP) are accessed through the same protocol, and `SubagentClient` works unchanged for both.

**Architecture:**

```
run_subagent()
    └── acp.spawn_agent_process()
            ├── Gemini: gemini --experimental-acp (native ACP)
            └── Claude: python -m protocol.acp.claude_bridge (Python ACP bridge)
                    └── speaks ACP on stdio ← SubagentClient connects here
                    └── internally spawns claude-agent-sdk subprocess
                    └── translates: ACP session/prompt → SDK query()
                    └── translates: SDK stream events → ACP session/update notifications
```

**Core translation mapping** (from Zed bridge analysis):

| ACP Method (incoming) | Bridge Action | SDK Call |
|---|---|---|
| `initialize` | Return capabilities | N/A (static response) |
| `session/new` | Create SDK client, set cwd/model/permissions | `ClaudeSDKClient()` + configure |
| `session/prompt` | Forward prompt text | `client.query()` + iterate `receive_messages()` |
| `session/cancel` | Abort stream | Close SDK stream |
| `session/update` (outgoing) | Map SDK events → ACP notifications | SDK `assistant`/`tool_use`/`result` → `AgentMessageChunk`/`ToolCallStart`/etc. |
| `fs/read_text_file` | Delegate to ACP client | Client handles (SubagentClient) |
| `fs/write_text_file` | Delegate to ACP client | Client handles (SubagentClient) |
| `terminal/*` | Delegate to ACP client | Client handles (SubagentClient) |
| Permission requests | Map SDK `can_use_tool` → ACP `request_permission` | Callback bridge |

**Implementation sketch:**

```python
# New file: protocol/acp/claude_bridge.py (~1750 LOC total)
import asyncio
import json
import sys
from claude_agent_sdk import ClaudeSDKClient

class ClaudeACPBridge:
    """ACP server that wraps claude-agent-sdk.

    Reads JSON-RPC requests on stdin, translates to SDK calls,
    and writes ACP notifications/responses on stdout.
    """

    def __init__(self):
        self.sdk_client: ClaudeSDKClient | None = None
        self.sessions: dict[str, SDKSession] = {}

    async def handle_initialize(self, params: dict) -> dict:
        return {
            "protocolVersion": 1,
            "serverInfo": {"name": "claude-acp-bridge", "version": "0.1.0"},
            "capabilities": {
                "terminal": True,
                "fs": {"readTextFile": True, "writeTextFile": True},
            },
        }

    async def handle_session_new(self, params: dict) -> dict:
        session_id = str(uuid.uuid4())
        self.sdk_client = ClaudeSDKClient()
        # Configure from params: cwd, model, permissions
        # Start MCP servers and inject as tools (vault_search, vault_get, etc.)
        mcp_servers = params.get("mcpServers", [])
        mcp_tools = await self._start_mcp_servers(mcp_servers)
        self.sessions[session_id] = SDKSession(
            client=self.sdk_client, tools=mcp_tools, **params
        )
        return {"sessionId": session_id}

    async def handle_session_prompt(self, params: dict) -> dict:
        session = self.sessions[params["sessionId"]]
        prompt_text = extract_text(params["prompt"])

        # Stream SDK responses → emit ACP session/update notifications
        async for event in session.client.query_stream(prompt=prompt_text):
            acp_update = self._map_sdk_event_to_acp(event)
            self._send_notification("session/update", acp_update)

        return {"status": "completed"}

    def _map_sdk_event_to_acp(self, event: dict) -> dict:
        """Map claude-agent-sdk stream events to ACP session/update types."""
        match event["type"]:
            case "assistant":
                return {"type": "agentMessageChunk",
                        "content": {"type": "text", "text": event["content"]}}
            case "tool_use":
                return {"type": "toolCallStart",
                        "title": event["tool_name"],
                        "toolCallId": event["id"]}
            case "tool_result":
                return {"type": "toolCallProgress",
                        "toolCallId": event["tool_call_id"],
                        "status": "completed"}
            case _:
                return {"type": "agentThoughtChunk",
                        "content": {"type": "text", "text": str(event)}}

    async def run(self):
        """Main JSON-RPC loop over stdin/stdout."""
        reader = asyncio.StreamReader()
        await asyncio.get_event_loop().connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer
        )
        # ... standard JSON-RPC dispatch loop
```

**What the bridge replaces vs. preserves:**

- **Replaces**: `ClaudeProvider.prepare_process()` args — now points to the Python bridge
- **Preserves**: `SubagentClient` (all 450 lines), `run_subagent()` orchestration, `spawn_agent_process` flow, file sandboxing, terminal management, permission model, session logging

**Size estimate** (from Zed bridge analysis, updated for MCP tool injection):

- JSON-RPC stdio transport: ~200 lines
- SDK-to-ACP event mapper: ~400 lines
- Session lifecycle management: ~300 lines
- Permission bridging (`can_use_tool` → ACP `request_permission`): ~200 lines
- File I/O and terminal delegation: ~250 lines
- MCP server lifecycle and tool injection: ~250 lines
- Error handling, logging, edge cases: ~300 lines
- **Total: ~1900-2000 lines Python**

**Dependencies added**: `claude-agent-sdk` (already accepted), `watchdog` (file watching, optional), `pathspec` (gitignore matching, optional)

**Pros:**

- **Unified protocol**: Both providers speak ACP — single code path through orchestration
- **SubagentClient unchanged**: File sandboxing, terminal management, permissions, session logging all work for Claude exactly as they do for Gemini
- **Python-only**: No Node.js dependency
- **`read-only` mode works natively**: `SubagentClient.write_text_file()` enforces `.vault/`-only writes regardless of provider — no need to trust SDK permission modes
- **Proven design**: Direct port of working Zed TypeScript bridge — not speculative
- **ClaudeProvider change is minimal**: Only `prepare_process()` args change
- **Testable**: Bridge can be tested independently by sending JSON-RPC on stdio

**Cons:**

- ~1750 lines of new code to write and maintain
- Must track changes in both `claude-agent-sdk` API and ACP spec
- Extra process hop (Python bridge → Claude subprocess) adds ~50-100ms latency
- Bridge must handle SDK edge cases (connection drops, partial streams, timeouts)
- `claude-agent-sdk` is v0.1.x — bridge must absorb API changes

## Evaluation Matrix

| Criterion | Weight | A (Dual) | B (Node Bridge) | C (Raw) | D (SDK+Interface) | **E (Py Bridge)** |
|---|---|---|---|---|---|---|
| Maintenance burden | High | Medium | Low | High | Medium | **Medium** |
| Dependency count | Medium | +1 (SDK) | +1 (Node.js) | -1 (ACP) | +1 (SDK) | **+1 (SDK)** |
| Claude correctness | Critical | Yes | Yes | Yes | Yes | **Yes** |
| Gemini correctness | Critical | Yes | Yes | Partial | Yes | **Yes** |
| Feature parity | High | Low | High | Low | Medium | **High** |
| Python-only | Hard | Yes | **No** | Yes | Yes | **Yes** |
| SubagentClient reuse | High | No (Claude) | Yes | No | No (Claude) | **Yes (both)** |
| Code change size | Low | Medium | Small | Large | Medium | **Large (~2000 LOC)** |
| Future-proofing | High | Good | Risky | Poor | Good | **Good** |
| Testability | Medium | Medium | Low | Medium | High | **High** |
| Sandboxing parity | High | Partial | Full | None | Partial | **Full** |

## Recommendation

**Option E: Python ACP Bridge wrapping claude-agent-sdk.**

### Justification

Given the confirmed constraints (Python-only, Gemini must-have, claude-agent-sdk acceptable), Option E is the strongest choice:

1. **Unified protocol — the decisive advantage**: Both Claude and Gemini speak ACP. `run_subagent()`, `spawn_agent_process`, and `SubagentClient` work identically for both. No `if provider == "claude"` branches anywhere in orchestration. This is the only option (besides the eliminated Option B) that achieves true protocol convergence.

2. **SubagentClient works unchanged for both providers**: The 450-line `SubagentClient` with file sandboxing (`read-only` mode restricts writes to `.vault/`), terminal management, permission handling, and session logging serves Claude exactly as it serves Gemini. Option D would lose this for Claude.

3. **Proven design, not speculative**: The Zed TypeScript bridge is production code with a clear 1:1 mapping to Python. The translation is mechanical — no protocol design decisions required.

4. **Python-only**: Satisfies the hard constraint.

5. **Sandboxing parity**: In Options A and D, Claude's file writes are controlled by SDK permission modes — coarser than `SubagentClient.write_text_file()` which enforces `.vault/`-only writes. Option E preserves this fine-grained sandboxing because all file I/O goes through `SubagentClient`.

### Why not Option D?

Option D was the previous recommendation and remains a solid fallback. Its main weakness: two code paths means two sets of behaviors to test, two permission models, and no file-sandboxing parity for Claude. If the ~1750 LOC bridge cost is deemed too high, fall back to Option D.

### Risk mitigation

The primary risk — ~2000 lines of new bridge code (including MCP tool injection) — is mitigated by:

- Direct port from working TypeScript (not greenfield design)
- Bridge is independently testable via JSON-RPC on stdio
- `claude-agent-sdk` API surface used is small (connect, query, receive_messages)
- If bridge maintenance becomes burdensome, can fall back to Option D without touching Gemini

## Migration Path

### Phase 1: JSON-RPC Transport Layer

1. Create `protocol/acp/jsonrpc.py` — ~200 lines
2. Implement async stdin/stdout JSON-RPC reader/writer
3. Support both requests (with `id`) and notifications (without `id`)
4. Unit test with mock stdio

### Phase 2: SDK-to-ACP Event Mapper

1. Create `protocol/acp/claude_bridge.py` — core bridge module
2. Implement `_map_sdk_event_to_acp()` for all SDK event types:
   - `assistant` → `AgentMessageChunk`
   - `tool_use` → `ToolCallStart`
   - `tool_result` → `ToolCallProgress`
   - `init` → `SessionInfoUpdate`
   - `result` → final response
3. Implement `handle_initialize()`, `handle_session_new()`, `handle_session_prompt()`, `handle_session_cancel()`
4. Unit test event mapping in isolation (no subprocess needed)

### Phase 3: Permission, File I/O, and MCP Tool Injection

1. Implement `can_use_tool` callback in SDK → ACP `request_permission` round-trip
2. Wire file I/O ACP methods to delegate back through the SubagentClient (the bridge acts as ACP server; SubagentClient is ACP client — file ops flow: Claude SDK → bridge → ACP notification → SubagentClient)
3. Terminal management delegation (same pattern)
4. Implement MCP server lifecycle management:
   - Accept `mcpServers` config from `session/new` params
   - Start MCP servers as subprocesses (vault_search, vault_get, vault_list, vault_related, vault_status, vault_index)
   - Register MCP tools with `claude-agent-sdk` via its in-process tool injection API
   - Route tool call results back through ACP protocol
   - Shut down MCP servers on `session/cancel`
5. Add `claude-agent-sdk` to `pyproject.toml`

### Phase 4: Wire Up ClaudeProvider

1. Update `ClaudeProvider.prepare_process()`:

   ```python
   return ProcessSpec(
       executable=sys.executable,
       args=["-m", "protocol.acp.claude_bridge", "--model", model],
       env=env,
       # ...
   )
   ```

2. No changes to `run_subagent()`, `SubagentClient`, or `GeminiProvider`
3. **Verify**: Claude subagent works end-to-end via ACP bridge
4. **Verify**: Gemini subagent still works (should be untouched)

### Phase 5: Integration Testing and Cleanup

1. Add integration tests: spawn bridge, send ACP handshake, verify responses
2. Test `read-only` mode sandboxing works for Claude (via SubagentClient)
3. Test multi-turn interactive sessions through bridge
4. Remove dead code (`args=["mcp", "serve"]`)
5. Update documentation

## Consequences

### What Improves

- Claude subagent path actually works (currently broken)
- Both providers share identical orchestration, permission, and sandboxing code paths
- `SubagentClient` file sandboxing (`read-only` → `.vault/`-only writes) applies to Claude
- No conditional logic in `run_subagent()` — both providers are ACP
- Claude subagents gain access to vault MCP tools (vault_search, vault_get, vault_list, vault_related, vault_status, vault_index) via in-process tool injection — enabling full subagent-driven development workflows
- Adding future ACP-speaking providers requires only a new `ProcessSpec`

### What Changes

- `ClaudeProvider.prepare_process()` returns bridge command instead of `["mcp", "serve"]`
- New `protocol/acp/claude_bridge.py` module (~2000 LOC) becomes a critical path component
- Bridge manages MCP server lifecycle: starts vault MCP servers on `session/new`, injects as tools into `claude-agent-sdk`, shuts down on `session/cancel`
- `claude-agent-sdk` added as a dependency
- Claude subprocess chain: orchestrator → Python bridge → Claude CLI (one extra hop vs. native)

### What Breaks

- Nothing in the Gemini path (completely untouched)
- Nothing in the orchestration layer (`run_subagent`, `SubagentClient` — unchanged)
- Claude subagent is already broken, so there is nothing to regress
- Tests for Claude provider will need updating (they currently cannot work anyway)

### Risks

- **Bridge maintenance**: ~2000 lines (including MCP tool injection) that must track both `claude-agent-sdk` and ACP spec changes. Mitigated by the bridge's small SDK API surface and the fact that ACP spec is stable.
- **Extra process hop latency**: ~50-100ms added. Acceptable for agent tasks that take seconds to minutes.
- **`claude-agent-sdk` v0.1.x instability**: Bridge isolates the rest of the codebase from SDK API changes — only `claude_bridge.py` needs updating.
- **`CLAUDECODE` env var**: May block nested Claude sessions. Bridge must unset this before spawning Claude subprocess.
- **MCP server lifecycle**: Bridge must reliably start/stop MCP servers per session. Zombie MCP processes on crash must be handled (PID tracking + cleanup on bridge exit).

## Resolved Questions

1. **Node.js tolerance**: Python-only is a hard constraint. Eliminates Option B.
2. **Gemini priority**: Must-have. Both providers required.
3. **SDK dependency appetite**: `claude-agent-sdk` is acceptable as a production dependency.

4. **Bridge scope**: YES — the bridge will support MCP tool injection. Claude subagents must have access to vault MCP tools (vault_search, vault_get, vault_list, vault_related, vault_status, vault_index) in-process. Subagent-driven development is the core purpose of vaultspec; agents need full vault access.
5. **Fallback strategy**: Option D (SDK-primary with unified interface). It preserves the subagent architecture even if ACP bridging proves too costly. Option A (dual-protocol) adds too much complexity for the core use case.

## References

- `protocol/acp/client.py` — SubagentClient (ACP implementation)
- `protocol/providers/claude.py` — ClaudeProvider (broken: `args=["mcp", "serve"]`)
- `protocol/providers/gemini.py` — GeminiProvider (working ACP)
- `orchestration/subagent.py` — run_subagent orchestrator
- [claude-agent-sdk on PyPI](https://pypi.org/project/claude-agent-sdk/) — v0.1.36
- [@zed-industries/claude-code-acp](https://www.npmjs.com/package/@zed-industries/claude-code-acp) — Node.js ACP bridge
- [ACP Specification](https://github.com/agentclientprotocol/agent-client-protocol) — Protocol spec
- [Claude Code Teams](https://code.claude.com/docs/en/agent-teams) — File-based coordination (2026)
