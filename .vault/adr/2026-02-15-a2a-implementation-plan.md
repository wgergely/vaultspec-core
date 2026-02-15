---
title: "A2A Implementation Plan: Gemini-Claude Bidirectional Agent Communication"
status: Proposed
date: "2026-02-15"
authors: [team-lead, a2a-sdk-researcher, gemini-researcher, claude-researcher, test-architect, build-engineer]
tags: [adr, a2a, implementation, gemini, claude, bidirectional, test]
related:
  - "[[2026-02-15-cross-agent-bidirectional-communication]]"
  - "[[2026-02-15-subagent-architecture-refactor]]"
  - "[[2026-02-07-a2a-protocol-reference]]"
---

## ADR: A2A Implementation Plan — Gemini-Claude Bidirectional Communication

## Status

**Proposed** — Research complete, implementation pending approval.

## Context

The [cross-agent bidirectional ADR](2026-02-15-cross-agent-bidirectional-communication.md)
established 8/10 feasibility for Gemini-Claude A2A communication. This ADR is the
concrete implementation plan based on deep research into:

- `a2a-sdk` v0.3.22 source code (AgentExecutor, EventQueue, TaskUpdater, A2AStarletteApplication)
- Google ADK v1.25.0 (A2A support, Claude model integration)
- Claude Agent SDK (ClaudeSDKClient, streaming, MCP injection)
- Existing vaultspec ACP bridge architecture (claude_bridge.py, 1053 lines)
- Test infrastructure patterns (protocol/acp/tests/, subagent_server/tests/)

### Baseline Validated

ACP bumped from 0.8.0 → 0.8.1 (new `session/set_config_option` method, no breaking
changes). **All 341 tests pass** across protocol, orchestration, and subagent_server
suites.

---

## Architecture

### Target Protocol Stack

```
┌──────────────────────────────────────────────────────────┐
│  A2A Layer (NEW)                                         │
│  agent↔agent HTTP/JSON-RPC — a2a-sdk v0.3.22             │
│                                                          │
│  ┌─────────────────────┐    ┌─────────────────────────┐  │
│  │ ClaudeA2AExecutor   │    │ GeminiA2AExecutor       │  │
│  │ (AgentExecutor)     │    │ (AgentExecutor)         │  │
│  │                     │    │                         │  │
│  │ claude-agent-sdk    │    │ gemini CLI ACP or       │  │
│  │ + sandbox callback  │    │ direct API + sandbox    │  │
│  └────────┬────────────┘    └────────┬────────────────┘  │
│           │                          │                    │
│  ┌────────▼──────────────────────────▼────────────────┐  │
│  │ DefaultRequestHandler + InMemoryTaskStore          │  │
│  │ A2AStarletteApplication (HTTP server)              │  │
│  │ Agent Cards at /.well-known/agent.json             │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│  ACP Layer (EXISTING — unchanged)                        │
│  orchestrator↔agent stdio/JSON-RPC — agent-client-protocol v0.8.1 │
│                                                          │
│  run_subagent() → spawn_agent_process() → SubagentClient │
│  ClaudeACPBridge (claude_bridge.py)                      │
│  GeminiProvider (--experimental-acp)                     │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│  MCP Layer (EXISTING — unchanged)                        │
│  agent↔tool stdio — mcp v1.26.0                         │
│                                                          │
│  vs-subagent-mcp (5 tools)                               │
│  RAG MCP (planned: vault_search, vault_get, etc.)        │
└──────────────────────────────────────────────────────────┘
```

### Key Decision: Use `a2a-sdk` Directly (NOT Google ADK)

**Rationale**: Google ADK (`google-adk` v1.25.0) pulls ~30 transitive
`google-cloud-*` packages as **core** dependencies (BigQuery, Spanner, PubSub,
etc.). We need none of this. The `a2a-sdk` provides all necessary abstractions:
`AgentExecutor`, `DefaultRequestHandler`, `A2AStarletteApplication`,
`InMemoryTaskStore`, `TaskUpdater`, full Pydantic types.

Dependencies already satisfied: `starlette>=0.27.0`, `httpx>=0.27.0`,
`uvicorn>=0.23.0`, `pydantic>=2.0.0` — all in pyproject.toml today.

Only addition needed: `pip install "a2a-sdk[http-server]"` for `sse-starlette`.

---

## File Plan

### New Files

```
.vaultspec/lib/src/protocol/a2a/
├── __init__.py                          # Package init
├── executors/
│   ├── __init__.py
│   ├── base.py                          # Base executor with shared sandboxing
│   ├── claude_executor.py               # ClaudeA2AExecutor (AgentExecutor)
│   └── gemini_executor.py               # GeminiA2AExecutor (AgentExecutor)
├── agent_card.py                        # Agent Card generation from agent defs
├── server.py                            # A2A HTTP server setup + uvicorn runner
├── state_map.py                         # TaskEngine ↔ A2A TaskState mapping
└── tests/
    ├── __init__.py
    ├── conftest.py                      # A2A test fixtures
    ├── test_unit_a2a.py                 # Layer 1: unit tests (no network)
    ├── test_integration_a2a.py          # Layer 2: in-process HTTP (no LLM)
    └── test_e2e_a2a.py                  # Layer 3: real LLM (API keys)
```

### Modified Files

```
pyproject.toml                           # Add sse-starlette dep, a2a markers
.vaultspec/scripts/subagent.py           # Add 'a2a-serve' subcommand
```

### Unchanged Files

```
protocol/acp/claude_bridge.py            # Keep as-is (ACP path)
protocol/acp/client.py                   # Keep as-is (SubagentClient)
protocol/providers/claude.py             # Keep as-is (ClaudeProvider)
protocol/providers/gemini.py             # Keep as-is (GeminiProvider)
orchestration/subagent.py                # Keep as-is (run_subagent)
orchestration/task_engine.py             # Keep as-is (TaskEngine)
subagent_server/server.py                # Keep as-is (MCP server)
```

---

## Code Skeletons

### 1. State Mapping (`state_map.py`)

```python
"""Bidirectional mapping between TaskEngine states and A2A TaskState."""
from a2a.types import TaskState

# Vaultspec TaskEngine → A2A
VAULTSPEC_TO_A2A = {
    "pending":          TaskState.submitted,
    "working":          TaskState.working,
    "input_required":   TaskState.input_required,
    "completed":        TaskState.completed,
    "failed":           TaskState.failed,
    "cancelled":        TaskState.canceled,      # British → American
}

# A2A → Vaultspec TaskEngine
A2A_TO_VAULTSPEC = {
    TaskState.submitted:      "pending",
    TaskState.working:        "working",
    TaskState.input_required: "input_required",
    TaskState.completed:      "completed",
    TaskState.failed:         "failed",
    TaskState.canceled:       "cancelled",
    TaskState.rejected:       "failed",          # Map rejection to failure
    TaskState.auth_required:  "input_required",  # Auth = needs input
    TaskState.unknown:        "failed",          # Unknown = failure
}
```

### 2. Agent Card Generator (`agent_card.py`)

```python
"""Generate A2A Agent Cards from vaultspec agent definition files."""
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

def agent_card_from_definition(
    agent_name: str,
    agent_meta: dict,
    host: str = "localhost",
    port: int = 10010,
) -> AgentCard:
    """Convert a vaultspec agent definition to an A2A Agent Card."""
    return AgentCard(
        name=agent_name,
        description=agent_meta.get("description", f"Vaultspec agent: {agent_name}"),
        url=f"http://{host}:{port}/",
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(
            streaming=True,
            push_notifications=False,
            state_transition_history=True,
        ),
        skills=[
            AgentSkill(
                id=agent_name,
                name=agent_meta.get("name", agent_name),
                description=agent_meta.get("description", ""),
                tags=agent_meta.get("tags", []),
            ),
        ],
    )
```

### 3. Claude A2A Executor (`claude_executor.py`)

```python
"""A2A AgentExecutor wrapping claude-agent-sdk.

Bridges A2A task model → Claude SDK streaming conversation model.
Reuses sandboxing logic from protocol/acp/claude_bridge.py.
"""
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TaskState, TextPart
from claude_agent_sdk import (
    AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient,
    ResultMessage, TextBlock, ToolUseBlock,
)

class ClaudeA2AExecutor(AgentExecutor):
    def __init__(self, *, model, root_dir, mode="read-only",
                 mcp_servers=None, system_prompt=None):
        self._model = model
        self._root_dir = root_dir
        self._mode = mode
        self._mcp_servers = mcp_servers or {}
        self._system_prompt = system_prompt
        self._active_clients: dict[str, ClaudeSDKClient] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        task_id = context.task_id
        updater = TaskUpdater(event_queue, task_id, context.context_id)
        prompt = context.get_user_input()

        await updater.start_work()

        sdk_client = ClaudeSDKClient(ClaudeAgentOptions(
            model=self._model, cwd=self._root_dir,
            mcp_servers=self._mcp_servers,
            can_use_tool=_make_sandbox(self._mode, self._root_dir),
            permission_mode="bypassPermissions",
            system_prompt=self._system_prompt,
        ))
        self._active_clients[task_id] = sdk_client

        try:
            await sdk_client.connect()
            await sdk_client.query(prompt)
            collected = []

            async for msg in sdk_client.receive_messages():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            collected.append(block.text)
                elif isinstance(msg, ResultMessage):
                    text = "".join(collected) or msg.result or ""
                    if text:
                        await updater.add_artifact(
                            parts=[Part(root=TextPart(text=text))],
                            name="response",
                        )
                    if msg.is_error:
                        await updater.failed(message=updater.new_agent_message(
                            parts=[Part(root=TextPart(text=text))]))
                    else:
                        await updater.complete(message=updater.new_agent_message(
                            parts=[Part(root=TextPart(text=text))]))
                    break
        except Exception as e:
            await updater.failed(message=updater.new_agent_message(
                parts=[Part(root=TextPart(text=str(e)))]))
        finally:
            await sdk_client.disconnect()
            self._active_clients.pop(task_id, None)

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        task_id = context.task_id
        updater = TaskUpdater(event_queue, task_id, context.context_id)
        client = self._active_clients.get(task_id)
        if client:
            await client.interrupt()
            await client.disconnect()
        await updater.cancel()
```

### 4. Gemini A2A Executor (`gemini_executor.py`)

```python
"""A2A AgentExecutor wrapping Gemini via existing ACP subprocess.

Uses run_subagent() to delegate to GeminiProvider's ACP flow,
mapping results back to A2A events.
"""
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart

from orchestration.subagent import run_subagent

class GeminiA2AExecutor(AgentExecutor):
    def __init__(self, *, root_dir, model="gemini-2.5-flash",
                 agent_name="researcher"):
        self._root_dir = root_dir
        self._model = model
        self._agent_name = agent_name

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        task_id = context.task_id
        updater = TaskUpdater(event_queue, task_id, context.context_id)
        prompt = context.get_user_input()

        await updater.start_work()

        try:
            result = await run_subagent(
                agent_name=self._agent_name,
                root_dir=self._root_dir,
                initial_task=prompt,
                model_override=self._model,
            )
            text = result.response_text or ""
            if text:
                await updater.add_artifact(
                    parts=[Part(root=TextPart(text=text))],
                    name="response",
                )
            await updater.complete(message=updater.new_agent_message(
                parts=[Part(root=TextPart(text=text or "Done"))]))
        except Exception as e:
            await updater.failed(message=updater.new_agent_message(
                parts=[Part(root=TextPart(text=str(e)))]))

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()
```

### 5. A2A Server (`server.py`)

```python
"""A2A HTTP server for vaultspec agents.

Usage:
    python -m protocol.a2a.server --executor claude --port 10010
    python -m protocol.a2a.server --executor gemini --port 10011
"""
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

def create_app(executor, agent_card):
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler,
    )
    return app.build()
```

### 6. Test Fixtures (`tests/conftest.py`)

```python
"""Fixtures for A2A protocol tests."""
import pytest
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater, InMemoryTaskStore
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.apps import A2AStarletteApplication
from a2a.types import AgentCard, AgentSkill, AgentCapabilities, Part, TextPart
import httpx

class EchoExecutor(AgentExecutor):
    """Echoes input back as completed task."""
    async def execute(self, context, event_queue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        text = context.get_user_input()
        await updater.start_work()
        await updater.complete(message=updater.new_agent_message(
            parts=[Part(root=TextPart(text=f"Echo: {text}"))]))
    async def cancel(self, context, event_queue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()

class PrefixExecutor(AgentExecutor):
    """Prepends a prefix to input text."""
    def __init__(self, prefix: str):
        self._prefix = prefix
    async def execute(self, context, event_queue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        text = context.get_user_input()
        await updater.start_work()
        await updater.complete(message=updater.new_agent_message(
            parts=[Part(root=TextPart(text=f"{self._prefix}{text}"))]))
    async def cancel(self, context, event_queue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()

@pytest.fixture
def echo_executor():
    return EchoExecutor()

@pytest.fixture
def mock_claude_executor():
    return PrefixExecutor("[Claude] ")

@pytest.fixture
def mock_gemini_executor():
    return PrefixExecutor("[Gemini] ")

def _make_card(name, port):
    return AgentCard(
        name=name, url=f"http://localhost:{port}/", version="0.1.0",
        description=f"Test {name} agent",
        default_input_modes=["text"], default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[AgentSkill(id="test", name="Test", description="Test skill")],
    )

@pytest.fixture
def a2a_server_factory():
    """Factory: (executor, name, port) -> (app, card, httpx_client)"""
    async def _factory(executor, name="test", port=10099):
        card = _make_card(name, port)
        handler = DefaultRequestHandler(executor, InMemoryTaskStore())
        app = A2AStarletteApplication(card, handler).build()
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app))
        return app, card, client
    return _factory
```

---

## Test Plan

### Layer 1 — Unit Tests (`test_unit_a2a.py`)

No network, no LLM. Marker: `@pytest.mark.unit`

| Test | Validates |
|------|-----------|
| `test_state_mapping_vaultspec_to_a2a` | All 6 states map correctly |
| `test_state_mapping_a2a_to_vaultspec` | All 9 A2A states map (including fallbacks) |
| `test_agent_card_from_definition` | Agent Card has required fields |
| `test_agent_card_skills_from_meta` | Skills populated from agent metadata |
| `test_echo_executor_returns_text` | EchoExecutor completes with echoed input |
| `test_prefix_executor_prepends` | PrefixExecutor prepends prefix |
| `test_message_serialization_roundtrip` | Message → dict → Message |

### Layer 2 — Integration Tests (`test_integration_a2a.py`)

In-process HTTP via `httpx.ASGITransport`. No real TCP. Marker: `@pytest.mark.integration, @pytest.mark.a2a`

| Test | Validates |
|------|-----------|
| `test_agent_card_served` | GET `/.well-known/agent.json` returns valid card |
| `test_send_message_returns_completed_task` | POST `/` with message/send → completed Task |
| `test_echo_round_trip_integrity` | Input text survives full A2A encode→send→process→respond→decode |
| `test_two_agents_bidirectional` | Agent A sends to B, B sends to A, both complete |
| `test_task_state_transitions` | Task moves submitted→working→completed |
| `test_cancel_running_task` | tasks/cancel transitions to canceled |

### Layer 3 — E2E Tests (`test_e2e_a2a.py`)

Real LLM, requires API keys. Marker: `@pytest.mark.e2e, @pytest.mark.a2a`

| Test | Validates |
|------|-----------|
| `test_claude_a2a_responds` | Real Claude processes A2A message |
| `test_gemini_a2a_responds` | Real Gemini processes A2A message |
| **GOLD: `test_claude_asks_gemini`** | Claude sends task to Gemini via A2A, gets result back |
| **GOLD: `test_gemini_asks_claude`** | Gemini sends task to Claude via A2A, gets result back |

---

## Dependency Changes

```toml
# pyproject.toml additions
dependencies = [
    # existing...
    "sse-starlette>=1.0.0",     # Required for A2A streaming (SSE responses)
]

[tool.pytest.ini_options]
markers = [
    # existing...
    "a2a: A2A protocol interoperability tests",
    "e2e: end-to-end tests requiring real LLM API keys",
]
```

No new heavy dependencies. `sse-starlette` is the only addition (lightweight,
pure-Python SSE for Starlette).

---

## Implementation Phases

### Phase 1: Foundation (state_map + agent_card + test fixtures)

1. Create `protocol/a2a/` package structure
2. Implement `state_map.py` with bidirectional mapping
3. Implement `agent_card.py` for card generation
4. Create test fixtures (`EchoExecutor`, `PrefixExecutor`, `a2a_server_factory`)
5. Write Layer 1 unit tests
6. **Verify**: `pytest protocol/a2a/tests/test_unit_a2a.py -v` passes

### Phase 2: A2A Server + Integration Tests

1. Implement `server.py` (create_app wiring)
2. Write Layer 2 integration tests with in-process ASGI transport
3. Add `sse-starlette` to pyproject.toml
4. **Verify**: `pytest protocol/a2a/tests/test_integration_a2a.py -v` passes

### Phase 3: ClaudeA2AExecutor

1. Implement `executors/claude_executor.py`
2. Reuse sandbox logic from `claude_bridge.py` (extract to shared util)
3. Unit test with mock SDK client
4. Integration test with mock SDK (no API key)
5. E2E test with real Claude (requires ANTHROPIC_API_KEY)

### Phase 4: GeminiA2AExecutor

1. Implement `executors/gemini_executor.py`
2. Delegate to existing `run_subagent()` + `GeminiProvider`
3. Unit test with mock subagent
4. E2E test with real Gemini (requires Gemini CLI)

### Phase 5: Gold Standard Bidirectional Tests

1. Wire up two A2A servers (Claude + Gemini)
2. Implement gold standard test: Claude asks Gemini via A2A
3. Implement reverse: Gemini asks Claude via A2A
4. Measure and log round-trip latency
5. Add `a2a-serve` subcommand to `subagent.py`

### Phase 6: Gemini CLI A2A Discovery (Optional)

1. Generate `.gemini/agents/*.md` config files with agent_card_url
2. Enable Gemini CLI to discover and delegate to vaultspec A2A agents
3. Configure via `settings.json`: `{"experimental": {"enableAgents": true}}`

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| A2A spec breaks before 1.0 | Medium | Medium | Thin wrapper isolates A2A from core |
| `sse-starlette` compatibility | Low | Low | Well-maintained, simple package |
| Claude SDK API changes | Medium | Medium | Executor is the only touch point |
| Port conflicts in CI | Low | Low | ASGI transport avoids real TCP |
| LLM latency in E2E tests | Low | High | Generous timeouts, explicit markers |
| No reference impl to copy | Medium | N/A | We have complete code skeletons |

## Fallback

If A2A wrapping proves too complex or the SDK is too unstable:

- **Short-term**: Keep using MCP dispatch pattern (Agent A uses `dispatch_agent`
  tool via `vs-subagent-mcp` to spawn Agent B, polls `get_task_status`). This
  already works today for one-way communication.
- **Medium-term**: Add `send_message_to_task` MCP tool for injecting messages
  into running tasks via `TaskEngine.input_required`.

---

## References

- [a2a-sdk v0.3.22](https://pypi.org/project/a2a-sdk/) — `AgentExecutor`, `TaskUpdater`, `A2AStarletteApplication`
- [agent-client-protocol v0.8.1](https://pypi.org/project/agent-client-protocol/) — Zed ACP (unchanged)
- [claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/) — `ClaudeSDKClient`, `ClaudeAgentOptions`
- [Google ADK](https://pypi.org/project/google-adk/) — NOT recommended (heavyweight deps)
- [A2A Protocol Spec v0.3.0](https://a2a-protocol.org/latest/)
- [Cross-Agent Bidirectional ADR](2026-02-15-cross-agent-bidirectional-communication.md)
