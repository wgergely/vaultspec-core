---
tags:
  - '#adr'
  - '#team-mcp-integration'
date: '2026-02-20'
related:
  - '[[2026-02-20-team-mcp-integration-research]]'
---

# `team-mcp-integration` adr: Unified `vs-agents-mcp` server | (**status:** `accepted`)

## Problem Statement

The `orchestration/team` library and `team.py` CLI are fully implemented but unintegrated
at three critical seams: `mcp.json` has no team server entry, `team.py` has no `serve`
command, and `rules/` has no `vaultspec-team` skill. Naively adding a second MCP server
(`vs-team-mcp`) would produce two parallel server connections for what is conceptually one
concern — agent orchestration. The architectural question is whether the subagent and team
MCP surfaces should be unified under a single server or remain separate.

## Considerations

**Three options were evaluated:**

**Option 1 — Unified server (`vs-agents-mcp`)**
A new `agent_server/server.py` module exposes all orchestration tools (subagent dispatch

- team lifecycle) under one FastMCP instance. `mcp.json` has a single entry. A new CLI
  entry point (`agents.py serve` or `subagent.py serve` extended) starts the unified server.
  The existing `subagent_server/server.py` is either renamed or merged.

**Option 2 — Extend existing `subagent_server/server.py`**
Team tools (create_team, dispatch_task, etc.) are added directly into the existing server
module. One server, no new module, minimal structural change. Risks coupling two distinct
concerns in a single growing file (~680 lines currently).

**Option 3 — Keep separate servers**
`vs-subagent-mcp` and `vs-team-mcp` remain independent. Maximum isolation but: two MCP
connections, two `mcp.json` entries, duplicated lifespan/init patterns, and a split mental
model for callers selecting between them.

**Evaluation factors:**

- Current `subagent_server/server.py` is already ~680 lines with 5 tools and significant
  global state. Adding 8 team tools would push it past maintainable size.

- `team.py` CLI and `subagent.py` CLI are intentionally separate for standalone use. The
  MCP layer should not mirror that split — it is a higher-level routing concern.

- A unified `vs-agents-mcp` name accurately reflects the domain: "orchestrate agents",
  whether single or team.

- `mcp.json` simplicity: one entry is strictly better than two when both share a process
  lifecycle.

## Constraints

- Existing `subagent_server/server.py` MUST NOT be broken; it is tested by 53 tests.

- `team.py` and `subagent.py` CLIs remain standalone (no merge of the CLI layer).

- The new server module must mirror the FastMCP lifespan and global-state initialization
  pattern from `subagent_server/server.py` exactly.

- Session persistence for teams (`.vault/logs/teams/{name}.json`) must be respected by
  MCP tools — all team tools load/save sessions from disk (idempotent across requests).

- Windows asyncio `ProactorEventLoopPolicy` must be applied in the serve entry point.

- `mcp.json` env block must match the existing pattern (`{}` with implicit PYTHONPATH from
  the serve command's own `_paths.py` bootstrap).

## Implementation

**Phase 1 — Core infrastructure:**

1. Create `agent_server/` module under `.vaultspec/lib/src/` mirroring `subagent_server/`:

   - `agent_server/__init__.py`

   - `agent_server/server.py` — FastMCP instance `"vs-agents-mcp"`, lifespan, 13 tools
     (5 subagent tools from existing server + 8 team tools from design)

   - Reuse `subagent_server/` helpers (LockManager, TaskEngine) via import; do not fork.

1. Add `serve` subcommand to `team.py` (or add a new `agents.py` script) that calls
   `agent_server.server.main()`.

1. Update `mcp.json`:

   - Replace `vs-subagent-mcp` entry with `vs-agents-mcp` pointing to the new serve entry.
   - Keep old entry commented or in a migration note until `agent_server/` tests pass.

**Phase 2 — Rules surface:**

1. Create `.vaultspec/rules/skills/vaultspec-team.md` using the structural template
   derived from `vaultspec-subagent.md` (72-line pattern, 5 sections, same tooling block).

1. Update all 13 rules files containing `vaultspec-subagent` mentions (22 locations) with
   conditional language distinguishing single-agent from team dispatch.

1. Update `vaultspec-subagents.builtin.md` (both copies) to reference `vs-agents-mcp` and
   acknowledge `vaultspec-team` as the parallel dispatch pathway.

**Tool surface for `vs-agents-mcp` (13 tools total):**

| Tool                    | Source                                   |
| ----------------------- | ---------------------------------------- |
| `list_agents`           | carried from subagent_server             |
| `dispatch_agent`        | carried from subagent_server             |
| `get_task_status`       | carried from subagent_server             |
| `cancel_task`           | carried from subagent_server             |
| `get_locks`             | carried from subagent_server             |
| `create_team`           | new, wraps `TeamCoordinator.form_team()` |
| `get_team_status`       | new, read-only session load              |
| `list_teams`            | new, scans `.vault/logs/teams/`          |
| `dispatch_task`         | new, wraps `dispatch_parallel()`         |
| `collect_results`       | new, polls tasks to completion           |
| `relay_message`         | new, wraps `relay_output()`              |
| `dissolve_team_session` | new, wraps `dissolve_team()`             |
| `ping_team_members`     | new, wraps `ping_all()`                  |

## Rationale

Option 1 is chosen over Option 2 because the existing `subagent_server/server.py` is
already at maintainable size limits; adding 8 tools would make it unwieldy and conflate
two distinct orchestration concerns (ACP single-agent vs A2A team). Option 1 is chosen
over Option 3 because two MCP connections for one conceptual domain contradicts the
principle of minimal `mcp.json` surface and forces callers to reason about which server
handles their intent. A unified `vs-agents-mcp` server correctly names the domain and
provides a single routing point for all agent orchestration.

The `subagent_server/` module is preserved intact and its tools are carried into
`agent_server/server.py` via import delegation or copy-with-refactor; the 53-test suite
remains the acceptance bar.

## Consequences

- `mcp.json` simplifies to one server entry.

- `subagent_server/` becomes a candidate for eventual deprecation once `agent_server/`
  reaches test parity; not removed in this phase.

- All downstream rules referencing `vs-subagent-mcp` must be updated to `vs-agents-mcp`.

- `vaultspec-team` skill becomes a first-class peer of `vaultspec-subagent`; both skills
  delegate through the same `vs-agents-mcp` MCP server.

- `team.py` CLI gains a `serve` command but it simply delegates to `agent_server.server`
  (or `agents.py` if a new entry script is preferred) — no team-specific server module
  is created.
