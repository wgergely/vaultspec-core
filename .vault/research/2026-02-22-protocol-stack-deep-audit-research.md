---
tags:
  - "#research"
  - "#protocol-stack"
date: "2026-02-22"
related:
  - "[[2026-02-22-protocol-test-architecture-research]]"
  - "[[2026-02-22-protocol-test-architecture-adr]]"
  - "[[2026-02-22-protocol-test-architecture-plan]]"
  - "[[2026-02-22-gemini-acp-audit-research]]"
  - "[[2026-02-22-gemini-overhaul-reference]]"
---
# Protocol Stack Deep Audit: MCP, CLI, and Test Suite

Cross-domain audit of the vaultspec protocol stack (ACP/A2A/MCP/CLI) conducted
by a 4-agent team (3 Sonnet domain auditors, 1 Opus synthesizer). The audit
was prompted by the discovery that `resume_session_id` in `run_subagent()` is
a no-op — it feeds only the `SessionLogger`, never triggers actual ACP session
resume — exposing a systemic session management gap across all layers.

## Findings

### Systemic Root Cause: Session Management Is Broken Across All Layers

The `resume_session_id` parameter accepted by `run_subagent()` at
`src/vaultspec/orchestration/subagent.py:281` is used solely to name the
`SessionLogger`. The function always calls `conn.new_session()` (line 370),
never `conn.resume_session()` or `conn.load_session()`. The Gemini bridge
*implements* `resume_session`, `load_session`, and `fork_session`
(`gemini_bridge.py:720-842`), but no caller in the codebase invokes them.

This means:
- Multi-turn "state retention" tests create independent sessions per turn
- The State Agent cannot remember values set in a previous invocation
- `interactive=True` (real multi-turn via stdin loop) is only available via
  CLI `--interactive` flag, never programmatically
- MCP `dispatch_agent` hardcodes `interactive=False` and has no
  `resume_session_id` parameter
- No agent definition or skill file specifies session behavior

### Domain 1: MCP Server

**Tool Inventory** — `src/vaultspec/subagent_server/server.py` and
`src/vaultspec/mcp_tools/team_tools.py` register 13 tools across two groups:

Subagent tools: `list_agents`, `dispatch_agent`, `get_task_status`,
`cancel_task`, `get_locks`.

Team tools: `create_team`, `team_status`, `list_teams`, `dispatch_task`,
`broadcast_message`, `send_message`, `spawn_agent`, `dissolve_team`.

**P0 — `dispatch_agent` hardcodes `interactive=False`**
(`server.py:162,488`). MCP callers cannot dispatch interactive agents.

**P0 — `set_session_id()` called but never consumed for resume**
(`server.py:500-502`). The session ID is stored via `task_engine` but
`get_task_status` does not return it, so callers cannot retrieve the ID
needed for resume.

**P1 — No `resume_session_id` param on `dispatch_agent`**
(`server.py:401-410`). Even if backend resume were fixed, MCP callers
could not use it.

**P1 — Team MCP tools are synchronous/blocking** (`team_tools.py:310-438`).
`dispatch_task`, `send_message`, `broadcast_message` call
`coordinator.dispatch_parallel()` which polls to terminal state before
returning. Unlike `dispatch_agent` which returns a `taskId` immediately and
runs in background, team tools block the entire MCP tool call. For
long-running A2A agents this will cause MCP tool timeouts.

**P2 — No `provider_override` param on `dispatch_agent`**
(`server.py:401-410`). Provider is auto-detected from model name.

**P2 — `relay_output()` has no MCP tool equivalent.** Pipeline workflows
require manual extraction and re-dispatch.

**P3 — Agent resource registration uses private API**
(`server.py:320-323`). `_resource_manager._resources` is an
implementation detail.

**P3 — Corrupt team session JSON causes unhandled exception**
(`team_tools.py:134`). Should be wrapped in try/except with ToolError.

**P3 — Gemini provider silently drops Claude-only features**
(`gemini.py:249-256`). `max_turns`, `budget`, `effort` are
warned-and-ignored. MCP callers don't know their parameters were dropped.

### Domain 2: CLI Intermediaries

**Parameter mapping for `subagent_cli.py` `command_run` → `run_subagent()`:**

| CLI Flag | Backend Param | Status |
|---|---|---|
| `--agent` | `agent_name` | Present |
| `--goal` | `initial_task` | Present |
| `--model` | `model_override` | Present |
| `--provider` | `provider_override` | Present |
| `--mode` | `mode` | Present |
| `--interactive` | `interactive` | Present |
| `--context` | `context_files` | Present |
| `--plan` | `plan_file` | Present |
| (none) | `resume_session_id` | **MISSING** |
| (none) | `max_turns` | **MISSING** |
| (none) | `budget` | **MISSING** |
| (none) | `effort` | **MISSING** |
| (none) | `output_format` | **MISSING** |
| (none) | `mcp_servers` | **MISSING** |
| `--content-dir` | `content_root` | Partial (resolved but not passed to `run_subagent`) |

**P1 — CLI missing 6 backend parameters** (`subagent_cli.py:125-142`).
MCP `dispatch_agent` exposes `max_turns`, `budget`, `effort`,
`output_format` but the CLI does not — a parity gap.

**P0 — `vaultspec test` command has stale module paths**
(`cli.py:1526-1535`). `MODULE_PATHS` references `.vaultspec/lib/tests/`
and `.vaultspec/lib/src/` which are pre-restructure paths. The
`vaultspec test` command silently finds zero tests.

**P2 — `--debug`/`--verbose` not registered on `a2a-serve` and `serve`
subparsers** (`subagent_cli.py:293-301`). Running
`vaultspec-subagent a2a-serve --debug` fails with "unrecognized argument".

**P1 — No team CLI commands.** `TeamCoordinator` has `form_team`,
`dissolve_team`, `dispatch_parallel`, `relay_output`, `collect_results`,
`ping_agents`, `spawn_agent`, `restore_session` — none are accessible from
CLI. Only MCP tools and Python API.

**P1 — Claude A2A Executor has session resume via `context_id`, Gemini
does not** (`claude_executor.py:141-144` vs `gemini_executor.py:138-145`).
Claude executor stores `session_id` per `context_id` and passes
`resume=prev_session`. Gemini executor stores `session_id` in
`_session_ids` but never passes it back.

### Domain 3: Test Suite

**Positive confirmations:**
- Protocol matrix is 100% complete — all 8 ADR Decision 3 scenarios covered
- Every production module has corresponding test coverage
- Zero mocking in the entire test suite — DI pattern used consistently
- All 13 custom markers registered in `pyproject.toml`
- No TODO/FIXME/HACK in any test file

**P0 — Missing `__init__.py` in `src/vaultspec/tests/`.**
`src/vaultspec/tests/cli/` has `__init__.py` but the parent
`src/vaultspec/tests/` does not.

**P0 — Multi-turn state tests do not test actual session resume.**
`tests/protocol/isolation/test_subagent_gemini.py:52-61` and
`test_subagent_claude.py:52-61` pass `resume_session_id` which only
feeds the logger. Each invocation creates a brand new ACP session.

**P1 — `monkeypatch.chdir` in `test_utils.py:56`.**
`src/vaultspec/orchestration/tests/test_utils.py:56` uses
`monkeypatch.chdir(TEST_PROJECT)` which mutates the process working
directory — dangerous in concurrent test runs and violates the project
ban on monkeypatch for side-effecting mutations.

**P2 — 7 of 16 test constants are stale/unused.**
`tests/constants.py` defines `TEST_PORT_BASE`, `TEST_PORT_SUBAGENT`, all
`TIMEOUT_*` constants, and `DELAY_*` constants. Only `TEST_PORT_A2A_BASE`
has adoption. Bundled `src/` tests hardcode port numbers.

**P3 — `skipif` guards on CLI executables** (`test_e2e_a2a.py:38,43`,
`test_french_novel_relay.py:35,40`, `test_client_terminal.py:33`). The
project rule says "NO skip/skipIf except hardware deps." CLI executable
presence is an infrastructure guard, not a hardware dep.

**P3 — `test_french_novel_relay.py` still exists.** Legacy "fairytale"
test that the research doc and ADR both call for removing.

**P4 — `monkeypatch.setenv` used extensively in config tests.**
`tests/test_logging_config.py` (15 uses), `tests/test_config.py` (38),
`src/vaultspec/core/tests/test_config.py` (27+). These test real code
paths with real env vars. Borderline per letter of the rule but defensible
in spirit. Rule should be clarified to explicitly allow
`monkeypatch.setenv/delenv` for env-var driven config testing.

## Dependency Graph

```
[1] Fix run_subagent() → conn.resume_session() when resume_session_id set
    |
    +---> [2] Add resume_session_id param to MCP dispatch_agent
    |         |
    |         +---> [5] Store+reuse session_id in Gemini A2A executor
    |
    +---> [3] Add --resume-session flag to CLI
    |
    +---> [4] Fix multi-turn state tests to actually test resume

[6] Design programmatic multi-turn API (replaces stdin-blocking interactive)
    |
    +---> [7] MCP multi-turn dispatch support

[8] Add --max-turns/--budget/--effort/--output-format to CLI (independent)

[9] Team tools async pattern — TeamTaskEngine (independent)

[10] Fix stale vaultspec test paths in cli.py (independent)
```

## Recommended Implementation Order

- Fix `run_subagent()` to use `conn.resume_session()` (P0, medium)
- Add `resume_session_id` to MCP `dispatch_agent` (P1, trivial)
- Add `--resume-session` to CLI (P1, small)
- Fix Gemini A2A executor session reuse (P1, small)
- Update multi-turn tests to verify actual resume (P0, small)
- Add missing CLI flags for `max_turns`, `budget`, `effort`, etc. (P1, small)
- Fix stale `vaultspec test` module paths (P0, small)
- Add missing `__init__.py` in `src/vaultspec/tests/` (P0, trivial)
- Team tools async pattern (P1, medium)
- Fix Windows process tree kill in `team_tools.py` (P2, trivial)
- Design programmatic multi-turn API — requires ADR (P0, large)
- Clean up legacy `test_french_novel_relay.py` (P3, trivial)

## Consolidated Priority Summary

| Severity | Count |
|----------|-------|
| P0 (Broken) | 7 |
| P1 (Missing critical) | 7 |
| P2 (Gap) | 7 |
| P3 (Quality) | 7 |
| P4 (Polish) | 7 |
| **Total** | **35** |
