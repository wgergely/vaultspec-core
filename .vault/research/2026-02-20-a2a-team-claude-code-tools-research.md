---
tags:
  - '#research'
  - '#protocol'
date: '2026-02-20'
related:
  - '[[2026-02-15-cross-agent-bidirectional-communication]]'
  - '[[2026-02-07-a2a-protocol-reference]]'
---

# `a2a-team` research: Claude Code Team API & Two-Way Agent Communication

Investigation of the Claude Code team infrastructure tools (TaskCreate, TaskUpdate,
TaskList, TaskGet, SendMessage) and how they relate to building a formal multi-agent
team system backed by A2A protocol. Also covers gaps in the current vaultspec CLI and
TaskEngine that would need to be addressed.

## Findings

### 1. Claude Code Team API Surface

Claude Code provides a native team infrastructure with five core tool families. These
operate within a single Claude Code session where a "team lead" agent orchestrates
background "teammate" agents.

#### TaskCreate

Creates structured task entries visible to all team members. Fields:

- `subject` (required): brief imperative title (e.g., "Fix authentication bug")
- `description` (required): detailed requirements and context
- `activeForm`: present continuous form shown in spinner (e.g., "Fixing bug")
- `metadata`: arbitrary key-value pairs attached to the task

All tasks start in `pending` status with no owner. Task IDs are auto-assigned integers.

#### TaskUpdate

Updates task status, ownership, dependencies, and metadata:

- `taskId` (required): target task ID
- `status`: pending -> in_progress -> completed (or `deleted` for removal)
- `subject`, `description`, `activeForm`: mutable fields
- `owner`: assign to a specific agent by name
- `metadata`: merge additional key-value pairs (set key to null to delete)
- `addBlocks` / `addBlockedBy`: establish inter-task dependency chains

Key behaviors:

- Tasks progress through: `pending` -> `in_progress` -> `completed`
- `deleted` permanently removes a task
- Dependency tracking: blocked tasks cannot be started until blockers resolve

#### TaskList

Returns summary of all tasks (id, subject, status, owner, blockedBy). Used to find
available work, check progress, and identify blocked items.

#### TaskGet

Returns full task details by ID, including description, dependency graph (blocks,
blockedBy), and all metadata.

#### SendMessage

The primary inter-agent communication mechanism. Five message types:

| Type                     | Purpose                                | Key Fields                                      |
| ------------------------ | -------------------------------------- | ----------------------------------------------- |
| `message`                | Direct message to a specific teammate  | `recipient`, `content`, `summary`               |
| `broadcast`              | Message all teammates simultaneously   | `content`, `summary`                            |
| `shutdown_request`       | Ask a teammate to gracefully shut down | `recipient`, `content`                          |
| `shutdown_response`      | Teammate responds to shutdown request  | `request_id`, `approve`, `content`              |
| `plan_approval_response` | Approve/reject teammate's plan         | `request_id`, `recipient`, `approve`, `content` |

Critical constraint: plain text output from agents is NOT visible to other team
members. All inter-agent communication MUST go through SendMessage.

### 2. Agent Lifecycle

#### Spawning

The team lead creates background agents that run as separate Claude Code processes.
Each agent:

- Has a name (used for routing messages and task assignment)
- Receives custom instructions via its agent definition
- Operates in a configurable permission mode

#### Idle State

Agents persist in the background after completing assigned work. When idle, an agent
can:

- Call TaskList to find new unblocked, unowned tasks
- Be assigned new tasks via TaskUpdate (setting `owner`)
- Receive direct messages via SendMessage

The system sends automatic idle notifications when an agent stops actively using
tools, alerting the team lead that the agent is available.

#### Multi-Task Persistence

Agents persist across multiple task assignments within a session. The recommended
workflow:

1. Complete current task (mark `completed`)
1. Call TaskList to find next available work
1. Claim task via TaskUpdate (set `owner`, set `in_progress`)
1. Execute and repeat

#### Shutdown

Two shutdown mechanisms:

- **Graceful**: team lead sends `shutdown_request`; teammate responds with
  `shutdown_response` (approve=true exits, approve=false continues with reason)

- **Forced**: team lead can terminate background agents directly

### 3. Two-Way Communication

#### Message Delivery

Messages sent via SendMessage are automatically delivered to the recipient. Agents do
NOT need to poll or check an inbox. The delivery is push-based within the Claude Code
runtime.

#### Bidirectional Flow

- **Team lead -> Teammate**: Direct messages, task assignments, shutdown requests,
  plan approvals/rejections

- **Teammate -> Team lead**: Status updates, findings, questions, shutdown responses,
  plan approval requests

When a teammate sends a message back to the team lead, it appears inline in the team
lead's conversation with the user. The user sees all inter-agent communication.

#### Message Routing

- `message` type requires explicit `recipient` (agent name)
- `broadcast` sends to ALL teammates (expensive: N teammates = N deliveries)
- No built-in message queuing or persistence beyond the conversation context

### 4. Permission Modes

Claude Code agents can operate in several permission modes:

| Mode                | Description                                                   |
| ------------------- | ------------------------------------------------------------- |
| `default`           | Standard permission prompting                                 |
| `acceptEdits`       | Auto-approve file edits, prompt for other actions             |
| `bypassPermissions` | Skip all permission prompts (YOLO mode)                       |
| `plan`              | Plan-only mode; agent must get plan approved before executing |
| `dontAsk`           | Similar to bypass, agent proceeds without confirmation        |

For vaultspec, the most relevant modes are:

- `read-write` (maps to `bypassPermissions` or `acceptEdits`)
- `read-only` (restricts file writes to `.vault/` only)
- `plan` (plan mode with `plan_mode_required` flag for approval gating)

The plan mode creates an explicit approval checkpoint: the agent proposes a plan, the
team lead reviews via `plan_approval_response`, and only then can the agent proceed.

### 5. Current Vaultspec CLI Gap Analysis

#### What Exists

The current `subagent.py` CLI provides:

| Command     | Description                                                  |
| ----------- | ------------------------------------------------------------ |
| `run`       | Execute a single sub-agent via ACP (one-shot or interactive) |
| `serve`     | Start the MCP server (`vs-subagent-mcp`)                     |
| `a2a-serve` | Start an A2A HTTP server for a single agent                  |
| `list`      | List available agent definitions                             |

The MCP server (`server.py`) exposes 5 tools:

- `list_agents`: discover available agents
- `dispatch_agent`: run a sub-agent asynchronously (returns taskId)
- `get_task_status`: check task progress
- `cancel_task`: cancel a running task
- `get_locks`: view advisory file locks

#### What Is Missing for Team CLI

A formal team CLI would need these additional commands:

**Team Lifecycle:**

- `team create [--name NAME] [--members agent1,agent2,...]` - Create a named team
  with initial members. Must track team composition, assign roles (lead vs member),
  and establish a shared communication channel.

- `team dissolve [--name NAME]` - Gracefully shut down all team members, collect
  final status, and archive team state.

- `team status [--name NAME]` - Show team health: active members, their current
  tasks, idle status, message counts.

**Member Management:**

- `team add-member --agent NAME [--mode MODE] [--model MODEL]` - Spawn a new agent
  into an existing team. Must register it for message delivery and task assignment.

- `team remove-member --agent NAME [--graceful]` - Remove a member with optional
  graceful shutdown.

**Task Coordination:**

- `team assign --agent NAME --task "description"` - Assign a task to a specific team
  member. Creates a TaskCreate + TaskUpdate(owner) in one step.

- `team broadcast --message "text"` - Send a message to all team members.

**Communication:**

- `team message --to NAME --content "text"` - Send a direct message to a team
  member.

- `team log [--agent NAME] [--since TIME]` - View communication log, filtered by
  agent or time range.

#### Key Architectural Gaps

1. **No team registry**: The current system dispatches agents individually with no
   concept of a persistent team. Each `dispatch_agent` call is independent.

1. **No shared communication bus**: The MCP server has no message passing between
   agents. Agents communicate only via file artifacts in `.vault/`.

1. **No coordinated lifecycle**: No mechanism to spawn multiple agents that share
   context, coordinate work, and shut down together.

1. **No role differentiation**: All agents are peers. There is no team-lead / member
   distinction in the dispatch model.

### 6. TaskEngine State Management Gaps

#### Current Design

The `TaskEngine` in `task_engine.py` provides:

- **5-state lifecycle**: `WORKING -> INPUT_REQUIRED | COMPLETED | FAILED | CANCELLED`
- **Single-agent focus**: Each `SubagentTask` tracks one agent, one task
- **Advisory locks**: `LockManager` for workspace file coordination
- **TTL-based cleanup**: expired and stuck tasks are auto-evicted
- **Async wait/notify**: `wait_for_update()` for polling task status

#### What Needs to Change for Multi-Agent Teams

**New Concepts Needed:**

1. **Team Entity**: A first-class `Team` object that groups related tasks and agents:

   ```
   @dataclass
   class Team:
       team_id: str
       name: str
       lead: str
       members: dict[str, TeamMember]
       status: TeamStatus  # forming, active, dissolving, dissolved
       created_at: float
       shared_context: dict[str, Any]
   ```

1. **Team-Scoped Task Registry**: Tasks belong to a team, not just an agent. Need:

   - `team_id` field on `SubagentTask`
   - Query: "all tasks for team X"
   - Query: "unassigned tasks in team X"
   - Dependency resolution within team scope

1. **Member Status Tracking**: Beyond task status, need member-level state:

   ```
   class MemberStatus(StrEnum):
       SPAWNING = "spawning"
       IDLE = "idle"
       WORKING = "working"
       SHUTDOWN_REQUESTED = "shutdown_requested"
       TERMINATED = "terminated"
   ```

1. **Message Bus**: An in-process message queue for inter-agent communication:

   - Per-agent inbox (asyncio.Queue)
   - Broadcast support (fan-out to all member queues)
   - Message history for auditability
   - Integration with SessionLogger for persistent logging

1. **Coordinated Shutdown**: Team dissolution requires:

   - Send shutdown_request to all members
   - Wait for acknowledgments (with timeout)
   - Force-kill unresponsive members
   - Collect and archive final team state
   - Release all advisory locks

1. **A2A State Mapping**: The current A2A TaskState enum needs mapping to team states:

   ```
   A2A submitted  -> Team FORMING + member SPAWNING
   A2A working    -> Team ACTIVE + member WORKING
   A2A completed  -> Member IDLE (team persists)
   A2A canceled   -> Member TERMINATED (team may persist)
   A2A failed     -> Member error (team evaluates retry)
   ```

### 7. Bridge Architecture: Claude Code Teams \<-> A2A Protocol

The Claude Code team API and A2A protocol solve similar problems at different layers.
A bridge between them would enable:

| Claude Code Concept     | A2A Equivalent         | Bridge Behavior         |
| ----------------------- | ---------------------- | ----------------------- |
| TaskCreate              | A2A Task (submitted)   | Create A2A task, map ID |
| TaskUpdate(in_progress) | TaskState.working      | Update A2A state        |
| TaskUpdate(completed)   | TaskState.completed    | Send A2A result         |
| SendMessage(message)    | A2A Message/Part       | Wrap as A2A TextPart    |
| SendMessage(broadcast)  | Multi-target dispatch  | Fan-out to A2A agents   |
| shutdown_request        | A2A TaskState.canceled | Cancel A2A task         |

The bridge would live in `protocol/a2a/` and implement both:

- **Inbound**: A2A tasks -> Claude Code TaskCreate/SendMessage
- **Outbound**: Claude Code task updates -> A2A state transitions

### Summary

The Claude Code team API provides a mature, push-based communication model with
structured task tracking, dependency management, and graceful shutdown. The current
vaultspec infrastructure handles single-agent dispatch well via ACP/MCP but lacks the
multi-agent coordination primitives needed for formal teams.

Key gaps to fill:

- Team entity and lifecycle management
- Inter-agent message bus (beyond file-based coordination)
- Team-scoped task registry with dependency tracking
- Coordinated spawn/shutdown for agent groups
- A2A protocol bridge for cross-system agent teams
