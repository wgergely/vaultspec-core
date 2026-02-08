# Multi-Agent Orchestration Patterns -- Survey

**Date:** 2026-02-07
**Source:** Research agent -- multi-agent orchestration patterns
**Scope:** Cross-framework survey of agent team/delegation architectures

---

## 1. Protocol Layer Summary

| Protocol | Layer | Purpose | Status |
|---|---|---|---|
| **MCP** | Tool | Connect models to tools/resources | De facto standard |
| **A2A** | Agent | Peer agent communication | Linux Foundation standard |
| **ACP** (IBM) | Agent | Structured intra-cluster messaging | **Merged into A2A** |
| **ACP** (Zed) | Client | Editor-to-agent communication | Production, independent |

**Key insight**: MCP and A2A are complementary. MCP connects an agent to its tools. A2A connects agents to each other.

---

## 2. Claude Code Agent Teams

Released with Opus 4.6 (February 2026).

### Architecture

```
      Team Lead (Coordination)
       /         |         \
  Teammate A  Teammate B  Teammate C
       \         |         /
    Shared Task List + Direct DMs
```

### Core Tools

- `Teammate(spawnTeam)` / `Teammate(cleanup)` -- team lifecycle
- `SendMessage(message/broadcast/shutdown_request)` -- communication
- `TaskCreate/TaskUpdate/TaskList` -- shared task list

### Communication Model

Direct messaging via `SendMessage`. Async delivery with queueing. Broadcast available but expensive.

### Delegation Pattern

Team lead creates tasks via `TaskCreate`, assigns with `TaskUpdate(owner)`. Task states: `pending` -> `in_progress` -> `completed`. Dependencies via `blockedBy`.

### Shared State

- Task list at `~/.claude/tasks/{team-name}/`
- Team config at `~/.claude/teams/{team-name}/config.json`
- No shared context window -- only messages and task list

### Limitations

- No session resumption for teammates
- Multiple teammates editing same file causes conflicts
- Experimental status

---

## 3. OpenAI Agents SDK

### Architecture

```
Triage Agent -> handoff -> Specialist A
                       \-> Specialist B
```

### Communication Model

Function-based handoffs. LLM sees handoffs as callable tools (`transfer_to_{agent_name}`). Full conversation history passes with each handoff.

### Key Characteristics

- **Stateless pass-through** -- no persistent state between calls
- **Linear chain** -- no "reporting back", agent that has control owns the conversation
- **No parallelism** -- single thread of execution
- **No shared state** -- context travels with conversation

---

## 4. LangGraph Supervisor Pattern

### Architecture

```
Supervisor (LLM node) -> handoff_tool -> Worker A -> return to supervisor
                                      -> Worker B -> return to supervisor
```

### Communication Model

Graph-based routing. Supervisor calls `create_handoff_tool` to delegate. Workers return via `add_handoff_back_messages`.

### Key Characteristics

- **Stateful graph** with checkpointing (`InMemorySaver`)
- **Supervisor re-routes** based on worker results
- **Shared memory** via `InMemoryStore` key-value storage

---

## 5. Microsoft Magentic-One (AutoGen)

### Architecture

```
Orchestrator (Outer Loop: Task Ledger)
     |
  Inner Loop (Progress Ledger)
     |
  WebSurfer / FileSurfer / Coder / Terminal
```

### Dual-Loop Pattern

- **Outer Loop**: Task Ledger with facts, guesses, plan
- **Inner Loop**: Progress Ledger for self-reflection -- is progress being made? Which agent next?
- If progress stalls, re-enters outer loop and replans

### Semantic Kernel Orchestration Patterns

Five patterns: Sequential, Concurrent, Handoff, GroupChat, Magentic.

---

## 6. CrewAI

### Communication Model

Agents with `allow_delegation=True` get two built-in tools:

1. **Delegate Work** -- assign subtask to teammate
2. **Ask Question** -- query teammate for information

### Key Characteristics

- `allowed_agents` parameter for controlled delegation hierarchies
- Task context chain: `context=[other_task]` for dependency injection
- Processes: `sequential` or `hierarchical`

---

## 7. Google ADK + A2A

### Architecture

```
Root Agent -> Local sub-agent A
           -> Local sub-agent B
           -> RemoteA2aAgent (external, via HTTP/A2A)
```

### Key Pattern

```python
remote_agent = RemoteA2aAgent(
    name="approval_service",
    agent_card="https://approvals.example.com/.well-known/agent.json",
)
root_agent = Agent(
    sub_agents=[local_agent, remote_agent],  # Both local and remote
)
a2a_app = to_a2a(root_agent)  # Wrap as A2A server
```

Remote agents appear identical to local sub-agents from the root's perspective.

---

## 8. Comparative Matrix

| Dimension | Claude Teams | OpenAI SDK | LangGraph | Magentic-One | CrewAI | ADK+A2A |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Topology | Star + P2P | Chain | Star | Star | Star | Tree + Remote |
| Peer DMs | Yes | No | No | No | Yes | No |
| Shared Tasks | Yes | No | Graph state | Ledgers | Task context | A2A tasks |
| Parallel | Yes | No | Via nodes | One-at-a-time | Sequential/Hierarchical | Via sub-agents |
| Cross-process | Yes | No | No | No | No | Yes (HTTP) |
| Cross-network | No | No | No | No | No | Yes (A2A) |
| Protocol Standard | Proprietary | Proprietary | Proprietary | Proprietary | Proprietary | A2A (open) |

---

## 9. Five Dominant Patterns

1. **Supervisor/Star** (LangGraph, CrewAI, Magentic-One) -- central coordinator, bottleneck
2. **Handoff Chain** (OpenAI) -- linear, stateless, no parallelism
3. **Team with Peer Communication** (Claude Code) -- most flexible, most complex
4. **Dual-Loop Planning** (Magentic-One) -- most sophisticated, heaviest overhead
5. **Protocol-Mediated Federation** (ADK + A2A) -- only cross-boundary approach

---

## 10. Key Takeaways

1. MCP + A2A is the emerging standard stack
2. Dual-loop replanning (Magentic-One) is most robust for complex tasks
3. Claude Code Agent Teams is most practical for software engineering
4. Google ADK + A2A is the only cross-boundary solution
5. Industry converging on supervisor/orchestrator pattern

---

## Sources

- <https://code.claude.com/docs/en/agent-teams>
- <https://github.com/openai/openai-agents-python>
- <https://github.com/langchain-ai/langgraph-supervisor-py>
- <https://microsoft.github.io/autogen/stable/>
- <https://docs.crewai.com/en/concepts/collaboration>
- <https://google.github.io/adk-docs/a2a/>
- <https://lfaidata.foundation/communityblog/2025/08/29/acp-joins-forces-with-a2a/>
