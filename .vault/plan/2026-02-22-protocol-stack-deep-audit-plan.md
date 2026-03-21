---
tags:
  - '#plan'
  - '#protocol-stack'
date: '2026-02-22'
related:
  - '[[2026-02-22-protocol-stack-deep-audit-research]]'
  - '[[2026-02-22-protocol-stack-deep-audit-adr]]'
  - '[[2026-02-22-protocol-test-architecture-adr]]'
  - '[[2026-02-22-gemini-acp-bridge-adr]]'
  - '[[2026-02-22-gemini-overhaul-reference]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `protocol-stack` deep audit remediation plan

Implementation plan for the 4 authorized decisions in
\[[2026-02-22-protocol-stack-deep-audit-adr]\]. Decision 5 (Programmatic
Multi-Turn API) is **deferred** and excluded from this plan.

The 4 tracks are fully independent of each other and can execute in
parallel. Within Track A, steps form a dependency chain. Tracks B, C,
and D are internally sequential but can each start immediately.

## Proposed Changes

Fix the systemic session management bug where `run_subagent()` always
calls `conn.new_session()`, propagate the fix through MCP/CLI/A2A
layers, eliminate CLI/MCP parity gaps, convert blocking team tools to
an async task pattern, and repair test infrastructure defects.

## Tasks

<!-- IMPORTANT: This document must be updated between execution runs to
     track progress. -->

### Phase 1 — Track A: Session Management Fix (dependency chain)

Root cause fix plus propagation through all consumer layers.

- Name: Fix `run_subagent()` session resume branch

- Step summary: Phase 1 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-A-step1a.md`)

- Executing sub-agent: `vaultspec-complex-executor`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 1a

  **File:** `src/vaultspec/orchestration/subagent.py`
  **Line 370:** Replace the unconditional `await conn.new_session(...)` with a
  conditional branch:

  ```python
  if resume_session_id:
    session = await conn.resume_session(
          cwd=str(root_dir),
          session_id=resume_session_id,
          mcp_servers=final_mcp_servers_list,
      )
  else:
      session = await conn.new_session(
          cwd=str(root_dir),
          mcp_servers=final_mcp_servers_list,
      )
  ```

  The ACP connection interface (`gemini_bridge.py:775`, `claude_bridge.py:863`)
  already implements `resume_session()`. No new abstraction is needed.

______________________________________________________________________

- Name: Surface `session_id` in MCP `get_task_status` response

- Step summary: Phase 1 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-A-step1b.md`)

- Executing sub-agent: `vaultspec-standard-executor`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 1b

  **File:** `src/vaultspec/subagent_server/server.py`
  **Function:** `get_task_status()` (line 553-584)
  **Change:** After constructing the `res` dict (line 560-566), add the
  session ID if the task engine has one stored:

  ```python
  session_id = task_engine.get_session_id(task_id)
  ```

if session_id:
res["session_id"] = session_id

````

Requires adding a `get_session_id()` method to `TaskEngine`
(`src/vaultspec/orchestration/task_engine.py`) -- it already has
`set_session_id()` at line 338.

---

- Name: Add `resume_session_id` to MCP `dispatch_agent` tool
- Step summary: Phase 1 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-A-step1c.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-protocol-stack-deep-audit-adr]] Decision 1c

**File:** `src/vaultspec/subagent_server/server.py`
**Function:** `dispatch_agent()` (line 401-410)
**Change:** Add `resume_session_id: str | None = None` parameter to the
function signature. Pass it through to `_run_subagent_fn()` at line 483-498.
Also update `_prepare_dispatch_kwargs()` (line 142-170) to accept and
include the parameter.

---

- Name: Add `--resume-session` CLI flag
- Step summary: Phase 1 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-A-step1d.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-protocol-stack-deep-audit-adr]] Decision 1d, shared with Decision 2a

**File:** `src/vaultspec/subagent_cli.py`
**Location:** `run_parser` argument definitions (after line 291)
**Change:** Add `--resume-session` argument. Pass it to `run_subagent()`
in `command_run()` at line 128-142.

Note: This flag is shared with Track C Step 2a. If Track C executes
first, this step becomes a no-op verification.

---

- Name: Fix Gemini A2A executor session reuse
- Step summary: Phase 1 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-A-step1e.md`)
- Executing sub-agent: `vaultspec-complex-executor`
- References: [[2026-02-22-protocol-stack-deep-audit-adr]] Decision 1e

**File:** `src/vaultspec/protocol/a2a/executors/gemini_executor.py`
**Function:** `execute()` (line 108-250)
**Change:** Before creating the subagent task (line 138-144), look up
the stored session ID for the current `context_id`:

```python
async with self._session_ids_lock:
  prev_session = self._session_ids.get(context_id)

subagent_task = asyncio.create_task(
    self._run_subagent(
        agent_name=self._agent_name,
        root_dir=self._root_dir,
        initial_task=prompt,
        model_override=self._model,
        resume_session_id=prev_session,
    )
)
````

This aligns Gemini executor behavior with the Claude executor
(`claude_executor.py:141-144`), which already passes `resume=prev_session`.

______________________________________________________________________

- Name: Update multi-turn state tests to verify actual session resume

- Step summary: Phase 1 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-A-step1f.md`)

- Executing sub-agent: `vaultspec-standard-executor`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 1f

  **Files:**

  - `tests/protocol/isolation/test_subagent_gemini.py` (lines 30-61)
  - `tests/protocol/isolation/test_subagent_claude.py` (lines 30-61)

  **Change:** The existing tests already pass `resume_session_id` correctly.
  After Step 1a is complete, these tests will exercise the real resume path
  without code changes. However, add an explicit assertion that Turn 2
  runs on a resumed (not new) session. This can be verified by:

  - Asserting that `result2.session_id == result1.session_id` (same session
    resumed, not a new one created)

  - Adding a comment explaining that this test depends on the Step 1a fix

  No mocking. Tests run against real ACP connections.

______________________________________________________________________

### Phase 2 — Track C: CLI/MCP Parity (independent)

Close the parameter gap between CLI and backend.

- Name: Add 6 missing CLI flags to `subagent_cli.py`

- Step summary: Phase 2 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-C-step2a.md`)

- Executing sub-agent: `vaultspec-standard-executor`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 2a

  **File:** `src/vaultspec/subagent_cli.py`
  **Location:** `run_parser` argument definitions (lines 255-301)
  **Change:** Add arguments for all 6 missing parameters:

  - `--max-turns` (type=int)
  - `--budget` (type=float)
  - `--effort` (choices=["low", "medium", "high"])
  - `--output-format` (choices=["text", "json", "stream-json"])
  - `--resume-session` (type=str) -- shared with Track A Step 1d
  - `--mcp-servers` (type=str, JSON string or comma-separated)

  Update `command_run()` (line 125-142) to pass all new args to
  `run_subagent()`. For `--mcp-servers`, parse JSON string into dict.

______________________________________________________________________

- Name: Fix stale `MODULE_PATHS` in `cli.py`

- Step summary: Phase 2 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-C-step2b.md`)

- Executing sub-agent: `vaultspec-standard-executor`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 2b

  **File:** `src/vaultspec/cli.py`
  **Location:** `MODULE_PATHS` dict (lines 1526-1536) and fallback paths
  (lines 1557-1558)
  **Change:** Replace stale pre-restructure paths with correct
  post-restructure paths:

  ```python
  MODULE_PATHS = {
    "cli": ["src/vaultspec/tests/cli"],
      "rag": ["src/vaultspec/rag/tests"],
      "vault": ["src/vaultspec/vaultcore/tests"],
      "protocol": ["src/vaultspec/protocol/tests", "src/vaultspec/protocol/acp/tests", "src/vaultspec/protocol/a2a/tests"],
      "orchestration": ["src/vaultspec/orchestration/tests"],
      "subagent": ["src/vaultspec/subagent_server/tests"],
  }
  ```

  Also update the fallback `else` branch (lines 1557-1558) to use
  `src/vaultspec/` and `tests/` instead of `.vaultspec/lib/tests/` and
  `.vaultspec/lib/src/`.

  Verify by inspecting actual test directory layout with `fd`.

______________________________________________________________________

- Name: Register `--debug`/`--verbose` on `a2a-serve` and `serve` subparsers

- Step summary: Phase 2 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-C-step2c.md`)

- Executing sub-agent: `vaultspec-standard-executor`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 2c

  **File:** `src/vaultspec/subagent_cli.py`
  **Location:** `serve_parser` (line 305-306) and `a2a_serve_parser`
  (line 309-339)
  **Change:** Add `--debug` and `--verbose` arguments to both subparsers,
  mirroring the existing flags on `run_parser` (lines 293-301). Update
  `command_serve()` and `command_a2a_serve()` to respect these flags via
  `configure_logging()`.

______________________________________________________________________

- Name: Add team CLI commands exposing `TeamCoordinator` methods

- Step summary: Phase 2 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-C-step2d.md`)

- Executing sub-agent: `vaultspec-complex-executor`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 2d

  **File:** `src/vaultspec/subagent_cli.py` (or a new
  `src/vaultspec/team_cli.py` if one exists)
  **Change:** Add subcommands that mirror the 8 MCP team tools:

  - `form-team` -> `TeamCoordinator.form_team()`
  - `dissolve-team` -> `TeamCoordinator.dissolve_team()`
  - `team-status` -> session load + status display
  - `dispatch-task` -> `TeamCoordinator.dispatch_parallel()`
  - `spawn-agent` -> `TeamCoordinator.spawn_agent()`
  - `list-teams` -> scan `.vault/logs/teams/`
  - `send-message` -> `TeamCoordinator.dispatch_parallel()` (single)
  - `broadcast-message` -> `TeamCoordinator.dispatch_parallel()` (all)

  The session persistence pattern from `team_tools.py` (lines 79-165)
  should be reused. `TeamCoordinator` methods are at
  `src/vaultspec/orchestration/team.py` lines 298-638.

______________________________________________________________________

### Phase 3 — Track B: Team Tools Async Pattern (independent)

Replace blocking `dispatch_parallel()` calls in team MCP tools with an
async task-based approach.

- Name: Introduce `TeamTaskEngine`

- Step summary: Phase 3 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-B-step3a.md`)

- Executing sub-agent: `vaultspec-complex-executor`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 3a

  **New file:** `src/vaultspec/orchestration/team_task_engine.py`
  **Pattern:** Mirror the existing `TaskEngine` at
  `src/vaultspec/orchestration/task_engine.py` (line 240+). The
  `TeamTaskEngine` should:

  - Accept a team name and agent name when creating a task
  - Return a `taskId` immediately
  - Run the team dispatch in a background asyncio task
  - Support `get_task_status()` and `cancel_task()` queries
  - Store results when `dispatch_parallel()` completes

  The existing `TaskEngine` already demonstrates this pattern for
  subagent tools. The team version wraps `TeamCoordinator.dispatch_parallel()`
  instead of `run_subagent()`.

______________________________________________________________________

- Name: Refactor blocking team tools to async pattern

- Step summary: Phase 3 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-B-step3b.md`)

- Executing sub-agent: `vaultspec-complex-executor`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 3b

  **File:** `src/vaultspec/mcp_tools/team_tools.py`
  **Functions:** `dispatch_task()` (line 310-355), `send_message()`
  (line 397-438), `broadcast_message()` (line 358-394)
  **Change:** Refactor each function to:

  1. Create a task via `TeamTaskEngine.create_task()`
  1. Launch the coordinator dispatch in a background asyncio task
  1. Return `{"status": "working", "taskId": ...}` immediately
  1. On completion, store results via `TeamTaskEngine.complete_task()`

  Add a `get_team_task_status` MCP tool that wraps
  `TeamTaskEngine.get_task_status()`.

______________________________________________________________________

- Name: Add `relay_output` MCP tool

- Step summary: Phase 3 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-B-step3c.md`)

- Executing sub-agent: `vaultspec-standard-executor`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 3c

  **File:** `src/vaultspec/mcp_tools/team_tools.py`
  **Change:** Add a new tool function `relay_output()` that wraps
  `TeamCoordinator.relay_output()` (at `src/vaultspec/orchestration/team.py`
  line 522). Parameters: `team_name` (str), `from_agent` (str),
  `to_agent` (str). Register it in `register_tools()` with appropriate
  `ToolAnnotations`.

______________________________________________________________________

### Phase 4 — Track D: Test Suite Fixes (independent)

Address test infrastructure defects.

- Name: Add `__init__.py` to `src/vaultspec/tests/`

- Step summary: Phase 4 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-D-step4a.md`)

- Executing sub-agent: `vaultspec-standard-executor`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 4a

  **New file:** `src/vaultspec/tests/__init__.py`
  **Content:** Empty file (or minimal docstring). The child directory
  `src/vaultspec/tests/cli/__init__.py` already exists; the parent
  package marker is missing, which breaks Python package discovery for
  `pytest --import-mode=importlib`.

______________________________________________________________________

- Name: Remove `monkeypatch.chdir` from `test_utils.py`

- Step summary: Phase 4 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-D-step4b.md`)

- Executing sub-agent: `vaultspec-standard-executor`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 4b

  **File:** `src/vaultspec/orchestration/tests/test_utils.py`
  **Location:** `TestFindProjectRoot.test_finds_git_root()` (line 53-58)
  **Change:** `find_project_root()` at `src/vaultspec/orchestration/utils.py:17`
  uses `pathlib.Path.cwd()` internally. The function signature accepts no
  arguments, so `monkeypatch.chdir` is the only way to influence its
  behavior. The fix is to refactor `find_project_root()` to accept an
  optional `start_dir` parameter (defaulting to `Path.cwd()`), then
  update the test to pass `TEST_PROJECT` directly instead of using
  `monkeypatch.chdir`.

  This is a small signature change to a utility function. Callers that
  rely on the default (`Path.cwd()`) behavior are unaffected.

______________________________________________________________________

- Name: Audit and remove stale constants in `tests/constants.py`

- Step summary: Phase 4 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-D-step4c.md`)

- Executing sub-agent: `vaultspec-standard-executor`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 4c

  **File:** `tests/constants.py`
  **Change:** The following constants (lines 73-103) have zero imports
  outside this file (confirmed by codebase grep):

  - `TEST_PORT_BASE` (line 73)
  - `TEST_PORT_SUBAGENT` (line 75)
  - `TIMEOUT_QUICK` through `TIMEOUT_A2A_E2E` (lines 81-88)
  - `DELAY_SHORT`, `DELAY_MEDIUM`, `DELAY_LONG` (lines 94-96)

  Keep: `TEST_PORT_A2A_BASE` (line 74), `PROJECT_ROOT`, `LIB_SRC`,
  `SCRIPTS`, `TEST_PROJECT`, `TEST_VAULT`, `GPU_FAST_CORPUS_STEMS`,
  `LANCE_SUFFIX_*`, `ACP_TIMEOUT_*`.

  Remove the unused constants. Add a comment explaining which constants
  are actively consumed.

______________________________________________________________________

- Name: Clarify `monkeypatch` policy

- Step summary: Phase 4 Step Record (`.vault/exec/2026-02-22-protocol-stack/2026-02-22-protocol-stack-D-step4d.md`)

- Executing sub-agent: `vaultspec-code-reviewer`

- References: \[[2026-02-22-protocol-stack-deep-audit-adr]\] Decision 4d

  **Change:** Update the project memory (`MEMORY.md`) to clarify the
  `monkeypatch` policy under the existing "No Mocking — Ever" section.
  Add an explicit carve-out:

  > `monkeypatch.setenv` and `monkeypatch.delenv` are **permitted** for
  > environment-variable-driven configuration testing, as they exercise
  > real code paths with real configuration values.
  >
  > The following remain **banned**: `monkeypatch.setattr`,
  > `monkeypatch.chdir`, `monkeypatch.syspath_prepend` — these mutate
  > process-global state or substitute real behavior with fakes.

  This resolves the gray area identified in the research doc where 80+
  `monkeypatch.setenv` uses exist across config tests.

______________________________________________________________________

## Parallelization

All four tracks (A, B, C, D) are fully independent and can execute in
parallel via separate sub-agents:

```
Track A (Session Mgmt)  ──→ vaultspec-complex-executor
Track B (Team Async)    ──→ vaultspec-complex-executor
Track C (CLI/MCP)       ──→ vaultspec-standard-executor
Track D (Test Fixes)    ──→ vaultspec-standard-executor
```

Within Track A, steps 1a through 1f form a dependency chain: each step
depends on the prior one. Steps 1b and 1c could run in parallel after
1a completes; 1d can run in parallel with 1b/1c; 1e depends on 1a; 1f
depends on all prior steps.

```
Track A internal dependency graph:
  1a ──→ 1b ──→ 1c
    \──→ 1d
    \──→ 1e
              ──→ 1f (depends on 1a-1e)
```

Within Tracks B, C, and D, steps are sequential within each track but
tracks are independent of each other.

**Recommended sub-agent allocation:**

- Agent 1: Track A (6 steps, complex, critical path)
- Agent 2: Track B (3 steps, complex, new abstraction)
- Agent 3: Track C (4 steps, standard, additive flags)
- Agent 4: Track D (4 steps, standard/review, infrastructure)

## Verification

### Per-Phase Criteria

**Track A (Session Management):**

- `run_subagent()` calls `conn.resume_session()` when `resume_session_id`
  is provided, `conn.new_session()` otherwise

- `get_task_status` response includes `session_id` field

- `dispatch_agent` MCP tool accepts `resume_session_id` parameter

- `--resume-session` CLI flag is recognized and passed through

- Gemini A2A executor passes stored session ID on subsequent turns

- Multi-turn state tests assert `result2.session_id == result1.session_id`

**Track B (Team Async):**

- `dispatch_task`, `send_message`, `broadcast_message` return immediately
  with a `taskId` instead of blocking

- `get_team_task_status` tool exists and returns task state

- `relay_output` MCP tool is registered and functional

**Track C (CLI/MCP):**

- All 6 missing CLI flags are recognized by `vaultspec-subagent run --help`
- `vaultspec test` discovers tests in `src/vaultspec/**/tests/`
- `vaultspec-subagent a2a-serve --debug` no longer errors
- Team CLI commands exist and invoke `TeamCoordinator` methods

**Track D (Test Fixes):**

- `src/vaultspec/tests/__init__.py` exists
- `monkeypatch.chdir` is removed from `test_utils.py`
- `find_project_root()` accepts optional `start_dir` parameter
- Stale constants are removed from `tests/constants.py`
- `MEMORY.md` documents the `monkeypatch.setenv` policy

### Integration Verification

Run the full test suite after all tracks complete:

```bash
python -m pytest src/vaultspec/ tests/ -x --tb=short
```

The protocol isolation tests (`tests/protocol/isolation/`) are the
ultimate validation of Track A: they will exercise real session resume
across both providers. If `test_gemini_state_multi_turn` and
`test_claude_state_multi_turn` pass with the session ID assertion, the
end-to-end session management chain is proven correct.

Note: The protocol isolation tests require live API keys for Gemini and
Claude. They should be run in a CI environment with credentials or
manually verified during code review.
