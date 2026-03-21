---
tags:
  - '#audit'
  - '#health'
date: '2026-02-18'
---

# Health Audit: protocol/ and subagent_server/

**Auditor:** investigator2
**Date:** 2026-02-18
**Scope:** `.vaultspec/lib/src/protocol/` (all subdirs) + `.vaultspec/lib/src/subagent_server/`
**Mandate:** READ-ONLY. No source modifications.

______________________________________________________________________

## Executive Summary

Both modules are well-architected and exhibit strong test discipline. The primary
architectural strength is pervasive constructor dependency injection (DI), which
eliminates the need for `unittest.mock` / `@patch` across all test files. Two
functional issues were identified: an `await`-missing bug in the `cancel()` path of
`ClaudeA2AExecutor`, and a `_noop` return type mismatch in several `dispatch_agent`
integration tests. Several minor quality issues (f-string logging anti-patterns,
dead commented-out code, duplicate test coverage, private API access) are catalogued
below.

______________________________________________________________________

## Files Audited

### protocol/ — source

| File                                        | Lines | Notes                                 |
| ------------------------------------------- | ----- | ------------------------------------- |
| `protocol/__init__.py`                      | 0     | empty                                 |
| `protocol/sandbox.py`                       | ~60   | shared sandboxing utilities           |
| `protocol/a2a/__init__.py`                  | 1     | doc-only                              |
| `protocol/a2a/agent_card.py`                | ~55   | AgentCard factory                     |
| `protocol/a2a/discovery.py`                 | ~80   | Gemini CLI discovery config generator |
| `protocol/a2a/server.py`                    | ~35   | ASGI server factory                   |
| `protocol/a2a/state_map.py`                 | ~35   | bidirectional state dicts             |
| `protocol/a2a/executors/base.py`            | ~15   | re-exports sandbox symbols            |
| `protocol/a2a/executors/claude_executor.py` | ~170  | ClaudeA2AExecutor — **BUG**           |
| `protocol/a2a/executors/gemini_executor.py` | ~130  | GeminiA2AExecutor                     |
| `protocol/acp/__init__.py`                  | 0     | empty                                 |
| `protocol/acp/types.py`                     | ~30   | SubagentError, SubagentResult         |
| `protocol/acp/client.py`                    | ~460  | SubagentClient — several style issues |
| `protocol/acp/claude_bridge.py`             | ~965  | ClaudeACPBridge — complex but clean   |
| `protocol/providers/base.py`                | ~130  | AgentProvider ABC, model constants    |
| `protocol/providers/claude.py`              | ~115  | ClaudeProvider                        |
| `protocol/providers/gemini.py`              | ~120  | GeminiProvider                        |

### protocol/ — tests

| File                                           | Notes                                                |
| ---------------------------------------------- | ---------------------------------------------------- |
| `protocol/tests/conftest.py`                   | `test_root_dir`, `test_agent_md` fixtures            |
| `protocol/tests/test_client.py`                | SubagentClient unit tests                            |
| `protocol/tests/test_providers.py`             | Both providers, `resolve_includes`, version checking |
| `protocol/tests/test_sandbox.py`               | `_is_vault_path`, `_make_sandbox_callback`           |
| `protocol/tests/test_fileio.py`                | Read-only file I/O enforcement                       |
| `protocol/tests/test_permissions.py`           | Permission denial scenarios                          |
| `protocol/a2a/tests/conftest.py`               | EchoExecutor, PrefixExecutor, a2a_server_factory     |
| `protocol/a2a/tests/test_unit_a2a.py`          | State mapping, executor in-process                   |
| `protocol/a2a/tests/test_agent_card.py`        | agent_card_from_definition unit tests                |
| `protocol/a2a/tests/test_discovery.py`         | discovery.py generation tests                        |
| `protocol/a2a/tests/test_claude_executor.py`   | ClaudeA2AExecutor with \_InProcessSDKClient          |
| `protocol/a2a/tests/test_gemini_executor.py`   | GeminiA2AExecutor with \_RunSubagentRecorder         |
| `protocol/a2a/tests/test_integration_a2a.py`   | Full HTTP stack via httpx.ASGITransport              |
| `protocol/a2a/tests/test_e2e_a2a.py`           | E2E real Claude/Gemini (gated)                       |
| `protocol/acp/tests/conftest.py`               | SDKClientRecorder, ConnRecorder, make_di_bridge      |
| `protocol/acp/tests/test_bridge_lifecycle.py`  | ~200 tests, constructor→session→config lifecycle     |
| `protocol/acp/tests/test_bridge_resilience.py` | Cancel, streaming errors, logging                    |
| `protocol/acp/tests/test_bridge_sandbox.py`    | Sandbox + \_is_vault_path                            |
| `protocol/acp/tests/test_bridge_streaming.py`  | _emit_\* methods, StreamEvent, JSON delta            |
| `protocol/acp/tests/test_client_terminal.py`   | Terminal sandbox enforcement                         |
| `protocol/acp/tests/test_e2e_bridge.py`        | Bridge subprocess spawn (integration+claude gated)   |

### subagent_server/ — source and tests

| File                                      | Lines | Notes                             |
| ----------------------------------------- | ----- | --------------------------------- |
| `subagent_server/__init__.py`             | 0     | empty                             |
| `subagent_server/server.py`               | ~664  | FastMCP server, 5 tools + helpers |
| `subagent_server/tests/conftest.py`       | 1     | empty (docstring only)            |
| `subagent_server/tests/test_helpers.py`   | ~85   | Helper unit tests                 |
| `subagent_server/tests/test_mcp_tools.py` | ~728  | Comprehensive MCP tool tests      |

______________________________________________________________________

## Code Quality

### Strengths

**1. Consistent Constructor DI throughout.**
All three executor/bridge classes (`ClaudeA2AExecutor`, `GeminiA2AExecutor`,
`ClaudeACPBridge`, `SubagentClient`) expose `*_factory` or `*_fn` constructor
parameters. This makes every class unit-testable without process spawning or
network access.

**2. Sandboxing is centralized.**
`protocol/sandbox.py` owns all sandbox logic. Both ACP and A2A layers import from
it. The logic is correct: write tools (`Write`, `Edit`, `MultiEdit`, `NotebookEdit`)
are blocked outside `.vault/`; shell tools (`Bash`) are unconditionally blocked in
read-only mode.

**3. `ClaudeACPBridge` is well-documented despite its size.**
At ~965 lines it is the most complex file in scope. Every method has a docstring.
The streaming event mapping via `_emit_stream_event` / `_emit_content_block_*` is
complex but all edge cases (tool_use_id correlation, `input_json_delta` replay) are
handled.

**4. `subagent_server/server.py` — pure-function extraction.**
`_prepare_dispatch_kwargs`, `_extract_artifacts`, `_merge_artifacts`,
`_inject_permission_prompt`, `_resolve_effective_mode`, `_parse_agent_metadata`,
`_parse_tools` are all extracted as pure (or near-pure) functions. This is the
correct approach for a module with module-level globals.

**5. `initialize_server()` for test injection.**
The server exposes `refresh_callback` and `run_subagent_fn` overrides in
`initialize_server()`. Tests use these to avoid spawning real subagents.

______________________________________________________________________

### Issues

#### ISSUE-1 (BUG — medium severity): Missing `await` on `disconnect()` in `cancel()` path

**File:** `protocol/a2a/executors/claude_executor.py`, lines 161–167

```python

# cancel() — lines 161-167

try:
    client.interrupt()
except Exception:
    logger.exception("Error interrupting SDK client for task %s", task_id)
try:
    client.disconnect()   # ← NOT awaited
except Exception:
    logger.exception("Error disconnecting SDK client for task %s", task_id)
```

In `execute()` (line 149), the same call is correctly awaited:

```python
await sdk_client.disconnect()   # ← correctly awaited
```

If `ClaudeSDKClient.disconnect()` is a coroutine, the `cancel()` path silently
drops the coroutine object on the floor — the connection is never actually closed.
The test double `_InProcessSDKClient.disconnect()` is synchronous, so the test
suite does not catch this. The fix is to make `cancel()` async (it is already
declared `async`) and add `await client.disconnect()`.

**Recommendation:** Change both `client.interrupt()` and `client.disconnect()` in
`cancel()` to be awaited, or verify that the real SDK methods are synchronous and
document this explicitly.

______________________________________________________________________

#### ISSUE-2 (BUG — low severity): `_noop` coroutine returns `None`, not `SubagentResult`

**File:** `protocol/a2a/tests/test_mcp_tools.py` — multiple `TestDispatchAgent`
integration tests (lines ~195–304)

Several integration tests inject:

```python
async def _noop(**_kw):
    pass   # returns None implicitly
```

as `srv._run_subagent_fn`. The real `run_subagent` returns a `SubagentResult`
(with `.response_text`, `.written_files`, `.session_id`). When the background
task runs and calls `result.response_text` on `None`, it raises `AttributeError`
— but this happens inside `asyncio.create_task`, so the exception is silently
swallowed by the background task. The tests assert only on the immediate return
value of `dispatch_agent()` (status="working") before the background task has
run, so they pass. However, the background task will always fail silently in
these tests.

**Recommendation:** Replace `_noop` with a stub that returns a minimal
`SubagentResult`:

```python
async def _noop_subagent(**_kw):
    from protocol.acp.types import SubagentResult
    return SubagentResult(response_text="ok", written_files=[], session_id=None)
```

______________________________________________________________________

#### ISSUE-3 (style): f-string anti-pattern in logging calls

**File:** `protocol/acp/client.py` (multiple lines — sample: 125, 193, 283, 357)
**File:** `subagent_server/server.py` (lines 283–284, 290)

```python
logger.warning(f"Agents directory not found: {AGENTS_DIR}")   # server.py:283
logger.warning(f"Failed to parse agent {agent_path.name}: {exc}")  # server.py:290
```

Python logging should use lazy `%`-style formatting so the string interpolation
is skipped when the log level is not active:

```python
logger.warning("Agents directory not found: %s", AGENTS_DIR)
logger.warning("Failed to parse agent %s: %s", agent_path.name, exc)
```

The `client.py` file has the most occurrences (~6 sites). `server.py` has 2.
These are style issues, not functional bugs, but they waste CPU when logging is
at WARNING level or above with many agents.

______________________________________________________________________

#### ISSUE-4 (dead code): Commented-out code blocks in `client.py`

**File:** `protocol/acp/client.py`, approx. lines 184–202

Three commented-out type annotations / code blocks referencing
`UserMessageChunk`, `ToolCallProgress`, `AgentPlanUpdate` appear to be stale
from a prior API version. They add noise and should be removed.

______________________________________________________________________

#### ISSUE-5 (design): Module-level globals in `subagent_server/server.py`

The server uses module-level globals (`ROOT_DIR`, `AGENTS_DIR`, `lock_manager`,
`task_engine`, `_refresh_fn`, `_run_subagent_fn`) initialized via
`initialize_server()`. This is a pragmatic choice for FastMCP but creates test
isolation risk: tests that manipulate `srv._agent_cache` directly must reset it
in teardown (the `_init_server` autouse fixture handles this, but it is fragile).

The `_init_server` fixture correctly resets `_agent_cache`, `_background_tasks`,
and `_active_clients` after each test. However, `srv.task_engine` and
`srv.lock_manager` are reset at the test method level (each test that needs a
fresh engine creates its own `fresh_task_engine` fixture and assigns
`srv.task_engine = fresh_task_engine`). This works but is not as clean as
constructor-based DI.

**Recommendation:** No immediate action required — the pattern is documented and
the autouse fixture provides adequate isolation. Consider extracting server state
into a `ServerState` dataclass if the module grows further.

______________________________________________________________________

#### ISSUE-6 (private API access): `_register_agent_resources` uses internal FastMCP

**File:** `subagent_server/server.py`, lines 304–321

```python
resources = mcp._resource_manager._resources   # private access
stale_keys = [k for k in resources if k.startswith("agents://")]
for k in stale_keys:
    del resources[k]
```

The comment on line 299 acknowledges this:

> "FastMCP ResourceManager has no public remove_resource() API.
> e access_esource_manager.\_resources (dict[str, Resource]) directly..."

This is a documented workaround. The fix is to upstream a `remove_resource()`
method to FastMCP, or track agent URIs separately and skip re-registration for
unchanged agents. Acceptable as-is given the pinned `mcp>=1.20.0`.

______________________________________________________________________

## Test Integrity

### Mock / Patch Usage

**ZERO** uses of `unittest.mock`, `MagicMock`, `patch`, or `@patch` across all
test files in scope. This was verified via manual inspection of all 21 test files.

All test isolation is achieved via:

`refresh_callback` params.

- **Custom test doubles** — `SDKClientRecorder`, `ConnRecorder`,
  `AsyncItemIterator`, `EchoExecutor`, `PrefixExecutor`, `_InProcessSDKClient`,
  `_RunSubagentRecorder`. All are handwritten in `conftest.py` files or inline
  in the test module.

- **Module-global injection** — `srv._agent_cache`, `srv._run_subagent_fn`,
  `srv.task_engine` set directly in test bodies, with reset in autouse fixture.

This is the correct approach for this codebase and fully consistent with the
project's anti-mock stance.

### Assertion Quality

No vacuous or trivially true assertions were found. Every test class has
well-scoped, named test methods with single-responsibility assertions. Return
values from `dispatch_agent()`, `get_task_status()`, etc. are deserialized via
`json.loads()` and asserted field-by-field.

### E2E Test Gating

E2E tests are properly gated:

- `test_e2e_a2a.py` — uses `requires_anthropic` / `requires_gemini` skip marks.
- `test_e2e_bridge.py` — marked `@pytest.mark.integration` and `@pytest.mark.claude`.
- Two stubs in `TestCancelTask` use `pytest.skip("requires ...")` directly
  (intentional, not a quality issue).

### Integration Test Marker Consistency

Several tests in `TestDispatchAgent` are marked `@pytest.mark.integration` but
do not actually perform integration-level operations — they inject `_noop` for
`run_subagent` and make no real external calls. The `integration` marker appears
to have been applied conservatively. This is not wrong but may cause these tests
to be excluded from fast unit test runs unnecessarily.

______________________________________________________________________

## Conftest.py Audit

### `protocol/tests/conftest.py`

Defines two shared fixtures:

and a `test.txt` file.

- `test_agent_md(test_root_dir)` — creates a `.vaultspec/agents/test-agent.md`
  file with valid frontmatter.

These fixtures are imported by tests in `protocol/tests/` and are also inherited
by tests in `protocol/acp/tests/` that reference `test_root_dir` (pytest walks
up the directory tree to find fixtures).

No duplicate fixture definitions in this conftest. No `sys.path` manipulation.

### `protocol/acp/tests/conftest.py`

Defines the most complex conftest in scope:

- `AsyncItemIterator` — async iterator test helper.

- `SDKClientRecorder` — records `connect()`, `query()`, `disconnect()`,
  `receive_messages()` calls. Custom test double.

- `ConnRecorder` — records ACP `request()` calls, returns configurable responses.

- `make_di_bridge()` — factory returning `(bridge, holder, captured_options)` —
  the primary pattern for ClaudeACPBridge unit tests.

- Fixtures: `bridge`, `bridge_debug`, `test_conn`, `connected_bridge`.

No `sys.path` manipulation. No `unittest.mock`. Clean.

### `protocol/a2a/tests/conftest.py`

Defines A2A-specific doubles:

- `PrefixExecutor(AgentExecutor)` — prepends a configurable prefix.

- `make_request_context(prompt, task_id, context_id)` — factory helper.

- `a2a_server_factory` — fixture returning a callable that creates a full ASGI
  app with an injected executor and AgentCard.

- `_make_card()` — helper to build a minimal `AgentCard`.

No `sys.path` manipulation. No `unittest.mock`. Clean.

### `subagent_server/tests/conftest.py`

**Empty** — contains only the module docstring `"""Subagent server unit test fixtures."""`.
All test isolation for `test_mcp_tools.py` is done via:

- Module-level `pytestmark`.
- Per-test `fresh_task_engine` fixture defined inline.

This is acceptable — the autouse fixture and test-local fixtures in
`test_mcp_tools.py` provide the necessary isolation without requiring a shared
conftest.

### Duplicate Fixture Coverage

`protocol/acp/tests/test_bridge_sandbox.py` re-tests `_is_vault_path` and
`_make_sandbox_callback` — the same functions already tested in
`protocol/tests/test_sandbox.py`. The ACP tests add no new edge cases beyond
what exists in the dedicated sandbox test module. This is benign duplication but
adds maintenance surface.

No duplicate fixture _names_ across sibling conftest files.

______________________________________________________________________

## Structural Rule Violations

### `unittest` / `MagicMock` / `@patch` usage

```
ZERO occurrences across all 21 test files.
```

Verified by manual inspection of every test file in scope.

### `sys.path.insert()` in conftest files

```
ZERO occurrences across all 4 conftest files.
```

Consistent with the centralized path management convention established in
`pyproject.toml` and `lib/tests/constants.py`.

### Import pattern compliance

All test files use:

```python
from tests.constants import TEST_PROJECT
```

Not local `Path(...)` definitions. Confirmed in `test_mcp_tools.py` (line 29).

### pytest marker discipline

- All unit tests in `test_helpers.py` and `test_mcp_tools.py` are marked
  `pytest.mark.unit` via `pytestmark`.

- Integration and E2E tests carry `pytest.mark.integration` and appropriate
  model markers (`claude`, `gemini`).

- No `@pytest.mark.slow` usage found (correctly replaced with `quality`).

______________________________________________________________________

## Summary Table

| Category                    | Status | Details                                         |
| --------------------------- | ------ | ----------------------------------------------- |
| Code quality                | GOOD   | Clean DI architecture, extracted pure helpers   |
| Test integrity              | GOOD   | Zero mock/patch, all custom test doubles        |
| Conftest hygiene            | GOOD   | No duplicate fixture names, no sys.path         |
| Structural rules            | PASS   | No unittest imports, no sys.path in conftest    |
| BUG: cancel() missing await | FAIL   | `claude_executor.py` cancel path                |
| BUG: \_noop returns None    | WARN   | Test stubs in dispatch_agent integration tests  |
| Style: f-string logging     | WARN   | `client.py` (~6 sites), `server.py` (2 sites)   |
| Dead code                   | WARN   | Commented-out blocks in `client.py`             |
| Private API access          | WARN   | `mcp._resource_manager._resources` (documented) |

| Integration marker overuse | INFO | Some dispatch_agent tests marked integration unnecessarily |
| Duplicate sandbox coverage | INFO | test_bridge_sandbox.py overlaps test_sandbox.py |

______________________________________________________________________

## Recommended Actions

**Priority 1 (fix):**

- `protocol/a2a/executors/claude_executor.py` — Add `await` to `client.disconnect()`
  in the `cancel()` method (ISSUE-1).

**Priority 2 (fix):**

- `subagent_server/tests/test_mcp_tools.py` — Replace `_noop` stubs with
  `SubagentResult`-returning coroutines in integration dispatch tests (ISSUE-2).

**Priority 3 (cleanup):**

- `protocol/acp/client.py` — Remove dead commented-out code blocks (ISSUE-4).
- `protocol/acp/client.py` and `subagent_server/server.py` — Convert f-string
  logging to `%`-style lazy formatting (ISSUE-3).

**Priority 4 (low, no action required):**

- ISSUE-5: Module-level globals in server.py — acceptable, documented.
- ISSUE-6: Private FastMCP API access — acceptable, documented workaround.
