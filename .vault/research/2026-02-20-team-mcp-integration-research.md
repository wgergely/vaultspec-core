---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#research"
  - "#team-mcp-integration"
date: 2026-02-20
related:
  - "[[2026-02-20-team-mcp-surface-design-reference]]"
---

<!-- Migrated from frontmatter — do not promote back -->
**Title:** Team MCP Integration: Audit Findings
**Status:** complete

# Team MCP Integration: Audit Findings

> Three-agent parallel audit across subagent_server/, team.py CLI, orchestration/team.py,
> and all rules/ surface area.

## Problem Statement

The `team.py` CLI and `orchestration/team` library were fully implemented but left
unintegrated at three critical seams:

1. **mcp.json** — only registers `vs-subagent-mcp`; no entry for a team MCP server
2. **team.py** — has no `serve` command; cannot be started as an MCP server
3. **rules/** — no `vaultspec-team` skill; all dispatch instructions reference only
   `vaultspec-subagent`, making team mode invisible to agents and the framework

---

## Audit Track 1: FastMCP Server Pattern (from subagent_server/server.py)

### Construction

```python
mcp = FastMCP("vs-subagent-mcp", lifespan=_server_lifespan)
```

### Lifespan pattern

```python
@contextlib.asynccontextmanager
async def _server_lifespan(server: FastMCP):
    # Startup: register resources, spawn background polling task
    yield
    # Shutdown: suppress(asyncio.CancelledError), cancel background tasks
```

### Tool registration

```python
@mcp.tool(annotations=ToolAnnotations(...))
async def dispatch_agent(agent: str, task: str, model: str | None = None) -> str:
    ...
```

### Entry point pattern (subagent.py `command_serve`)

```python
def command_serve(args):
    from subagent_server.server import main as server_main
    server_main(root_dir=args.root, ...)
```

### Required imports

- `FastMCP`, `ToolError`, `FunctionResource`, `ToolAnnotations`
- `mcp.types`, `mcp.server.fastmcp.exceptions`
- Orchestration: `run_subagent`, `LockManager`, `TaskEngine`
- Global state: `ROOT_DIR`, `CONTENT_ROOT`, `AGENTS_DIR`, `lock_manager`, `task_engine`

### Global state initialization

`initialize_server(root_dir, ttl_seconds, content_root)` MUST run before `mcp.run()`.
Windows asyncio: `asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())`.

---

## Audit Track 2: Rules Surface — vaultspec-subagent Mentions

### Inventory: 22 mentions across 13 files

| Category | Files | Count |
|---|---|---|
| Framework-level statements | CLAUDE.md, framework.md | 2 |
| Rule files | vaultspec-subagents.builtin.md (×2) | 6 |
| Workflow skills | vaultspec-{adr,execute,research,review,curate,reference,write}.md | 10 |
| Executor agents | vaultspec-{complex,standard,simple}-executor.md, vaultspec-adr-researcher.md | 4 |

### Files requiring conditional language updates

All 7 workflow skill files, both `vaultspec-subagents.builtin.md` files, both framework
statement locations (`CLAUDE.md` + `framework.md`), and 4 agent files.

### Conditional language template

Replace single-mode dispatch instructions with the pattern:

> - **Single agent:** Invoke the `vaultspec-subagent` skill with `vaultspec-{agent}`.
> - **Team:** Invoke the `vaultspec-team` skill and assign the appropriate roles.

For mandatory code review (`YOU MUST` in complex/standard executor):

> Code review is **MANDATORY** before completion:
> - **Single agent:** Invoke `vaultspec-subagent` with `vaultspec-code-reviewer`.
> - **Team:** Invoke `vaultspec-team` with role=reviewer (multiple reviewers for high-risk).

### vaultspec-subagent.md structural analysis (template for vaultspec-team.md)

- 72 lines, minimal frontmatter (`description` only)
- 5 sections: Title/Warning → Usage → Tooling Strategy → Examples → Behavior
- HTML separator: `<!-- Human-readable documentation above | Agent instructions below -->`
- 3 parameters: `--agent` (req), `--goal` (req), `--model` (opt)
- Mandatory tooling: fd, rg, sg, sd (identical section needed in vaultspec-team.md)

---

## Audit Track 3: orchestration/team.py API & MCP Tool Surface Design

### TeamCoordinator public API

| Method | Sync/Async | Description |
|---|---|---|
| `form_team(name, agent_urls, api_key?)` | async | Fetch agent cards, create session |
| `restore_session(session)` | sync | Re-hydrate coordinator from persisted session |
| `dispatch_parallel(assignments: dict[str,str])` | async | Fan out tasks to members |
| `relay_output(src_task, target_name, content?)` | async | Forward one agent's output to another |
| `dissolve_team()` | async | Cancel all tasks, disconnect |
| `ping_all()` | async | Check reachability, update member status |
| `get_task(agent_name, task_id)` | async | Poll a specific task to completion |

Context manager: `async with coordinator:` (manages httpx client lifecycle).

### TeamSession / TeamMember

```python
@dataclass
class TeamSession:
    team_id: str; name: str; context_id: str
    status: TeamStatus; created_at: str
    members: dict[str, TeamMember]

@dataclass
class TeamMember:
    name: str; url: str; card: AgentCard; status: MemberStatus
```

Enums: `TeamStatus` (forming, active, dissolved, error) · `MemberStatus` (pending, ready, busy, error, offline)

### Designed 8-tool MCP surface for vs-team-mcp

| Tool | Type | TeamCoordinator method |
|---|---|---|
| `create_team` | async | `form_team()` + `_save_session()` |
| `get_team_status` | sync | `_load_session()` read-only |
| `list_teams` | sync | scan `.vault/logs/teams/*.json` |
| `dispatch_task` | async | `restore_session()` + `dispatch_parallel()` |
| `collect_results` | async | `get_task()` per member, timeout-guarded |
| `relay_message` | async | `restore_session()` + `relay_output()` |
| `dissolve_team_session` | async | `restore_session()` + `dissolve_team()` + delete file |
| `ping_team_members` | async | `restore_session()` + `ping_all()` + `_save_session()` |

Design principle: each tool loads session from disk (idempotent, no in-process state held between calls).

### mcp.json entry

```json
"vs-team-mcp": {
  "command": "python",
  "args": [".vaultspec/lib/scripts/team.py", "serve", "--root", "."],
  "env": {}
}
```

Mirrors the existing `vs-subagent-mcp` entry exactly.

---

## Gap Summary

| Gap | Location | Required Action |
|---|---|---|
| Missing `serve` command | `team.py` | Add `command_serve()` + subparser + `team_server/server.py` |
| Missing MCP server module | `.vaultspec/lib/src/team_server/` | Create mirroring `subagent_server/` pattern |
| Missing mcp.json entry | `mcp.json` | Add `vs-team-mcp` entry |
| Missing skill | `.vaultspec/rules/skills/` | Create `vaultspec-team.md` |
| Stale dispatch instructions | 13 files across rules/ | Add conditional single-agent vs team language |

---

## Linked Artifacts

- [[2026-02-20-team-mcp-surface-design-reference]] — tool surface design (from team-design-auditor)
