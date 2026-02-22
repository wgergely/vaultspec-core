---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#research"
  - "#mcp-testing"
date: "2026-02-22"
related:
  - "[[2026-02-22-mcp-consolidation-research]]"
  - "[[2026-02-22-mcp-consolidation-adr]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `mcp-testing` research: in-memory client session tests

Research into adding proper MCP SDK in-memory client session tests for the
vaultspec MCP server (`src/vaultspec/mcp_server/`). The consolidated server
exposes 15 tools across two modules (5 subagent + 10 team coordination) and
registers dynamic `agents://` resources. Current tests (105 total) use direct
function calls and `FastMCP.call_tool()` -- neither exercises the MCP
protocol's client-server session handshake, JSON-RPC serialization, or
transport layer.


## Findings


### 1. SDK in-memory transport API (`mcp.shared.memory`)

The MCP Python SDK v1.26.0 provides two functions in `mcp.shared.memory`:

**`create_client_server_memory_streams()`** -- Lower-level primitive. Creates
a pair of bidirectional `anyio` memory object streams (buffer size 1) and
returns `(client_streams, server_streams)` where each is a tuple of
`(read_stream, write_stream)`. The caller is responsible for wiring these into
`Server.run()` and `ClientSession` manually. This is a context manager.

**`create_connected_server_and_client_session(server, ...)`** -- Higher-level
convenience. Accepts either a `Server` or `FastMCP` instance. When given a
`FastMCP`, it extracts the underlying `_mcp_server` (low-level `Server`). It
then:

- Creates in-memory streams via `create_client_server_memory_streams()`
- Starts `server.run()` as a background task in an `anyio` task group
- Creates a `ClientSession` connected to the client side of the streams
- Calls `client_session.initialize()` (performs the MCP handshake)
- Yields the initialized `ClientSession`
- On exit, cancels the server task group

Full signature:

```python
@asynccontextmanager
async def create_connected_server_and_client_session(
    server: Server[Any] | FastMCP,
    read_timeout_seconds: timedelta | None = None,
    sampling_callback: SamplingFnT | None = None,
    list_roots_callback: ListRootsFnT | None = None,
    logging_callback: LoggingFnT | None = None,
    message_handler: MessageHandlerFnT | None = None,
    client_info: types.Implementation | None = None,
    raise_exceptions: bool = False,
    elicitation_callback: ElicitationFnT | None = None,
) -> AsyncGenerator[ClientSession, None]:
```

Import path: `from mcp.shared.memory import create_connected_server_and_client_session`


### 2. ClientSession API surface

The yielded `ClientSession` provides the following methods relevant to testing
(all return typed Pydantic result models):

| Method | Returns | Purpose |
|--------|---------|---------|
| `list_tools()` | `ListToolsResult` | Enumerate registered tools with schemas |
| `call_tool(name, arguments)` | `CallToolResult` | Invoke a tool through the protocol |
| `list_resources()` | `ListResourcesResult` | Enumerate registered resources |
| `read_resource(uri)` | `ReadResourceResult` | Read a specific resource by URI |
| `list_prompts()` | `ListPromptsResult` | Enumerate registered prompts |
| `get_prompt(name, arguments)` | `GetPromptResult` | Retrieve a specific prompt |
| `list_resource_templates()` | `ListResourceTemplatesResult` | List resource templates |
| `send_ping()` | `EmptyResult` | Protocol-level ping |
| `set_logging_level(level)` | `EmptyResult` | Set server logging level |

Key detail: `call_tool()` automatically validates tool results against their
`outputSchema` (via `_validate_tool_result`). If the server returns structured
content, the client validates it against the tool's declared JSON Schema. This
provides free schema conformance testing.

`CallToolResult` has an `isError` boolean and `content` list of
`TextContent | ImageContent | EmbeddedResource` objects. Tool errors (from
`ToolError`) are represented as `isError=True` with a text content item
containing the error message -- they do NOT raise Python exceptions on the
client side. This is a critical behavioral difference from `FastMCP.call_tool()`
which raises `ToolError` directly.


### 3. Lifespan interaction

**Critical finding**: `create_connected_server_and_client_session` calls
`server.run()` which enters the server's lifespan context (line 657 of
`lowlevel/server.py`):

```python
async with AsyncExitStack() as stack:
    lifespan_context = await stack.enter_async_context(self.lifespan(self))
```

The vaultspec server defines a lifespan in `mcp_server/app.py`:

```python
@asynccontextmanager
async def _lifespan(_app: FastMCP) -> AsyncIterator[None]:
    async with subagent_lifespan():
        yield None
```

`subagent_lifespan()` calls `_register_agent_resources()` (which scans
`AGENTS_DIR` for `.md` files) and starts `_poll_agent_files()` as a background
`asyncio.Task`. The poller runs indefinitely until cancelled on exit.

**Implication for testing**: When `create_connected_server_and_client_session`
runs the server, the lifespan fires. This means:

- `initialize_server()` MUST be called before creating the session, so that
  the globals (`ROOT_DIR`, `AGENTS_DIR`, etc.) are set.
- The agent-file poller task will start and run during the test.
- On context exit, the task group cancellation will cancel the poller cleanly.

This is actually beneficial -- it exercises the real lifespan, which current
tests skip entirely. However, tests that create the session will need
`initialize_server()` in a fixture, which is already the pattern used in the
existing conftest.

**Alternative**: Create the `FastMCP` instance via `create_server()` (from
`app.py`) which wires up the lifespan. Or use a stripped-down `FastMCP`
without lifespan for focused tool tests. The choice depends on whether a given
test needs the lifespan or not.


### 4. anyio vs asyncio compatibility

**Status**: Compatible with care.

The project uses:
- `pytest-asyncio` v1.3.0 with `asyncio_mode = "auto"` in `pyproject.toml`
- Python's `asyncio` event loop for all async tests (no `anyio` backend fixture)

The MCP SDK's in-memory transport uses:
- `anyio.create_memory_object_stream` for the streams
- `anyio.create_task_group` for managing the server task

When `anyio` detects that an `asyncio` event loop is running, it uses `asyncio`
as its backend automatically. The `anyio.create_task_group()` call wraps
`asyncio.TaskGroup` under the hood. This means:

- `pytest-asyncio`'s event loop is used as the `anyio` backend transparently
- No `anyio_backend` fixture is needed (that fixture is for `pytest-anyio`, a
  different plugin)
- `pytest.mark.asyncio` (or `asyncio_mode = "auto"`) is sufficient

**Key compatibility concern**: The MCP SDK's official test suite uses
`pytest.mark.anyio` (via the `anyio` pytest plugin) rather than
`pytest.mark.asyncio`. The `anyio` plugin and `pytest-asyncio` can coexist
but are separate. The `anyio` plugin is NOT installed in this project, and
we should NOT install it -- `pytest-asyncio` handles event loop creation,
and `anyio` detects the existing loop at runtime. This has been verified to
work in practice with the `anyio` 4.x series (our version: 4.12.1).

**Potential issue**: `pytest-asyncio` v1.3.0 runs setup and teardown of async
generator fixtures in separate tasks. If a fixture yields inside an `anyio`
cancel scope or task group, the teardown may fail because the scope crosses
task boundaries. This was fixed in newer `pytest-asyncio` versions (0.23+).
However, for the `create_connected_server_and_client_session` pattern, the
`async with` block is used within a single test function body (not across
fixture yield), so this should not be an issue.


### 5. Windows asyncio concerns

**In-memory transport avoids the main Windows pain points.** The known
`WindowsProactorEventLoopPolicy` issues stem from:
- Subprocess pipes (IOCP handles) not cleaning up cleanly
- `ProactorEventLoop` required for subprocess support

The in-memory transport uses pure memory streams (`anyio.create_memory_object_stream`)
with no subprocess spawning, no pipes, and no IOCP handles. This means:
- No `ProactorEventLoop` is required
- The default `SelectorEventLoop` used by `pytest-asyncio` on Windows works
- The transport is fully cross-platform with no OS-specific codepaths

The existing `WindowsProactorEventLoopPolicy` set in `app.py` `main()` and
`cli_common.py` is only needed for the stdio transport (which spawns the
MCP server as a subprocess). In-memory tests bypass this entirely.

**Conclusion**: In-memory client session tests should be immune to the
Windows async hangs seen with subprocess-based tests.


### 6. Current test gap analysis

Current tests exercise three layers:

| Layer | Approach | Example |
|-------|----------|---------|
| Logic | Direct `await list_agents()` | `test_mcp_tools.py` |
| FastMCP pipeline | `await mcp.call_tool("list_agents", {})` | `test_mcp_protocol.py` |
| Registration | `await mcp.list_tools()` | `test_mcp_protocol.py` |

What is missing:

- **MCP protocol handshake**: `initialize()` negotiation of protocol version
  and capabilities is never tested. A misconfigured server would pass all
  current tests but fail with real MCP clients.

- **JSON-RPC serialization round-trip**: Tool arguments go through
  Pydantic/JSON-RPC serialization on a real client. Current tests pass Python
  dicts directly. Type coercion bugs (e.g., `int` vs `str` for `task_id`) would
  be invisible.

- **Error propagation via protocol**: `ToolError` in current tests raises a
  Python exception. Through the MCP protocol, errors become
  `CallToolResult(isError=True, content=[TextContent(...)])`. Client code that
  checks `isError` instead of catching exceptions would behave differently.

- **Resource listing and reading via protocol**: `agents://` resources are
  registered dynamically by `_register_agent_resources()`. The protocol-level
  `list_resources()` and `read_resource()` paths are never tested.

- **Tool schema validation**: The `ClientSession.call_tool()` method
  automatically validates structured results against `outputSchema`. No current
  test exercises this validation.

- **Server capabilities negotiation**: `InitializeResult.capabilities` reports
  which features the server supports (tools, resources, prompts). Never verified.

- **Concurrent tool calls**: The MCP protocol supports concurrent requests over
  a single session. In-memory transport is the only practical way to test this
  without a full server process.

- **Lifespan behavior**: Agent-file polling, resource registration on startup,
  `list_changed` notifications -- none are tested end-to-end.

- **Transport-level error handling**: Malformed requests, missing required
  fields, unknown tool names -- behavior through the full protocol stack vs.
  direct function calls.

- **Team tools via protocol**: All 10 team tools (`create_team`, `team_status`,
  `list_teams`, `dispatch_task`, `broadcast_message`, `send_message`,
  `spawn_agent`, `dissolve_team`, `relay_output`, `get_team_task_status`) are
  tested via direct function calls but never through the MCP protocol.


### 7. Recommended test structure

Based on the SDK source and our codebase patterns, the recommended approach for
in-memory client session tests:

**Fixture pattern:**

```python
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.client.session import ClientSession

@pytest.fixture
async def client_session() -> AsyncGenerator[ClientSession, None]:
    """In-memory MCP client connected to the vaultspec server."""
    initialize_server(
        root_dir=TEST_PROJECT,
        ttl_seconds=60.0,
        refresh_callback=lambda: False,
    )
    server = create_server()  # from mcp_server.app
    async with create_connected_server_and_client_session(
        server,
        raise_exceptions=True,
    ) as session:
        yield session
```

**Lifespan consideration**: The `create_server()` function attaches
`_lifespan` which includes `subagent_lifespan()`. This will:
- Call `_register_agent_resources()` which needs `AGENTS_DIR` to exist
- Start the poller task (harmless -- cancelled on exit)

If lifespan behavior is not desired for a particular test, create a bare
`FastMCP` and register tools without the lifespan:

```python
@pytest.fixture
async def client_session_no_lifespan() -> AsyncGenerator[ClientSession, None]:
    """In-memory MCP client without server lifespan."""
    initialize_server(root_dir=TEST_PROJECT, ...)
    mcp = FastMCP(name="test-vaultspec-mcp")
    register_subagent_tools(mcp)
    register_team_tools(mcp)
    async with create_connected_server_and_client_session(
        mcp,
        raise_exceptions=True,
    ) as session:
        yield session
```

**`raise_exceptions=True`**: This is critical for test debugging. When `False`
(default), exceptions in tool handlers are serialized as error responses. When
`True`, they propagate as Python exceptions, making test failures readable.

**Test categories to add:**

- `TestProtocolHandshake` -- verify `initialize()` returns expected
  capabilities (tools=True, resources=True, prompts=None)
- `TestToolDiscovery` -- `list_tools()` returns all 15 tools with correct
  schemas and annotations
- `TestResourceDiscovery` -- `list_resources()` returns `agents://` URIs,
  `read_resource()` returns valid JSON
- `TestToolCallRoundTrip` -- call each tool through the protocol, verify
  JSON-RPC serialization
- `TestErrorPropagation` -- unknown tool, invalid arguments, ToolError -- all
  via `CallToolResult.isError`
- `TestConcurrentCalls` -- fire multiple tool calls concurrently on a single
  session
- `TestLifecycle` -- dispatch, poll, complete cycle through the protocol
  (already partially covered in `test_mcp_protocol.py` but only at the
  `FastMCP.call_tool` level)


### 8. `inline-snapshot` assessment

The MCP SDK documentation recommends `inline-snapshot` for snapshot testing of
tool results. Status in this project:

- **Not installed** (`pip show inline-snapshot` returns nothing)
- **Not in dependencies** (absent from `pyproject.toml`)
- **No usage** in the codebase

`inline-snapshot` provides `snapshot()` assertions that auto-update expected
values in test source code on first run. This is useful for schema regression
testing (e.g., asserting the exact `list_tools()` response shape).

**Assessment**: Not required for the initial in-memory test phase. Standard
assertions against `ListToolsResult` fields are sufficient and more explicit.
Could be added later for schema regression if tool definitions change
frequently. Not a blocker.


### 9. SDK evolution: `Client` and `InMemoryTransport` (main branch)

The MCP SDK's `main` branch (unreleased at time of research) introduces:

- `mcp.client._memory.InMemoryTransport` -- wraps the memory stream setup
- `mcp.Client` -- high-level client class with `async with Client(server) as client:`

These are NOT available in v1.26.0. The `create_connected_server_and_client_session`
approach is the correct one for our pinned version. When the SDK releases these
APIs, the migration would be straightforward but is not necessary now.


### 10. NO-MOCK policy alignment

The in-memory client session approach aligns perfectly with the project's
strict no-mocking policy:

- No `unittest.mock`, `monkeypatch.setattr`, or test doubles needed
- The `ClientSession` is a real MCP client talking to a real MCP server
- JSON-RPC serialization/deserialization happens for real
- The only "fake" element is the transport (memory streams instead of stdio/HTTP),
  which is an explicitly supported and documented SDK feature
- `initialize_server()` with `refresh_callback=lambda: False` is an injection
  point already used in production code -- not a mock

The `_run_subagent_fn` override used in dispatch tests is a first-class
dependency injection parameter of `initialize_server()`, not a mock. It
replaces the actual subprocess-spawning `run_subagent` with a recording
function that exercises the same interface. This pattern should continue
unchanged in protocol-level tests.


## Summary of key decisions for implementation

- Use `create_connected_server_and_client_session` from `mcp.shared.memory`
  (available in SDK v1.26.0)
- Pass `raise_exceptions=True` for test debuggability
- Use `pytest-asyncio` with `asyncio_mode = "auto"` (no `anyio` plugin needed)
- Two fixture variants: with lifespan (for resource/lifecycle tests) and
  without (for focused tool tests)
- Error assertions must check `CallToolResult.isError` rather than
  `pytest.raises(ToolError)` since errors are protocol-level, not exceptions
- Windows compatibility is a non-issue for in-memory transport
- `inline-snapshot` is optional and not needed initially
