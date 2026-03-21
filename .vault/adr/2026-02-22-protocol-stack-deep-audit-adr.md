---
tags:
  - '#adr'
  - '#protocol-stack'
date: '2026-02-22'
related:
  - '[[2026-02-22-protocol-stack-deep-audit-research]]'
  - '[[2026-02-22-protocol-test-architecture-adr]]'
  - '[[2026-02-22-protocol-test-architecture-research]]'
  - '[[2026-02-22-gemini-acp-bridge-adr]]'
  - '[[2026-02-22-gemini-acp-audit-research]]'
  - '[[2026-02-22-gemini-overhaul-reference]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `protocol-stack` ADR: Protocol Stack Deep Audit Remediation | (**status:** `superseded`)

**SUPERSEDED** — This ADR is fully superseded by
`[[2026-02-24-subagent-protocol-adr]]` (Unified A2A Protocol Stack — Full
Rewrite). Session resume fixes, CLI parity, and team tools patterns described
here assumed ACP bridges remain. That assumption is eliminated. Specific
decisions (e.g. `__init__.py` fix, monkeypatch policy) may still be
independently valid but are not binding from this document.

## Problem Statement

A cross-domain audit of the vaultspec protocol stack (ACP/A2A/MCP/CLI) revealed
35 findings across 5 severity levels. The systemic root cause is that
`run_subagent()` at `src/vaultspec/orchestration/subagent.py:281` always calls
`conn.new_session()` (line 370), never `conn.resume_session()`. The
`resume_session_id` parameter is consumed only by the `SessionLogger` for naming
purposes. The Gemini bridge implements `resume_session`, `load_session`, and
`fork_session` (`gemini_bridge.py:720-842`) but no caller in the codebase
invokes them.

This renders multi-turn "state retention" tests meaningless (each turn creates
an independent session), breaks the State Agent pattern established in
\[[2026-02-22-protocol-test-architecture-adr]\], and leaves MCP callers with no
mechanism to resume sessions. The audit also uncovered CLI/MCP parity gaps,
blocking team tools, test infrastructure defects, and an absent programmatic
multi-turn API.

## Considerations

- The Gemini bridge already has the resume/load/fork session machinery; the gap
  is purely in the callers

- Claude's A2A executor (`claude_executor.py:141-144`) correctly stores
  `session_id` per `context_id` and passes `resume=prev_session`; Gemini's
  executor stores the ID but never passes it back

- MCP `dispatch_agent` hardcodes `interactive=False` and exposes no
  `resume_session_id` parameter; `get_task_status` does not surface the
  `session_id` it stores

- Team MCP tools (`team_tools.py:310-438`) call `dispatch_parallel()` which
  polls to terminal state before returning, blocking the MCP tool call and
  causing timeouts for long-running A2A agents

- The CLI is missing 6 parameters that `run_subagent()` already accepts:
  `resume_session_id`, `max_turns`, `budget`, `effort`, `output_format`,
  `mcp_servers`

- `vaultspec test` references pre-restructure module paths
  (`.vaultspec/lib/tests/`, `.vaultspec/lib/src/`) and silently finds zero tests

- `src/vaultspec/tests/` is missing `__init__.py`, breaking Python package
  discovery

- The project bans mocking, but `monkeypatch.setenv`/`delenv` for env-var
  config testing is a gray area requiring explicit policy

- A non-blocking programmatic multi-turn API is a prerequisite for MCP
  multi-turn dispatch but is large enough to warrant its own ADR

## Constraints

- Session resume must work for both Claude and Gemini providers without
  provider-specific branching in the orchestration layer

- The MCP `dispatch_agent` tool returns a `taskId` immediately (non-blocking);
  any resume mechanism must preserve this async contract

- Team tools cannot be refactored to async without introducing a task engine
  abstraction, which carries its own complexity

- CLI flags must maintain backward compatibility; all new flags are additive

- The `monkeypatch` policy clarification is a documentation change that affects
  contributor behavior and must be explicit

## Implementation

This ADR authorizes five decision tracks. Tracks A and B are independent of each
other. Tracks C, D, and E are independent of all other tracks. Track F is
deferred to a future ADR.

### Decision 1: Session Management Fix (Track A -- dependency chain)

Fix the root cause and propagate session resume capability through all layers.

**Step 1a.** Modify `run_subagent()` in `src/vaultspec/orchestration/subagent.py`
to branch on `resume_session_id`:

- When `resume_session_id` is set, call `conn.resume_session(resume_session_id)`
  instead of `conn.new_session()`

- When unset, preserve the current `conn.new_session()` behavior

- The ACP connection interface already supports both methods; this is a
  conditional dispatch, not a new abstraction

**Step 1b.** Surface `session_id` in the MCP `get_task_status` response
(`server.py`). The task engine already stores the ID via `set_session_id()`;
include it in the response payload so callers can retrieve it for resume.

**Step 1c.** Add `resume_session_id` as an optional parameter to the MCP
`dispatch_agent` tool schema (`server.py:401-410`). Pass it through to
`run_subagent()`.

**Step 1d.** Add `--resume-session` flag to the CLI in `subagent_cli.py`. Map it
to the `resume_session_id` parameter of `run_subagent()`.

**Step 1e.** Fix Gemini A2A executor session reuse
(`gemini_executor.py:138-145`). The executor stores `session_id` in
`_session_ids` but never passes it back to the ACP connection on subsequent
turns. Align with Claude executor behavior: look up the stored session ID by
`context_id` and pass it as the resume parameter.

**Step 1f.** Update multi-turn state tests
(`tests/protocol/isolation/test_subagent_gemini.py:52-61`,
`test_subagent_claude.py:52-61`) to verify actual session resume. Tests must
assert that Turn 2 retrieves state set in Turn 1 via a resumed (not new)
session. This validates the entire chain from Step 1a through 1e.

### Decision 2: CLI/MCP Parity (Track C -- independent)

Eliminate the 6-parameter gap between CLI and `run_subagent()`.

**Step 2a.** Add the following flags to `subagent_cli.py` `command_run`:

- `--max-turns` (int) mapped to `max_turns`
- `--budget` (float) mapped to `budget`
- `--effort` (str, choices: low/medium/high) mapped to `effort`
- `--output-format` (str) mapped to `output_format`
- `--resume-session` (str) mapped to `resume_session_id` (shared with Decision 1d)
- `--mcp-servers` (str, JSON array or comma-separated) mapped to `mcp_servers`

**Step 2b.** Fix stale `MODULE_PATHS` in `cli.py:1526-1535`. Replace
`.vaultspec/lib/tests/` and `.vaultspec/lib/src/` with the correct
post-restructure paths (`src/vaultspec/**/tests/`, `tests/`).

**Step 2c.** Register `--debug` and `--verbose` on the `a2a-serve` and `serve`
subparsers in `subagent_cli.py:293-301`.

**Step 2d.** Add team CLI commands that expose `TeamCoordinator` methods:
`form-team`, `dissolve-team`, `team-status`, `dispatch-task`, `spawn-agent`. At
minimum, parity with the 8 MCP team tools.

### Decision 3: Team Tools Async Pattern (Track B -- independent)

Replace the blocking `dispatch_parallel()` call pattern in team MCP tools with
an async task-based approach.

**Step 3a.** Introduce a `TeamTaskEngine` (or equivalent) that mirrors the
subagent `TaskEngine` pattern: team tools submit work and return a `taskId`
immediately; callers poll via a status endpoint.

**Step 3b.** Refactor `dispatch_task`, `send_message`, and `broadcast_message`
in `team_tools.py` to use the async pattern. These three tools currently block
on `coordinator.dispatch_parallel()`.

**Step 3c.** Add a `relay_output` MCP tool that wraps
`TeamCoordinator.relay_output()`. Pipeline workflows currently require manual
extraction and re-dispatch.

### Decision 4: Test Suite Fixes (Track D -- independent)

Address test infrastructure defects that undermine suite reliability.

**Step 4a.** Add `__init__.py` to `src/vaultspec/tests/`. The child directory
`src/vaultspec/tests/cli/` already has one; the parent does not.

**Step 4b.** Remove `monkeypatch.chdir(TEST_PROJECT)` from
`src/vaultspec/orchestration/tests/test_utils.py:56`. Replace with explicit path
injection (pass the test project path as a parameter to the function under test)
to avoid mutating process-global state in concurrent test runs.

**Step 4c.** Audit and remove the 7 stale/unused constants in
`tests/constants.py` (`TEST_PORT_BASE`, `TEST_PORT_SUBAGENT`, all `TIMEOUT_*`,
all `DELAY_*`). Consolidate remaining constants.

**Step 4d.** Clarify the `monkeypatch` policy in project memory / contributing
docs: `monkeypatch.setenv` and `monkeypatch.delenv` are explicitly permitted for
environment-variable-driven configuration testing. `monkeypatch.chdir`,
`monkeypatch.setattr`, and `monkeypatch.syspath_prepend` remain banned as they
mutate process-global state or substitute real behavior with fakes.

### Decision 5: Programmatic Multi-Turn API (Track F -- deferred)

This decision is **not authorized for implementation** by this ADR. It is
recorded here for traceability and will require its own dedicated ADR.

The current `interactive=True` mode works via a stdin loop, making it unusable
from MCP or programmatic callers. A non-blocking multi-turn API is needed that:

- Accepts a sequence of turns as input (or provides a turn-by-turn callback
  interface)

- Returns results per turn without requiring stdin

- Integrates with MCP `dispatch_agent` for multi-turn dispatch

This is a large architectural change that affects the ACP connection interface,
the orchestration layer, and the MCP tool contract. It depends on Decision 1
(session resume) being complete.

## Rationale

**Session management (Decision 1)** is the highest-priority fix because it is
the systemic root cause. Every layer -- orchestration, MCP, CLI, A2A executors,
and tests -- is affected by the single bug at `subagent.py:370`. The fix is
surgical: a conditional branch in one function, with propagation of the parameter
through existing interfaces. The Gemini bridge already implements the backend;
only the callers are broken.

**CLI/MCP parity (Decision 2)** is prioritized because the 6-parameter gap means
CLI users cannot access capabilities that MCP users can (and vice versa). The
stale `vaultspec test` paths are a P0 because the test command silently produces
zero results, which is worse than failing loudly.

**Team tools async (Decision 3)** is independent but urgent because blocking MCP
tool calls will cause timeouts for any team operation involving long-running A2A
agents. The subagent layer already solved this problem with the `TaskEngine`
pattern; team tools should adopt the same architecture.

**Test suite fixes (Decision 4)** are prerequisites for reliable CI. The missing
`__init__.py` breaks package discovery, and `monkeypatch.chdir` violates the
project's testing philosophy. The policy clarification on `monkeypatch.setenv`
resolves a gray area that causes contributor confusion.

**Programmatic multi-turn (Decision 5)** is deferred because it requires
designing a new API contract that touches multiple layers. Attempting it without
a dedicated research and ADR cycle would risk an under-specified implementation.

## Consequences

**Positive:**

- Multi-turn agent workflows will actually persist state across turns, enabling
  the State Agent pattern from \[[2026-02-22-protocol-test-architecture-adr]\]

- CLI and MCP interfaces will expose identical capabilities, eliminating a class
  of "works in MCP but not CLI" (or vice versa) bugs

- Team operations will no longer block MCP callers, enabling real-time team
  coordination from client tools

- The test suite will have correct package structure, no process-global mutations,
  and a clear policy on permissible `monkeypatch` usage

- The deferred Decision 5 establishes a clear dependency chain: session resume
  first, then multi-turn API, preventing premature implementation

**Negative:**

- Decision 1 touches the critical path of every agent invocation; regressions
  must be caught by the protocol matrix tests from
  \[[2026-02-22-protocol-test-architecture-adr]\]

- Decision 3 introduces a new `TeamTaskEngine` abstraction that adds complexity
  to the team tools layer and requires its own test coverage

- Decision 4d (policy clarification) may require revisiting existing tests that
  use `monkeypatch.setattr` in ways that were previously tolerated

- Decision 5's deferral means MCP multi-turn dispatch remains unavailable until
  a follow-up ADR is completed
