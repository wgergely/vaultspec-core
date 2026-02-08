# ACP (Agent Client Protocol) -- Technical Reference

**Date:** 2026-02-07
**Source:** Research agent -- ACP SDK deep dive
**Scope:** Full protocol surface area, SDK APIs, code examples

---

## 1. Protocol Overview

ACP is a JSON-RPC 2.0 based protocol enabling bidirectional communication between **Clients** (code editors, IDEs) and **Agents** (AI-powered coding tools). Created by Zed Industries.

- **Protocol version**: `uint16` (0-65535). Currently at version `1`. Version changes only for breaking changes; non-breaking additions use capabilities.
- **Transport**: stdio (primary, required). Messages are newline-delimited, UTF-8 encoded JSON-RPC. The client launches the agent as a subprocess. Messages MUST NOT contain embedded newlines. Agents MAY write to stderr for logging. Streamable HTTP is a draft proposal not yet finalized.
- **Message types**: Methods (request/response with `id`) and Notifications (one-way, no `id`).

---

## 2. Initialization (`initialize`)

**Direction**: Client -> Agent (request/response)

### Request

```json
{
  "jsonrpc": "2.0",
  "id": 0,
  "method": "initialize",
  "params": {
    "protocolVersion": 1,
    "clientCapabilities": {
      "fs": { "readTextFile": true, "writeTextFile": true },
      "terminal": true
    },
    "clientInfo": {
      "name": "my-editor",
      "title": "My Editor",
      "version": "1.0.0"
    }
  }
}
```

### Response

```json
{
  "jsonrpc": "2.0",
  "id": 0,
  "result": {
    "protocolVersion": 1,
    "agentCapabilities": {
      "loadSession": true,
      "promptCapabilities": {
        "image": false, "audio": false, "embeddedContext": true
      },
      "mcpCapabilities": { "http": true, "sse": false }
    },
    "agentInfo": { "name": "my-agent", "title": "My Agent", "version": "0.1.0" },
    "authMethods": []
  }
}
```

### Version Negotiation

- Client sends its latest supported version.
- If agent supports it: responds with same version.
- If not: responds with agent's latest version.
- Client should disconnect if it cannot support the response version.

### Capability Structures

**ClientCapabilities**:

| Field | Type | Description |
|---|---|---|
| `fs.readTextFile` | boolean | Supports `fs/read_text_file` |
| `fs.writeTextFile` | boolean | Supports `fs/write_text_file` |
| `terminal` | boolean | Supports all `terminal/*` methods |

**AgentCapabilities**:

| Field | Type | Default | Description |
|---|---|---|---|
| `loadSession` | boolean | false | Supports `session/load` |
| `promptCapabilities.image` | boolean | false | Accept image content blocks |
| `promptCapabilities.audio` | boolean | false | Accept audio content blocks |
| `promptCapabilities.embeddedContext` | boolean | false | Accept embedded resource blocks |
| `mcpCapabilities.http` | boolean | false | HTTP MCP transport |
| `mcpCapabilities.sse` | boolean | false | SSE MCP transport |

### Baseline Requirements

- All agents MUST support: `ContentBlock::Text` and `ContentBlock::ResourceLink`
- All agents MUST implement: `initialize`, `authenticate`, `session/new`, `session/prompt`, `session/cancel`
- All clients MUST implement: `session/request_permission`

---

## 3. Authentication (`authenticate`)

**Direction**: Client -> Agent

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "authenticate",
  "params": { "methodId": "oauth-github" }
}
```

Response: `AuthenticateResponse` (default empty). Called when agent requires auth before session creation.

---

## 4. Session Setup

### 4.1 New Session (`session/new`)

```json
{
  "jsonrpc": "2.0", "id": 2,
  "method": "session/new",
  "params": {
    "cwd": "/home/user/project",
    "mcpServers": [
      { "name": "my-tools", "command": "/usr/bin/mcp-server", "args": ["--port", "8080"],
        "env": [{"name": "API_KEY", "value": "xxx"}] },
      { "type": "http", "name": "remote-tools", "url": "https://mcp.example.com/v1",
        "headers": [{"name": "Authorization", "value": "Bearer xxx"}] }
    ]
  }
}
```

Response: `{ "sessionId": "sess_abc123", "modes": { "currentModeId": "code", "availableModes": [...] } }`

### MCP Server Transport Types

| Transport | Required Fields | Capability Gate |
|---|---|---|
| **Stdio** (required) | `name`, `command`, `args`, `env` | Always supported |
| **HTTP** (optional) | `type: "http"`, `name`, `url`, `headers` | `mcpCapabilities.http` |
| **SSE** (deprecated) | `type: "sse"`, `name`, `url`, `headers` | `mcpCapabilities.sse` |

### 4.2 Load Session (`session/load`)

Only if agent advertises `loadSession: true`. Agent replays conversation history via `session/update` notifications before responding.

### 4.3 Session Modes (`session/set_mode`)

Agent can also change modes autonomously via `session/update` with `current_mode_update`.

---

## 5. Prompt Turn (`session/prompt`)

### Request

```json
{
  "jsonrpc": "2.0", "id": 10,
  "method": "session/prompt",
  "params": {
    "sessionId": "sess_abc123",
    "prompt": [
      {"type": "text", "text": "Fix the bug in auth.py"},
      {"type": "resource_link", "uri": "file:///home/user/project/auth.py", "name": "auth.py"}
    ]
  }
}
```

### Response

```json
{ "result": { "stopReason": "end_turn" } }
```

**StopReason values**:

| Value | Meaning |
|---|---|
| `end_turn` | LLM completed naturally |
| `max_tokens` | Token limit exceeded |
| `max_turn_requests` | Max model requests per turn exceeded |
| `refusal` | Agent declines continuation |
| `cancelled` | Client initiated cancellation |

### Lifecycle

```
Client                          Agent
  |--- session/prompt ----------->|
  |                               |---> LLM Processing
  |<--- session/update (plan) ----|
  |<--- session/update (text) ----|
  |<--- session/update (tool) ----|
  |                               |---> Tool needs permission
  |<--- session/request_permission|
  |--- permission response ------>|
  |                               |---> Execute tool
  |<--- session/update (tool upd)-|
  |                               |---> Send results to LLM
  |<--- session/update (text) ----|
  |<--- prompt response ----------|
```

### Cancellation (`session/cancel`)

Notification, no response. Agent returns `stopReason: "cancelled"`.

---

## 6. Session Updates (`session/update`)

**Direction**: Agent -> Client (notification)

### Update Variants

| `sessionUpdate` value | Description |
|---|---|
| `user_message_chunk` | Replayed user message during session load |
| `agent_message_chunk` | Agent text/content output |
| `agent_thought_chunk` | Agent internal reasoning |
| `tool_call` | New tool call initiated |
| `tool_call_update` | Tool call progress/completion |
| `plan` | Agent plan with entries |
| `available_commands_update` | Slash commands available |
| `current_mode_update` | Mode change notification |
| `config_option_update` | Config option change |
| `session_info_update` | Session metadata update (unstable) |

### Plan Update Example

```json
{
  "sessionUpdate": "plan",
  "entries": [
    {"content": "Read auth.py", "priority": "high", "status": "completed"},
    {"content": "Fix token validation", "priority": "high", "status": "in_progress"},
    {"content": "Add tests", "priority": "medium", "status": "pending"}
  ]
}
```

### Tool Call Start Example

```json
{
  "sessionUpdate": "tool_call",
  "toolCallId": "call_001",
  "title": "Reading auth.py",
  "kind": "read",
  "status": "pending",
  "content": [],
  "locations": [{"path": "/home/user/project/auth.py", "line": 42}],
  "rawInput": {"path": "/home/user/project/auth.py"},
  "rawOutput": {}
}
```

---

## 7. Tool Calls

### Tool Kinds

`read`, `edit`, `delete`, `move`, `search`, `execute`, `think`, `fetch`, `other`

### Tool Call Status Lifecycle

`pending` -> `in_progress` -> `completed` | `failed` | `cancelled`

### Tool Call Content Types

- **Regular content**: `{"type": "content", "content": {"type": "text", "text": "..."}}`
- **Diff**: `{"type": "diff", "path": "...", "oldText": "...", "newText": "..."}`
- **Terminal reference**: `{"type": "terminal", "terminalId": "term_xyz789"}`

---

## 8. Permission System (`session/request_permission`)

**Direction**: Agent -> Client

```json
{
  "jsonrpc": "2.0", "id": 5,
  "method": "session/request_permission",
  "params": {
    "sessionId": "sess_abc123",
    "toolCall": { "toolCallId": "call_001", "title": "Write to config.json", "kind": "edit", "status": "pending" },
    "options": [
      {"optionId": "allow-once", "name": "Allow once", "kind": "allow_once"},
      {"optionId": "allow-always", "name": "Always allow", "kind": "allow_always"},
      {"optionId": "reject-once", "name": "Reject", "kind": "reject_once"},
      {"optionId": "reject-always", "name": "Never allow", "kind": "reject_always"}
    ]
  }
}
```

**Response**: `{ "outcome": { "outcome": "selected", "optionId": "allow-once" } }`

**Outcome types**: `cancelled` (prompt turn was cancelled) | `selected` (user chose an option, includes `optionId`)

---

## 9. File System

### Read (`fs/read_text_file`)

Agent -> Client. Params: `path` (absolute), `sessionId`, `line` (1-based, optional), `limit` (optional).
Response: `{"content": "file contents..."}`

### Write (`fs/write_text_file`)

Agent -> Client. Params: `path` (absolute), `sessionId`, `content`. Client MUST create file if not exists.
Response: `null`.

---

## 10. Terminals

All require `clientCapabilities.terminal: true`.

| Method | Description |
|---|---|
| `terminal/create` | Spawn subprocess, returns `terminalId` immediately |
| `terminal/output` | Get current output + optional exit status |
| `terminal/wait_for_exit` | Block until completion |
| `terminal/kill` | Terminate command, ID remains valid |
| `terminal/release` | Kill + release all resources, ID becomes invalid |

### Create Parameters

- `command` (string): Executable path
- `args` (string[]): Arguments
- `env` ([{name, value}]): Environment variables
- `cwd` (string): Working directory
- `outputByteLimit` (number): Truncation limit

### Output Response

- `output` (string): Current terminal output
- `truncated` (boolean): Whether byte limit caused truncation
- `exitStatus` (optional): `{ exitCode: number|null, signal: string|null }` -- only present when exited

### Recommended Pattern

```
1. terminal/create -> get terminalId
2. Race: terminal/wait_for_exit vs timeout
3. If timeout: terminal/kill, then terminal/output
4. Always: terminal/release
```

---

## 11. Content Blocks

### Text (baseline, always supported)

```json
{"type": "text", "text": "Hello world", "annotations": null}
```

### Image (requires `promptCapabilities.image`)

```json
{"type": "image", "mimeType": "image/png", "data": "<base64>", "uri": "file:///path/to/image.png"}
```

### Audio (requires `promptCapabilities.audio`)

```json
{"type": "audio", "mimeType": "audio/wav", "data": "<base64>"}
```

### Resource Link (baseline, always supported)

```json
{
  "type": "resource_link", "uri": "file:///path/to/file.py", "name": "file.py",
  "mimeType": "text/x-python", "size": 2048, "title": "Main module", "description": "The entry point"
}
```

### Embedded Resource (requires `promptCapabilities.embeddedContext`)

```json
{
  "type": "resource",
  "resource": { "uri": "file:///path/to/file.py", "mimeType": "text/x-python", "text": "def main():\n    pass" }
}
```

---

## 12. Extensibility

### `_meta` Field

All protocol types include optional `_meta: { [key: string]: unknown }`. Reserved keys: `traceparent`, `tracestate`, `baggage` (W3C trace context).

### Custom Methods

Any method starting with `_` is a custom extension. Must return `-32601` for unrecognized extensions.

### Error Codes

| Code | Name |
|---|---|
| `-32700` | Parse error |
| `-32600` | Invalid request |
| `-32601` | Method not found |
| `-32602` | Invalid params |
| `-32603` | Internal error |
| `-32000` | Authentication required |
| `-32002` | Resource not found |

---

## 13. Proxy Chains (RFD)

### Architecture

```
Client -> Conductor -> Proxy1 -> Proxy2 -> Agent
```

A **conductor** orchestrates all message routing. Single new method: **`proxy/successor`**.

### Component Roles

- **Terminal Client**: Originates requests; only has a successor
- **Conductor**: Manages proxy chains; spawns components; routes messages
- **Proxy**: Non-terminal; has both predecessor and successor; transforms messages
- **Terminal Agent**: Final destination; processes messages directly

### Key Methods

- `proxy/initialize`: Signals a component operates as a proxy (has a successor)
- `initialize`: Signals a terminal agent (no successor)
- `proxy/successor`: Wraps inner messages traveling to/from successors

### What Proxies Can Do

- Inject/modify prompts, add global context, transform responses
- Add MCP servers for tool provisioning, filter tools
- Switch between session modes, delay client prompts during initialization

### What Proxies Cannot Do

- Modify system prompts directly (only prepend messages)
- Access internal agent state or model parameters

### Conductor Modes

- **Terminal mode**: Receives `initialize`; manages chains; acts as agent
- **Proxy mode**: Receives `proxy/initialize`; forwards to parent
- **Hierarchical nesting**: Conductor chains

### Future Extensions

Multi-agent support via optional `peer` field in `proxy/successor` for M:N topologies.

---

## 14. MCP-over-ACP (RFD)

Enables MCP servers to communicate through ACP channels.

### Capability Advertisement

```json
{ "capabilities": { "mcpCapabilities": { "acp": true } } }
```

### Connection Protocol

- `mcp/connect` -> `{ "connectionId": "conn-123" }`
- `mcp/message` -> Exchange MCP methods over the connection
- `mcp/disconnect` -> Close connection

Supports connection multiplexing and bidirectional messaging.

---

## 15. Rust SDK

**Crate**: `agent-client-protocol` (v0.9.4), Edition 2024, Apache-2.0

### Workspace Crates

`agent-client-protocol`, `agent-client-protocol-schema`, `sacp`, `sacp-tokio`, `sacp-proxy`, `sacp-rmcp`, `sacp-conductor`, `sacp-test`, `sacp-tee`

### Key: Non-Send Futures

Uses `async_trait(?Send)` -- requires `tokio::task::LocalSet` and `spawn_local`.

### Agent Trait (Complete)

```rust
#[async_trait::async_trait(?Send)]
pub trait Agent {
    // Required methods:
    async fn initialize(&self, args: InitializeRequest) -> Result<InitializeResponse>;
    async fn authenticate(&self, args: AuthenticateRequest) -> Result<AuthenticateResponse>;
    async fn new_session(&self, args: NewSessionRequest) -> Result<NewSessionResponse>;
    async fn prompt(&self, args: PromptRequest) -> Result<PromptResponse>;
    async fn cancel(&self, args: CancelNotification) -> Result<()>;

    // Optional methods (default: Error::method_not_found()):
    async fn load_session(&self, _args: LoadSessionRequest) -> Result<LoadSessionResponse>;
    async fn set_session_mode(&self, _args: SetSessionModeRequest) -> Result<SetSessionModeResponse>;
    async fn set_session_config_option(&self, _args: SetSessionConfigOptionRequest) -> Result<SetSessionConfigOptionResponse>;
    async fn ext_method(&self, _args: ExtRequest) -> Result<ExtResponse>;
    async fn ext_notification(&self, _args: ExtNotification) -> Result<()>;

    // Unstable (feature-gated):
    #[cfg(feature = "unstable_session_model")]
    async fn set_session_model(&self, _args: SetSessionModelRequest) -> Result<SetSessionModelResponse>;
    #[cfg(feature = "unstable_session_list")]
    async fn list_sessions(&self, _args: ListSessionsRequest) -> Result<ListSessionsResponse>;
    #[cfg(feature = "unstable_session_fork")]
    async fn fork_session(&self, _args: ForkSessionRequest) -> Result<ForkSessionResponse>;
    #[cfg(feature = "unstable_session_resume")]
    async fn resume_session(&self, _args: ResumeSessionRequest) -> Result<ResumeSessionResponse>;
}
```

### Client Trait (Complete)

```rust
#[async_trait::async_trait(?Send)]
pub trait Client {
    // Required methods:
    async fn request_permission(&self, args: RequestPermissionRequest) -> Result<RequestPermissionResponse>;
    async fn session_notification(&self, args: SessionNotification) -> Result<()>;

    // Optional methods (default: Error::method_not_found()):
    async fn write_text_file(&self, _args: WriteTextFileRequest) -> Result<WriteTextFileResponse>;
    async fn read_text_file(&self, _args: ReadTextFileRequest) -> Result<ReadTextFileResponse>;
    async fn create_terminal(&self, _args: CreateTerminalRequest) -> Result<CreateTerminalResponse>;
    async fn terminal_output(&self, _args: TerminalOutputRequest) -> Result<TerminalOutputResponse>;
    async fn release_terminal(&self, _args: ReleaseTerminalRequest) -> Result<ReleaseTerminalResponse>;
    async fn wait_for_terminal_exit(&self, _args: WaitForTerminalExitRequest) -> Result<WaitForTerminalExitResponse>;
    async fn kill_terminal_command(&self, _args: KillTerminalCommandRequest) -> Result<KillTerminalCommandResponse>;
    async fn ext_method(&self, _args: ExtRequest) -> Result<ExtResponse>;
    async fn ext_notification(&self, _args: ExtNotification) -> Result<()>;
}
```

### Connection Types

**`ClientSideConnection`** -- Client's view. Implements the `Agent` trait for sending requests to the agent.

```rust
let (conn, handle_io) = acp::ClientSideConnection::new(
    my_client,        // impl Client
    outgoing_bytes,   // impl AsyncWrite
    incoming_bytes,   // impl AsyncRead
    |fut| { tokio::task::spawn_local(fut); }
);
// conn implements Agent trait -- use conn.initialize(), conn.prompt(), etc.
```

**`AgentSideConnection`** -- Agent's view. Implements the `Client` trait for sending requests to the client.

```rust
let (conn, handle_io) = acp::AgentSideConnection::new(
    my_agent,         // impl Agent
    outgoing_bytes,   // impl AsyncWrite
    incoming_bytes,   // impl AsyncRead
    |fut| { tokio::task::spawn_local(fut); }
);
// conn implements Client trait -- use conn.session_notification(), etc.
```

Both return a `StreamReceiver` via `conn.subscribe()` for real-time stream updates.

### Key Rust Types

```rust
pub const V1: u16 = 1;

pub struct SessionId(pub Arc<str>);

pub enum StopReason { EndTurn, MaxTokens, MaxTurnRequests, Refusal, Cancelled }

pub enum ContentBlock {
    Text(TextContentBlock),
    Image(ImageContentBlock),
    Audio(AudioContentBlock),
    ResourceLink(ResourceLinkContentBlock),
    Resource(EmbeddedResourceContentBlock),
}

pub enum SessionUpdate {
    UserMessageChunk(ContentChunk),
    AgentMessageChunk(ContentChunk),
    AgentThoughtChunk(ContentChunk),
    ToolCallStart(ToolCallStart),
    ToolCallProgress(ToolCallProgress),
    Plan(AgentPlanUpdate),
    AvailableCommandsUpdate(AvailableCommandsUpdate),
    CurrentModeUpdate(CurrentModeUpdate),
    ConfigOptionUpdate(ConfigOptionUpdate),
}
```

### Unstable Feature Flags

```toml
[dependencies]
agent-client-protocol = { version = "0.9", features = ["unstable"] }
# Or individual: "unstable_session_model", "unstable_session_fork",
#   "unstable_session_list", "unstable_session_resume"
```

### Rust Agent Example (Complete)

```rust
use std::cell::Cell;
use agent_client_protocol::{self as acp, Client as _};
use tokio::sync::{mpsc, oneshot};
use tokio_util::compat::{TokioAsyncReadCompatExt as _, TokioAsyncWriteCompatExt as _};

struct ExampleAgent {
    session_update_tx: mpsc::UnboundedSender<(acp::SessionNotification, oneshot::Sender<()>)>,
    next_session_id: Cell<u64>,
}

#[async_trait::async_trait(?Send)]
impl acp::Agent for ExampleAgent {
    async fn initialize(&self, _args: acp::InitializeRequest) -> Result<acp::InitializeResponse, acp::Error> {
        Ok(acp::InitializeResponse {
            protocol_version: acp::V1,
            agent_capabilities: acp::AgentCapabilities::default(),
            auth_methods: Vec::new(),
            agent_info: Some(acp::Implementation {
                name: "example-agent".to_string(),
                title: Some("Example Agent".to_string()),
                version: "0.1.0".to_string(),
            }),
            meta: None,
        })
    }

    async fn authenticate(&self, _args: acp::AuthenticateRequest) -> Result<acp::AuthenticateResponse, acp::Error> {
        Ok(acp::AuthenticateResponse::default())
    }

    async fn new_session(&self, _args: acp::NewSessionRequest) -> Result<acp::NewSessionResponse, acp::Error> {
        let session_id = self.next_session_id.get();
        self.next_session_id.set(session_id + 1);
        Ok(acp::NewSessionResponse {
            session_id: acp::SessionId(session_id.to_string().into()),
            modes: None,
            meta: None,
        })
    }

    async fn prompt(&self, arguments: acp::PromptRequest) -> Result<acp::PromptResponse, acp::Error> {
        for content in ["Client sent: ".into()].into_iter().chain(arguments.prompt) {
            let (tx, rx) = oneshot::channel();
            self.session_update_tx.send((
                acp::SessionNotification {
                    session_id: arguments.session_id.clone(),
                    update: acp::SessionUpdate::AgentMessageChunk(acp::ContentChunk {
                        content, meta: None,
                    }),
                    meta: None,
                },
                tx,
            )).map_err(|_| acp::Error::internal_error())?;
            rx.await.map_err(|_| acp::Error::internal_error())?;
        }
        Ok(acp::PromptResponse { stop_reason: acp::StopReason::EndTurn, meta: None })
    }

    async fn cancel(&self, _args: acp::CancelNotification) -> Result<(), acp::Error> { Ok(()) }
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> acp::Result<()> {
    let outgoing = tokio::io::stdout().compat_write();
    let incoming = tokio::io::stdin().compat();
    let local_set = tokio::task::LocalSet::new();
    local_set.run_until(async move {
        let (tx, mut rx) = mpsc::unbounded_channel();
        let (conn, handle_io) = acp::AgentSideConnection::new(
            ExampleAgent { session_update_tx: tx, next_session_id: Cell::new(0) },
            outgoing, incoming,
            |fut| { tokio::task::spawn_local(fut); }
        );
        tokio::task::spawn_local(async move {
            while let Some((notification, tx)) = rx.recv().await {
                if conn.session_notification(notification).await.is_err() { break; }
                tx.send(()).ok();
            }
        });
        handle_io.await
    }).await
}
```

### Rust Client Example (Complete)

```rust
use agent_client_protocol::{self as acp, Agent as _};
use tokio_util::compat::{TokioAsyncReadCompatExt, TokioAsyncWriteCompatExt};

struct ExampleClient;

#[async_trait::async_trait(?Send)]
impl acp::Client for ExampleClient {
    async fn request_permission(&self, _args: acp::RequestPermissionRequest) -> acp::Result<acp::RequestPermissionResponse> {
        Err(acp::Error::method_not_found())
    }

    async fn session_notification(&self, args: acp::SessionNotification) -> acp::Result<()> {
        if let acp::SessionUpdate::AgentMessageChunk(acp::ContentChunk { content, .. }) = args.update {
            let text = match content {
                acp::ContentBlock::Text(tc) => tc.text,
                acp::ContentBlock::ResourceLink(rl) => rl.uri,
                _ => "<other>".into(),
            };
            println!("| Agent: {text}");
        }
        Ok(())
    }
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> anyhow::Result<()> {
    let mut child = tokio::process::Command::new("path/to/agent")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .kill_on_drop(true)
        .spawn()?;

    let outgoing = child.stdin.take().unwrap().compat_write();
    let incoming = child.stdout.take().unwrap().compat();

    let local_set = tokio::task::LocalSet::new();
    local_set.run_until(async move {
        let (conn, handle_io) = acp::ClientSideConnection::new(
            ExampleClient, outgoing, incoming,
            |fut| { tokio::task::spawn_local(fut); }
        );
        tokio::task::spawn_local(handle_io);

        conn.initialize(acp::InitializeRequest {
            protocol_version: acp::V1,
            client_capabilities: acp::ClientCapabilities::default(),
            client_info: Some(acp::Implementation {
                name: "example-client".to_string(),
                title: Some("Example Client".to_string()),
                version: "0.1.0".to_string(),
            }),
            meta: None,
        }).await?;

        let response = conn.new_session(acp::NewSessionRequest {
            mcp_servers: Vec::new(),
            cwd: std::env::current_dir()?,
            meta: None,
        }).await?;

        conn.prompt(acp::PromptRequest {
            session_id: response.session_id.clone(),
            prompt: vec!["Hello agent!".into()],
            meta: None,
        }).await?;

        Ok(())
    }).await
}
```

---

## 16. Python SDK

**Package**: `agent-client-protocol` on PyPI, imported as `acp`

### Core API

```python
from acp import (
    PROTOCOL_VERSION,
    run_agent, connect_to_agent, spawn_agent_process,
    text_block, image_block, resource_link_block,
    start_tool_call, update_tool_call, tool_diff_content,
    update_agent_message, update_agent_message_text,
    update_plan, plan_entry, session_notification,
)
```

### Python Agent Protocol

```python
class Agent(Protocol):
    async def initialize(self, protocol_version, client_capabilities=None, client_info=None, **kwargs) -> InitializeResponse: ...
    async def authenticate(self, method_id, **kwargs) -> AuthenticateResponse | None: ...
    async def new_session(self, cwd, mcp_servers, **kwargs) -> NewSessionResponse: ...
    async def load_session(self, cwd, mcp_servers, session_id, **kwargs) -> LoadSessionResponse | None: ...
    async def prompt(self, prompt, session_id, **kwargs) -> PromptResponse: ...
    async def cancel(self, session_id, **kwargs) -> None: ...
    def on_connect(self, conn: Client) -> None: ...
```

### Python Client Protocol

```python
class Client(Protocol):
    async def request_permission(self, options, session_id, tool_call, **kwargs) -> RequestPermissionResponse: ...
    async def session_update(self, session_id, update, **kwargs) -> None: ...
    async def write_text_file(self, content, path, session_id, **kwargs) -> WriteTextFileResponse | None: ...
    async def read_text_file(self, path, session_id, **kwargs) -> ReadTextFileResponse: ...
    async def create_terminal(self, command, session_id, **kwargs) -> CreateTerminalResponse: ...
    async def terminal_output(self, session_id, terminal_id, **kwargs) -> TerminalOutputResponse: ...
    async def release_terminal(self, session_id, terminal_id, **kwargs) -> ReleaseTerminalResponse | None: ...
    async def wait_for_terminal_exit(self, session_id, terminal_id, **kwargs) -> WaitForTerminalExitResponse: ...
    async def kill_terminal(self, session_id, terminal_id, **kwargs) -> KillTerminalCommandResponse | None: ...
    def on_connect(self, conn: Agent) -> None: ...
```

### Python Agent Example

```python
import asyncio
from acp import PROTOCOL_VERSION, Agent, run_agent, text_block, update_agent_message
from acp.schema import AgentCapabilities, Implementation

class ExampleAgent(Agent):
    _conn = None

    def on_connect(self, conn):
        self._conn = conn

    async def initialize(self, protocol_version, client_capabilities=None, client_info=None, **kwargs):
        from acp.schema import InitializeResponse
        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(),
            agent_info=Implementation(name="my-agent", title="My Agent", version="0.1.0"),
        )

    async def authenticate(self, method_id, **kwargs):
        return None

    async def new_session(self, cwd, mcp_servers, **kwargs):
        from acp.schema import NewSessionResponse
        return NewSessionResponse(session_id="sess_0", modes=None)

    async def prompt(self, prompt, session_id, **kwargs):
        from acp.schema import PromptResponse
        await self._conn.session_update(session_id, update_agent_message(text_block("Hello!")))
        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id, **kwargs):
        pass

asyncio.run(run_agent(ExampleAgent()))
```

---

## 17. JSON-RPC Method Reference

### Agent Interface (Client -> Agent)

| Method | Type | Required |
|---|---|---|
| `initialize` | Request | Yes |
| `authenticate` | Request | Yes |
| `session/new` | Request | Yes |
| `session/load` | Request | If `loadSession` |
| `session/prompt` | Request | Yes |
| `session/cancel` | Notification | Yes |
| `session/set_mode` | Request | No |
| `session/set_config_option` | Request | No |
| `session/set_model` | Request | Unstable |
| `session/list` | Request | Unstable |
| `session/fork` | Request | Unstable |
| `session/resume` | Request | Unstable |
| `_*` | Request/Notification | Extension |

### Client Interface (Agent -> Client)

| Method | Type | Required |
|---|---|---|
| `session/request_permission` | Request | Yes |
| `session/update` | Notification | Yes |
| `fs/read_text_file` | Request | If `fs.readTextFile` |
| `fs/write_text_file` | Request | If `fs.writeTextFile` |
| `terminal/create` | Request | If `terminal` |
| `terminal/output` | Request | If `terminal` |
| `terminal/wait_for_exit` | Request | If `terminal` |
| `terminal/kill` | Request | If `terminal` |
| `terminal/release` | Request | If `terminal` |
| `_*` | Request/Notification | Extension |

---

## 18. Key Design Principles

1. Paths must be absolute. Line numbers are 1-based.
2. Capability-gated features -- check before calling.
3. MCP alignment -- content blocks align with MCP types.
4. Session-scoped operations -- all ops after init are scoped to `sessionId`.
5. Streaming via notifications -- intermediate output flows through `session/update`, not prompt response.
6. Agent owns cleanup -- responsible for releasing terminals.
7. Non-Send futures -- Rust SDK uses `?Send` async traits, requiring `LocalSet` and `spawn_local`.
8. Extension safety -- custom fields go in `_meta`; custom methods use underscore prefix.

---

## Sources

- <https://agentclientprotocol.com/protocol> (overview, schema, transports)
- <https://agentclientprotocol.com/protocol/tool-calls>
- <https://agentclientprotocol.com/rfds/proxy-chains>
- <https://agentclientprotocol.com/rfds/mcp-over-acp>
- GitHub: `agentclientprotocol/rust-sdk`
- GitHub: `agentclientprotocol/python-sdk`
