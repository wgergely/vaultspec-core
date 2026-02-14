# Gemini CLI A2A/ACP Web Research Brief

**Date:** 2026-02-07
**Researcher:** web-researcher (sub-agent)
**Scope:** Gemini CLI protocol support (ACP, A2A, MCP) -- web-only research

---

## 1. The `--experimental-acp` Flag

**Confidence: HIGH**

The `--experimental-acp` flag tells Gemini CLI to start in **Agent Client Protocol** mode. Instead of launching the terminal UI, it communicates via **JSON-RPC 2.0 over stdin/stdout**, enabling headless operation as a subprocess of an editor/IDE.

- **Origin:** ACP was created by **Zed** in August 2025, with Gemini CLI as the first reference implementation.
- **Current status:** Still marked "experimental" in Gemini CLI v0.27.x.
- **Use case:** Editor integration (Zed, IntelliJ IDEA, Neovim, Marimo, etc.).
- **Launch:** The host IDE spawns `gemini --experimental-acp` as a subprocess and exchanges JSON-RPC messages over pipes.

### ACP Session Lifecycle (JSON-RPC Methods)

| Method | Direction | Purpose |
|---|---|---|
| `initialize` | Client -> Agent | Negotiate protocol version, exchange capabilities |
| `authenticate` | Client -> Agent | Validate credentials |
| `session/new` | Client -> Agent | Create conversation session |
| `session/prompt` | Client -> Agent | Send user messages |
| `session/update` | Agent -> Client (notification) | Stream message chunks, tool calls, plans, mode changes |
| `session/load` | Client -> Agent | Resume previous session (optional) |
| `session/set_mode` | Client -> Agent | Switch operational mode (optional) |
| `session/cancel` | Client -> Agent (notification) | Interrupt processing (optional) |
| `session/request_permission` | Agent -> Client | Request tool execution authorization |
| `fs/read_text_file`, `fs/write_text_file` | Agent -> Client | File system operations |
| `terminal/create`, `terminal/output`, `terminal/kill` | Agent -> Client | Terminal management |

**Source:** [ACP Protocol Overview](https://agentclientprotocol.com/protocol/overview), [Zed Blog](https://zed.dev/blog/bring-your-own-agent-to-zed)

---

## 2. A2A (Agent-to-Agent) Protocol in Gemini CLI

**Confidence: HIGH**

Gemini CLI has **separate, foundational A2A support** for agent-to-agent communication. This is distinct from ACP.

### Implementation Status

- **PR #3079** (by samdickson22) added initial A2A client support: `A2AClient`, types, `@a2a` tool. **Status: CLOSED (not merged).** Maintainers said A2A client work is "not prioritized" but remain open to server-side contributions.
- **Issue #3076** requested A2A communication; labeled `priority/p2` (important but deferrable).
- **RFC Discussion #7822** proposed standardizing on A2A for all Gemini CLI integrations moving forward.
- **Issue #10482** proposed integrating `@google/gemini-cli-a2a-server` into the CLI. **Status: CLOSED (not planned)** -- concerns about architecture complexity and attack surface.

### A2A Components in Gemini CLI Codebase

| Component | File | Purpose |
|---|---|---|
| A2AClient | `packages/core/src/a2a/client.ts` | JSON-RPC 2.0 communication with external agents |
| A2A Types | `packages/core/src/a2a/types.ts` | Protocol type definitions (tasks, messages, agent discovery) |
| @a2a Tool | `packages/core/src/tools/a2a-tool.ts` | Tool for model-driven agent communication |
| A2A Server | `@google/gemini-cli-a2a-server` npm package | Separate package for inbound A2A connections |

### A2A Task States (Protocol Spec)

| State | Description |
|---|---|
| `submitted` | Initial task submission |
| `working` | Task in progress |
| `input-required` | Agent needs additional information |
| `completed` | Processing complete |
| `canceled` | User canceled |
| `failed` | Processing failed |

**Source:** [A2A Protocol Spec](https://a2a-protocol.org/latest/specification/), [PR #3079](https://github.com/google-gemini/gemini-cli/pull/3079), [RFC #7822](https://github.com/google-gemini/gemini-cli/discussions/7822)

---

## 3. ACP vs A2A -- The Relationship

**Confidence: HIGH**

ACP and A2A are **distinct protocols solving different problems**:

| Aspect | ACP (Agent Client Protocol) | A2A (Agent-to-Agent Protocol) |
|---|---|---|
| **Purpose** | Agent <-> IDE/Editor communication | Agent <-> Agent communication |
| **Transport** | JSON-RPC 2.0 over stdio (subprocess) | JSON-RPC 2.0 over HTTP |
| **Trust model** | Trusted (local subprocess) | Potentially untrusted (distributed agents) |
| **Discovery** | Editor spawns agent directly | `.well-known/agent.json` Agent Cards |
| **State** | Session-based (editor lifecycle) | Task-based (submitted/working/completed) |
| **Governance** | Zed-initiated open standard | Linux Foundation (merged with IBM's ACP*) |
| **Gemini flag** | `--experimental-acp` | No CLI flag; uses `@a2a` tool or server |

> *Note: IBM's "ACP" (Agent Communication Protocol) merged with Google's A2A under Linux Foundation governance on Sep 1, 2025. This is a **different** ACP from Zed's "Agent Client Protocol". The naming collision is a source of confusion.

### Strategic Direction

The RFC #7822 proposes standardizing on A2A for all Gemini CLI integrations. Rationale:

1. A2A is "a robust, open standard" with a "stable and predictable foundation"
2. It is "built to be extended" with custom data
3. With Linux Foundation governance, A2A is "becoming an industry standard"

However, a community member raised concerns that the IDE extension proposal conflicts with A2A's core "Async First" and "Opaque Execution" principles, as IDE integration requires more synchronous, client-controlled interaction.

**Source:** [RFC #7822](https://github.com/google-gemini/gemini-cli/discussions/7822), [Protocol Comparison](https://heidloff.net/article/mcp-acp-a2a-agent-protocols/), [ACP Overview](https://blog.promptlayer.com/agent-client-protocol-the-lsp-for-ai-coding-agents/)

---

## 4. Configuration Requirements

**Confidence: HIGH**

### ACP Mode (Editor Integration)

**Flag:** `gemini --experimental-acp`

**Zed Configuration** (`settings.json`):

```json
{
  "agent_servers": {
    "gemini": {
      "command": "/path/to/gemini",
      "args": ["--experimental-acp"]
    }
  }
}
```

**JetBrains Configuration** (`~/.jetbrains/acp.json`):

```json
{
  "agent_servers": {
    "Gemini CLI": {
      "command": "/path/to/gemini",
      "args": ["--experimental-acp"],
      "use_idea_mcp": true,
      "use_custom_mcp": true
    }
  }
}
```

### MCP Server Configuration (`~/.gemini/settings.json`)

```json
{
  "mcpServers": {
    "server-name": {
      "command": "...",
      "args": ["..."]
    }
  }
}
```

### A2A Server

- No specific CLI flag to enable A2A server mode (as of v0.27).
- The `@google/gemini-cli-a2a-server` npm package provides an A2A server that can be started on a specified port.
- v0.28-preview adds: A2A auth config types, pluggable auth provider infrastructure, A2A admin settings.
- No evidence of an `experimental.enableAgents` setting specifically for A2A.

**Source:** [Gemini CLI Configuration](https://geminicli.com/docs/get-started/configuration/), [IntelliJ ACP Guide](https://glaforge.dev/posts/2026/02/01/how-to-integrate-gemini-cli-with-intellij-idea-using-acp/)

---

## 5. MCP + ACP/A2A Interaction

**Confidence: HIGH**

### MCP in ACP Mode

When Gemini CLI runs in `--experimental-acp` mode, **MCP servers remain fully available**. The editor can:

- Configure `use_idea_mcp: true` to grant Gemini access to the IDE's built-in MCP server
- Configure `use_custom_mcp: true` to enable custom MCP servers configured in the IDE
- Gemini's own `~/.gemini/settings.json` `mcpServers` also remain active

In ACP mode, Gemini CLI can "interact with your code, run terminal commands, and use Model Context Protocol (MCP) servers right from the AI Assistant chat window."

### MCP + A2A

- MCP and A2A are complementary protocols (MCP for tool invocation, A2A for agent-to-agent delegation).
- In Gemini CLI, both can coexist: MCP provides tools, A2A provides agent delegation.
- The `@a2a` tool would be exposed alongside MCP tools in the tool registry.

**Source:** [MCP Servers with Gemini CLI](https://geminicli.com/docs/tools/mcp-server/), [IntelliJ ACP Guide](https://glaforge.dev/posts/2026/02/01/how-to-integrate-gemini-cli-with-intellij-idea-using-acp/)

---

## 6. Recent Changes Timeline

**Confidence: HIGH**

| Date | Event |
|---|---|
| **Aug 2025** | Zed launches ACP with Gemini CLI as first reference implementation |
| **Sep 2025** | IBM's ACP merges with Google's A2A under Linux Foundation |
| **Jul 2025** | Issue #3076: A2A Communication request opened |
| **Jul 2025** | PR #3079: A2A client support (closed, not merged) |
| **Oct 2025** | RFC #7822: Gemini CLI A2A Development-Tool Extension proposed |
| **Jan 2026** | Issue #10482: A2A Server integration closed (not planned) |
| **Feb 3, 2026** | **v0.27.0 released**: Event-driven architecture, agent skills stabilized, sub-agent registry, MCP server enable/disable, AgentConfigDialog |
| **Feb 3, 2026** | **v0.28.0-preview.0**: A2A auth config types, pluggable A2A auth provider, ACP session resume, dynamic policy for subagents, ACP error parsing refactor |

### v0.27.0 Agent-Related Features

- Agent Skills promoted from experimental to stable
- Sub-agents migrated to event-driven scheduler
- Sub-agents use JSON schema for input
- AgentRegistry for discovering/tracking sub-agents
- MCP server prefix enforcement in agent definitions
- First-run experience for project-level sub-agents

### v0.28.0-preview.0 Protocol Features

- Pluggable auth provider infrastructure for A2A
- A2A admin settings configuration
- A2A auth config types
- ACP session resume support
- Dynamic policy registration for subagents

**Source:** [v0.27.0 Changelog](https://geminicli.com/docs/changelogs/latest/), [v0.28.0-preview](https://geminicli.com/docs/changelogs/preview/), [GitHub Releases](https://github.com/google-gemini/gemini-cli/releases)

---

## 7. Agent Card / `.well-known/agent.json`

**Confidence: MEDIUM-HIGH**

### A2A Agent Cards

The A2A protocol uses **Agent Cards** for service discovery. These are JSON metadata documents published at `/.well-known/agent.json` on an agent's host server.

**Agent Card fields include:**

- `name`: Agent name
- `description`: What the agent does
- `url`: Service endpoint
- `version`: Agent version
- `capabilities`: Supported features
- `defaultInputModes` / `defaultOutputModes`: MIME types
- `skills`: Array of skill descriptions with examples

### Gemini CLI Support

- **Client-side (consuming):** The `A2AClient` in `packages/core/src/a2a/client.ts` discovers agents by fetching `.well-known/agent.json` from the target host.
- **Server-side (publishing):** The `@google/gemini-cli-a2a-server` package provides an A2A server that serves `/.well-known/agent.json` and handles A2A JSON-RPC requests.
- **Status:** Client-side discovery was in PR #3079 (closed/not merged). Server-side exists as a separate npm package but is not integrated into the main CLI binary.

**Source:** [PR #3079](https://github.com/google-gemini/gemini-cli/pull/3079), [A2A Protocol Spec](https://a2a-protocol.org/latest/specification/), [@google/gemini-cli-a2a-server](https://www.npmjs.com/package/@google/gemini-cli-a2a-server)

---

## Summary: Protocol Landscape for Gemini CLI

```
                    +------------------+
                    |    Gemini CLI     |
                    +------------------+
                    |                  |
            ACP (stable-ish)    A2A (experimental)
            --experimental-acp  @a2a tool + server pkg
                    |                  |
            +-------+------+    +-----+------+
            | IDE/Editor   |    | Other      |
            | (Zed, IDEA,  |    | Agents     |
            |  Neovim...)  |    | (via HTTP) |
            +--------------+    +------------+
                    |
            +-------+------+
            | MCP Servers  |
            | (tools,      |
            |  resources)  |
            +--------------+
```

### Key Takeaways

1. **ACP is the stable path** for IDE/editor integration. `--experimental-acp` works today with Zed, JetBrains, Neovim, etc.
2. **A2A is emerging but not yet integrated** into the main CLI binary. The client-side PR was closed; the server package exists separately.
3. **MCP coexists with both** -- MCP tools are available in ACP mode and can coexist with A2A.
4. **The naming collision is real**: IBM's "ACP" (Agent Communication Protocol) merged into A2A. Zed's "ACP" (Agent Client Protocol) is a separate protocol. Both are commonly called "ACP."
5. **Strategic direction** is toward A2A for agent-to-agent, ACP for client-agent.
6. **v0.28 preview** adds A2A auth infrastructure, suggesting deeper A2A integration is coming.

---

## Citations

- [Zed Blog: Bring Your Own Agent](https://zed.dev/blog/bring-your-own-agent-to-zed)
- [ACP Protocol Overview](https://agentclientprotocol.com/protocol/overview)
- [Gemini CLI ACP Agent on Zed](https://zed.dev/acp/agent/gemini-cli)
- [IntelliJ ACP Integration Guide](https://glaforge.dev/posts/2026/02/01/how-to-integrate-gemini-cli-with-intellij-idea-using-acp/)
- [PR #3079: Adding A2A Support](https://github.com/google-gemini/gemini-cli/pull/3079)
- [Issue #3076: A2A Communication](https://github.com/google-gemini/gemini-cli/issues/3076)
- [RFC #7822: A2A Development-Tool Extension](https://github.com/google-gemini/gemini-cli/discussions/7822)
- [Issue #10482: A2A Server Integration](https://github.com/google-gemini/gemini-cli/issues/10482)
- [Gemini CLI v0.27.0 Changelog](https://geminicli.com/docs/changelogs/latest/)
- [Gemini CLI v0.28.0-preview Changelog](https://geminicli.com/docs/changelogs/preview/)
- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [MCP Servers with Gemini CLI](https://geminicli.com/docs/tools/mcp-server/)
- [Gemini CLI Configuration](https://geminicli.com/docs/get-started/configuration/)
- [@google/gemini-cli-a2a-server (npm)](https://www.npmjs.com/package/@google/gemini-cli-a2a-server)
- [Protocol Comparison: MCP, ACP, A2A](https://heidloff.net/article/mcp-acp-a2a-agent-protocols/)
- [ACP Intro by Block/Goose](https://block.github.io/goose/blog/2025/10/24/intro-to-agent-client-protocol-acp/)
- [PromptLayer: ACP as LSP for AI Agents](https://blog.promptlayer.com/agent-client-protocol-the-lsp-for-ai-coding-agents/)
- [A2A Task Lifecycle](https://a2a-protocol.org/latest/topics/life-of-a-task/)
