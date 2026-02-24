---
tags:
  - "#research"
  - "#protocol"
date: "2026-02-20"
related:
  - "[[2026-02-07-a2a-research]]"
---
# A2A Team research: Gemini CLI Native A2A and ACP Team Support

Investigation of Gemini CLI's native capabilities for participation in multi-agent
teams, covering ACP mode, A2A client/server support, Google ADK vs a2a-sdk,
discovery configuration, session persistence, and security.

## Findings

### 1. Gemini CLI ACP Mode (`--experimental-acp`)

**What it provides:** The `--experimental-acp` flag enables ACP (Agent Client Protocol)
support, allowing orchestrators to communicate with Gemini CLI via stdin/stdout
JSON-RPC framing. This is the mechanism used by Zed editor and by vaultspec's own
`GeminiProvider` to dispatch Gemini as a subagent.

**Current vaultspec implementation** (`.vaultspec/lib/src/protocol/providers/gemini.py`):

- `GeminiProvider.prepare_process()` builds a `ProcessSpec` with
  `["--experimental-acp", "--model", model]` args
- System prompt delivered via `GEMINI_SYSTEM_MD` environment variable pointing to a
  temp file (Gemini CLI has no `--system` flag)
- The process is spawned via `acp.spawn_agent_process()` in
  `orchestration/subagent.py`, which manages the ACP lifecycle:
  handshake -> new_session -> prompt -> cancel -> cleanup
- `SubagentClient` (`.vaultspec/lib/src/protocol/acp/client.py`) implements the ACP
  `Client` interface, handling permissions, file I/O, terminal management, and
  session updates

**Can Gemini CLI act as:**

- **A persistent A2A server (lingering, waiting for tasks)?** No. In ACP mode, Gemini
  CLI acts as an ACP *agent* (server-side of the ACP protocol), but it is a subprocess
  that handles one session at a time. It does not expose HTTP endpoints. The RFC
  (github.com/google-gemini/gemini-cli/discussions/7822) proposes evolving the
  experimental A2A server into a proper extension, but this is still RFC-phase
  (Sep 2025).

- **An A2A client (sending tasks to other agents)?** Yes, experimentally. PR #3079
  added an `@a2a` tool that allows the Gemini model to send messages to external A2A
  agents during its execution. This is client-side only: Gemini discovers agents via
  `.well-known/agent.json` and sends tasks via JSON-RPC.

- **Both simultaneously (bidirectional)?** Not currently. Gemini can consume A2A agents
  via the `@a2a` tool while being orchestrated over ACP, but it cannot receive
  inbound A2A tasks while running.

### 2. Gemini Native Agent Features

**Gemini API:** No native A2A endpoint in the Gemini API itself. A2A is implemented at
the CLI/ADK layer, not the model API layer.

**Gemini CLI flags beyond `--experimental-acp`:**

- `--sandbox`: Restricts file system writes
- `--model`: Model selection
- `--allowed-tools`: Tool allowlisting
- `--approval-mode`: default|auto_edit|yolo|plan
- `--output-format`: text|json|stream-json
- `--include-directories`: Additional workspace directories
- `--resume [index/ID]`: Resume previous sessions
- No `--agent` or explicit team flags

**Gemini CLI remote subagents (experimental):**

- Defined in `.gemini/agents/*.md` with YAML frontmatter: `kind: remote`,
  `name: <id>`, `agent_card_url: <url>`
- Gemini delegates tasks to these agents using A2A protocol
- Mixed local+remote agents not supported in a single file
- Requires `{"experimental": {"enableAgents": true}}` in settings.json

**Gemini Live API:** Designed for real-time multimodal streaming (audio/video), not
A2A task coordination. Not relevant for persistent two-way agent channels.

### 3. Google ADK vs a2a-sdk

**Existing decision:** The project ADR chose `a2a-sdk` directly over Google ADK.

**What Google ADK adds:**

- **Agent hierarchy:** `SequentialAgent`, `ParallelAgent`, `LoopAgent` workflow
  orchestrators for composing multi-agent pipelines
- **Built-in orchestration:** LLM-driven dynamic routing and delegation
- **A2A integration:** `A2AServer` (expose agent) and `RemoteA2aAgent` (consume
  agent) wrappers around a2a-sdk
- **Tool ecosystem:** Pre-built tools, LangChain/CrewAI integration
- **Agent Engine:** Deployment to Google Cloud Agent Engine (Vertex AI)

**What a2a-sdk provides alone:**

- Full A2A protocol implementation (JSON-RPC, SSE, gRPC)
- `AgentExecutor` abstract class for implementing agents
- `A2AStarletteApplication` / `A2AFastAPIApplication` for HTTP servers
- `A2AClient` / `A2ACardResolver` for discovery and communication
- `TaskUpdater`, `InMemoryTaskStore`, push notification support
- Enterprise auth: API keys, OAuth 2.0, mTLS

**Assessment:** a2a-sdk remains the right choice for vaultspec. The project already
has its own orchestration layer (`orchestration/task_engine.py`,
`orchestration/subagent.py`) and provider abstraction (`protocol/providers/`). ADK
would introduce a parallel orchestration framework with overlapping concerns. The
project only needs A2A's *protocol* layer, not ADK's *agent framework*. The existing
`GeminiA2AExecutor` (`.vaultspec/lib/src/protocol/a2a/executors/gemini_executor.py`)
already wraps `run_subagent()` into an A2A executor, demonstrating that the a2a-sdk
approach works cleanly with vaultspec's architecture.

### 4. Gemini as A2A Server

**Native support:** The Gemini CLI cannot currently run as a persistent A2A HTTP server.
The RFC proposes this capability but it remains unimplemented.

**Minimum wrapper using existing code:**

The project already has the pieces:

1. `GeminiA2AExecutor` wraps `run_subagent()` (which spawns Gemini CLI via ACP) into
   an A2A `AgentExecutor`
2. `a2a-sdk`'s `A2AStarletteApplication` provides the HTTP server
3. `InMemoryTaskStore` handles task state management

The minimum wrapper is approximately:

```python
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from protocol.a2a.executors.gemini_executor import GeminiA2AExecutor

handler = DefaultRequestHandler(
    agent_executor=GeminiA2AExecutor(root_dir=root, agent_name="vaultspec-researcher"),
    task_store=InMemoryTaskStore(),
)
server = A2AStarletteApplication(agent_card=card, http_handler=handler)
# uvicorn.run(server.build(), host="0.0.0.0", port=10010)
```

Each inbound A2A task spawns a fresh Gemini CLI subprocess via ACP. This is
*not* a persistent Gemini session -- each task gets its own lifecycle. For true
persistence, the ACP session resume mechanism (`--resume`) would need integration.

### 5. Gemini Config Discovery

**`.gemini/agents/*.md` configuration:**

```yaml
---
kind: remote
name: my-remote-agent
agent_card_url: https://example.com/.well-known/agent.json
---
Description of the agent.
```

- Project-level: `.gemini/agents/*.md` (shared with team)
- User-level: `~/.gemini/agents/*.md` (personal agents)
- `/agents refresh` reloads the registry at runtime

**`settings.json` experimental flags:**

```json
{
  "experimental": {
    "enableAgents": true
  },
  "maxSessionTurns": 100,
  "session": {
    "maxAge": "30d",
    "maxCount": 50,
    "minRetention": "1d"
  }
}
```

Located at `~/.gemini/settings.json`.

**Can `agent_card_url` point to a vaultspec A2A server?** Yes. If vaultspec runs an
A2A server (using `A2AStarletteApplication` + `GeminiA2AExecutor` or
`ClaudeA2AExecutor`), the URL can be configured in `.gemini/agents/<name>.md` and
Gemini CLI will discover and delegate tasks to it.

The existing `discovery.py` module
(`.vaultspec/lib/src/protocol/a2a/discovery.py`) already generates these files:

- `write_agent_discovery()` creates `.gemini/agents/<name>.md` with the agent card URL
- `write_gemini_settings()` enables `experimental.enableAgents`

**Is there `enableAgents: true` or similar?** Yes, exactly:
`settings.json` -> `experimental.enableAgents: true`.

### 6. Gemini CLI Session Persistence

**Subprocess lifecycle:** Each `run_subagent()` call spawns a fresh Gemini CLI process
via `acp.spawn_agent_process()`. The process lives for the duration of one ACP
session (handshake -> prompt(s) -> cancel). After `cancel()`, the process is
terminated during cleanup.

**How long can it stay alive?** The Gemini CLI process stays alive as long as the ACP
connection is open. In non-interactive mode (vaultspec default), it processes one
prompt and exits. In interactive mode, the `_interactive_loop()` in
`orchestration/subagent.py` keeps the connection alive for multiple turns until
the user types "exit"/"quit"/"bye" or the process exits.

**Lingering team member?** Not with the current architecture. Each dispatch creates a
new subprocess. However, the Gemini CLI's native session management stores
conversation history at `~/.gemini/tmp/<project_hash>/chats/`, and `--resume` can
restore context. This could theoretically be leveraged for multi-turn team workflows
by passing `resume_session_id` through `run_subagent()`, but:

- The ACP protocol does not persist conversation history across client instances
  (noted in `ClaudeACPBridge.load_session()` docstring)
- Each new ACP connection creates a fresh SDK/CLI client
- Session "resume" restores configuration, not conversation context

**For true persistence,** the A2A server approach is more appropriate: a persistent
HTTP process wrapping GeminiA2AExecutor, where each task gets its own subprocess
but the server itself lingers indefinitely.

### 7. Security Considerations

**Gemini CLI authentication methods:**

- Google OAuth 2.0 (browser-based, cached tokens)
- Gemini API keys (via `GEMINI_API_KEY` env var)
- Vertex AI / Application Default Credentials (enterprise)

**A2A protocol security (per spec):**

- Agent Card declares `securitySchemes` and `securityRequirements`
- Supported: API keys, HTTP auth (Bearer/Basic), OAuth 2.0 (authorization code,
  client credentials, device code), OpenID Connect, mTLS
- Push notifications secured via JWT + JWKS, HMAC, or mTLS

**Authentication as a team member to vaultspec A2A server:**

- For local development (localhost), no auth is strictly required -- the A2A spec
  allows unauthenticated connections
- For production/shared environments, the vaultspec A2A server should declare an API
  key or Bearer token scheme in its AgentCard
- Gemini CLI's `@a2a` tool currently has no authentication configuration for outbound
  A2A calls (limitation of the experimental feature)
- For inbound: Gemini Enterprise on Google Cloud supports registering A2A agents with
  OAuth credentials via `gcloud` CLI

**Recommendation:** For the initial a2a-team implementation, use unauthenticated
localhost connections. Add API key authentication (simplest A2A security scheme) when
moving to networked deployments.

## Summary Table

| Capability | Status | Notes |
|---|---|---|
| Gemini as ACP agent (subprocess) | Working | Current `GeminiProvider` implementation |
| Gemini as A2A client (@a2a tool) | Experimental | PR #3079, needs `enableAgents` |
| Gemini as A2A server | Not available | RFC proposed, unimplemented |
| Gemini discovering vaultspec A2A agents | Supported | Via `.gemini/agents/*.md` + `enableAgents` |
| Persistent Gemini team member | Not supported | Each task = new subprocess |
| ADK vs a2a-sdk | a2a-sdk preferred | ADK adds framework overhead vaultspec doesn't need |
| Auth for local team | Unauthenticated OK | API keys for networked deployments |

## Sources

- [Gemini CLI GitHub](https://github.com/google-gemini/gemini-cli)
- [Gemini CLI A2A PR #3079](https://github.com/google-gemini/gemini-cli/pull/3079)
- [Gemini CLI A2A RFC Discussion #7822](https://github.com/google-gemini/gemini-cli/discussions/7822)
- [Gemini CLI Remote Subagents Docs](https://geminicli.com/docs/core/remote-agents/)
- [Gemini CLI Subagents Docs](https://geminicli.com/docs/core/subagents/)
- [Gemini CLI Session Management](https://geminicli.com/docs/cli/session-management/)
- [Gemini CLI Authentication](https://geminicli.com/docs/get-started/authentication/)
- [ADK A2A Integration](https://google.github.io/adk-docs/a2a/)
- [ADK A2A Introduction](https://google.github.io/adk-docs/a2a/intro/)
- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [Gemini Enterprise A2A Agent Registration](https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-a2a-agent)
- [ACP Integration with Gemini CLI (blog)](https://glaforge.dev/posts/2026/02/01/how-to-integrate-gemini-cli-with-intellij-idea-using-acp/)
