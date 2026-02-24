---
tags:
  - "#research"
  - "#task-tool-dispatch"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-ecosystem-factoring-research]]"
  - "[[2026-02-22-mcp-consolidation-research]]"
---
# task-tool-dispatch research: unifying subagent dispatch via claude code task tool

The project currently has two parallel subagent dispatch systems that serve
overlapping purposes. This research examines how to consolidate them, making
Claude Code's native Task tool the primary dispatch path to gain live progress
UI, while retaining the custom ACP dispatch for provider-specific needs.

## Findings

### Current state: two dispatch systems

**System A — Claude Code Task tool (`.claude/agents/`)**

- Agent definitions synced from `.vaultspec/rules/agents/` via `agents_sync()`.
- Transform: strips `tier`, `mode`, `tools` fields; adds `kind: local` and
  resolved `model` (e.g. `claude-sonnet-4-5` for MEDIUM tier).
- Claude Code natively spawns these as subagents with full progress UI: spinner,
  tool use count, ctrl+o expansion, ctrl+b background support.
- **Limitation**: Only Claude models. No Gemini provider support.
- **Limitation**: Agent definitions lose `mode` and `tools` metadata during
  sync — Claude Code doesn't use these fields.

**System B — Custom ACP dispatch (`subagent.py` / MCP `dispatch_agent`)**

- Agent definitions loaded directly from `.vaultspec/rules/agents/`.
- Full ACP lifecycle: spawn process → initialize → new_session → conversation
  loop → cancel → cleanup.
- Supports both Claude and Gemini providers via ACP bridges.
- Streaming works via `SubagentClient.session_update()` + `rich.Console`, but
  only visible when run in a real terminal.
- **Limitation**: When invoked from Claude Code's Bash tool, all output is
  buffered until completion — no live progress UI.
- **Limitation**: MCP `dispatch_agent` returns a task ID for polling, which
  requires multiple round-trips.

### What the Task tool provides natively

When Claude Code dispatches via its Task tool, the user sees:

- Agent name and description in the tool call header
- Live spinner while the agent works
- Tool use count incrementing in real-time
- Expandable detail view (ctrl+o)
- Background execution support (ctrl+b)
- Automatic result display on completion
- `run_in_background` parameter for async dispatch

None of this is available when dispatching via Bash or MCP.

### Gap analysis: what would change

| Capability | Task tool | ACP dispatch | Gap |
|:-----------|:----------|:-------------|:----|
| Live progress UI | Yes | No (buffered) | Task tool wins |
| Claude provider | Yes | Yes | Parity |
| Gemini provider | No | Yes | ACP only |
| Custom ACP features | No | Yes | ACP only |
| Mode enforcement (read-only) | No | Yes | ACP only |
| Tool restrictions | No | Yes (via tools field) | ACP only |
| Session resume | No | Yes | ACP only |
| Session logging | No | Yes | ACP only |
| Max turns / budget | No | Yes | ACP only |
| File artifact tracking | No | Yes | ACP only |

### Architecture options

**Option A: Task tool as default, ACP as fallback**

The `vaultspec-subagent` skill and all workflow skills (research, execute,
review) would default to dispatching via Claude Code's Task tool for
Claude-backed agents. The ACP dispatch path remains for:

- Gemini provider requests
- Features requiring session resume, budget limits, or session logging
- Programmatic dispatch from MCP tools

Implementation:

- Update `vaultspec-subagent` SKILL.md to instruct: "Use the Task tool with
  `subagent_type={agent_name}` for Claude agents. Fall back to CLI dispatch
  for Gemini or when ACP-specific features are needed."
- The `.claude/agents/` definitions already exist and work. No code changes
  needed for Task tool dispatch itself.
- Keep `dispatch_agent` MCP tool for programmatic/automated use cases.

Effort: **Low** (documentation/skill update only).

**Option B: Enhance Task tool agents with ACP features**

Extend the `.claude/agents/` definitions with Claude Code's supported fields
to recapture some ACP features. Claude Code agent definitions support:

- `model` — already synced
- `kind: local` — already set
- Custom instructions in the body — already synced

But Claude Code agents do NOT support: mode enforcement, tool restrictions,
budget/turns limits, session logging, or session resume. These are Claude Code
platform limitations.

Effort: **None** (Claude Code doesn't support these features).

**Option C: Hybrid dispatch router**

Build a dispatch function that inspects the request and routes:

```
dispatch(agent, task, provider=None):
    if provider == "gemini" or needs_acp_features(agent):
        -> ACP dispatch (subagent.py)
    else:
        -> Task tool dispatch
```

This could be implemented as a new MCP tool or as logic in the skill
definition. The MCP tool would need to somehow trigger a Task tool call,
which is not possible from within an MCP server (MCP tools can't invoke
Claude Code's native tools).

Effort: **Medium** (new dispatch logic, but limited by MCP → Task tool
boundary).

### Recommended approach

**Option A** is the clear winner. The Task tool already works for all
Claude-backed vaultspec agents. The only change needed is updating the
`vaultspec-subagent` skill documentation to prefer Task tool dispatch over
CLI/MCP dispatch when running inside Claude Code.

Key changes:

- Update `.vaultspec/rules/skills/vaultspec-subagent/SKILL.md` to document
  Task tool as the preferred dispatch mechanism for Claude agents.
- Update `.claude/rules/vaultspec-subagents.builtin.md` to reflect the new
  dispatch preference.
- Keep ACP dispatch path unchanged for Gemini and advanced features.
- No Python code changes required.

### Key files

| File | Role |
|:-----|:-----|
| `.vaultspec/rules/skills/vaultspec-subagent/SKILL.md` | Dispatch skill definition — needs update |
| `.claude/rules/vaultspec-subagents.builtin.md` | Built-in dispatch rules — needs update |
| `.vaultspec/rules/agents/*.md` | Agent source definitions (unchanged) |
| `.claude/agents/*.md` | Synced Claude Code agents (already working) |
| `src/vaultspec/core/agents.py` | Agent sync logic (unchanged) |
| `src/vaultspec/orchestration/subagent.py` | ACP dispatch (unchanged, kept as fallback) |
| `src/vaultspec/mcp_server/subagent_tools.py` | MCP dispatch (unchanged, kept for programmatic use) |
