---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#adr"
  - "#mcp-testing"
date: "2026-02-22"
related:
  - "[[2026-02-22-mcp-testing-research]]"
  - "[[2026-02-22-mcp-consolidation-adr]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `mcp-testing` adr: `add in-memory client session tests` | (**status:** `accepted`)

## Problem Statement

The MCP server's 105 tests exercise tool logic and FastMCP's server-side
`call_tool()` but never test through the MCP protocol. No test verifies the
handshake, JSON-RPC serialization, resource discovery, error propagation
semantics (`isError` vs exceptions), or capabilities negotiation. A
misconfigured server would pass all current tests but fail with real MCP
clients.

## Considerations

- The MCP SDK v1.26.0 provides `create_connected_server_and_client_session`
  from `mcp.shared.memory` — an in-memory transport that runs a real server
  with lifespan and yields a real `ClientSession`. No subprocess, no network.
- Through the protocol, `ToolError` becomes `CallToolResult(isError=True)`
  with text content — not a Python exception. Tests must assert on `isError`.
- The in-memory transport is immune to Windows `ProactorEventLoop` hangs
  (pure `anyio` memory streams, no IOCP).
- `anyio` detects `pytest-asyncio`'s event loop transparently. No extra
  plugin needed.
- Aligns with the no-mock policy: real client, real server, real
  serialization. Only the transport is memory-backed (an officially supported
  SDK feature).

## Constraints

- Must not introduce `pytest-anyio` or `inline-snapshot` dependencies.
- Must use `pytest-asyncio` with `asyncio_mode = "auto"` (existing setup).
- `initialize_server()` must be called before creating the session so globals
  are set when the lifespan fires.
- `raise_exceptions=True` should be used for test debuggability.
- Two fixture variants needed: with lifespan (resource/lifecycle tests) and
  without (focused tool tests).

## Implementation

Add `src/vaultspec/mcp_server/tests/test_client_session.py` with these test
classes:

- **`TestProtocolHandshake`** — verify `initialize()` succeeds and returns
  expected capabilities (tools, resources).
- **`TestToolDiscovery`** — `list_tools()` returns all 15 tools with correct
  names, schemas, annotations, and titles.
- **`TestResourceDiscovery`** — `list_resources()` returns `agents://` URIs,
  `read_resource()` returns valid JSON metadata.
- **`TestSubagentToolsRoundTrip`** — call each of the 5 subagent tools
  through the protocol (`list_agents`, `dispatch_agent`, `get_task_status`,
  `cancel_task`, `get_locks`).
- **`TestTeamToolsRoundTrip`** — call team tools through the protocol
  (`list_teams`, `team_status`, `create_team` error paths, etc.).
- **`TestErrorPropagation`** — unknown tool, invalid arguments, missing
  required fields — verify `isError=True` in `CallToolResult`.
- **`TestConcurrentCalls`** — fire multiple tool calls concurrently on a
  single session.

Fixture pattern per [[2026-02-22-mcp-testing-research]] section 7.

## Rationale

The SDK's `create_connected_server_and_client_session` is the officially
recommended testing approach. It exercises the full protocol stack (handshake,
JSON-RPC, serialization, schema validation) with zero OS dependencies. It
costs nothing in test infrastructure and fills every gap identified in the
research. The in-memory transport avoids the Windows async hangs that plague
subprocess-based tests.

## Consequences

- New test file adds ~200-300 lines and ~20-30 test cases.
- Tests exercise the lifespan, which means `_register_agent_resources()` and
  the poller task run during tests. This is beneficial (tests a real path)
  but adds ~0.5s of overhead per session creation.
- `CallToolResult.isError` assertions are different from the `pytest.raises`
  pattern used in existing tests. Both patterns will coexist — existing tests
  remain unchanged.
- Future: when the SDK releases `mcp.Client` (on main branch, unreleased),
  migration from `create_connected_server_and_client_session` is
  straightforward but not urgent.
