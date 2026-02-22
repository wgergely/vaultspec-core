---
tags:
  - "#exec"
  - "#gemini-acp-bridge"
date: "2026-02-22"
related:
  - "[[2026-02-22-gemini-acp-bridge-plan]]"
  - "[[2026-02-22-gemini-overhaul-adr]]"
  - "[[2026-02-22-gemini-acp-bridge-review]]"
  - "[[2026-02-22-gemini-overhaul-reference]]"
  - "[[2026-02-22-gemini-acp-audit-research]]"
  - "[[2026-02-22-gemini-acp-audit-expanded]]"
---

# `gemini-acp-bridge` code review (post-rewrite)

**Status:** `PASS`

## Audit Context

- **Plan:** `[[2026-02-22-gemini-acp-bridge-plan]]`
- **ADR:** `[[2026-02-22-gemini-overhaul-adr]]` (Decisions 1, 2, 3, 4, 7)
- **Pre-rewrite review:** `[[2026-02-22-gemini-acp-bridge-review]]` (status: FAIL)
- **Scope:**
  - `src/vaultspec/protocol/acp/gemini_bridge.py` (876 lines -- full rewrite)
  - `src/vaultspec/protocol/acp/tests/test_gemini_bridge.py` (556 lines -- full rewrite)
  - `src/vaultspec/protocol/acp/__init__.py` (export update)

## Test Results

All 25 tests pass:

```
src/vaultspec/protocol/acp/tests/test_gemini_bridge.py  25 passed in 0.17s
```

Test breakdown by category:
- Lifecycle: 8 tests (initialize, new_session, prompt, cancel, cancel-during-prompt, authenticate, close, no-get-config)
- Normalization: 5 tests (tool kind mapping, diff generation, content accumulation, TodoWrite-to-plan, TodoWrite progress suppression)
- Session management: 12 tests (list_sessions, list_sessions_filter, fork, fork_unknown, load_alive, load_dead, load_unknown, resume, set_mode, set_model, ext_method, ext_notification)

## ADR Compliance: Decision-by-Decision Assessment

### Decision 1: Full Rewrite -- COMPLIANT

The implementation is a clean rewrite. Preserved elements verified:

- `_map_tool_kind()` (lines 80-95): Correctly carried over, matches Claude bridge.
- `_get_tool_call_content()` (lines 98-129): Correctly carried over with Gemini-specific `"replace"` tool name addition (appropriate adaptation).
- `GeminiProxyClient` pattern (lines 167-248): Structurally correct with clean shutdown path added (`start()` returns task, worker breaks on `CancelledError`).
- `_SessionState` dataclass (lines 137-159): Expanded with all required fields.

Replaced elements verified:

- Constructor uses `spawn_fn` DI (line 306) -- no `get_config()` coupling anywhere in the module.
- No `McpCapabilities` reference -- completely removed.
- No synchronous version check (`subprocess.run`) -- completely removed.
- No Windows `cmd.exe /c` workaround -- completely removed.
- No `os.environ.copy()` -- the module uses `os.environ.get()` for config only, lets SDK handle env trimming.
- Background tasks tracked in `_SessionState.background_tasks` and cleaned up in `_cleanup_session()`.

### Decision 2: 15 Agent Protocol Methods -- COMPLIANT

All 15 methods verified present with correct signatures:

| Method | Line | Signature | Status |
|--------|------|-----------|--------|
| `on_connect` | 347 | `(self, conn: Any) -> None` | Present |
| `initialize` | 353 | `(self, protocol_version, client_capabilities, client_info, **kwargs) -> InitializeResponse` | Present |
| `new_session` | 484 | `(self, cwd, mcp_servers, **kwargs) -> NewSessionResponse` | Present |
| `prompt` | 504 | `(self, prompt, session_id, **kwargs) -> PromptResponse` | Present |
| `cancel` | 633 | `(self, session_id, **kwargs) -> None` | Present |
| `authenticate` | 650 | `(self, method_id: str, **kwargs) -> AuthenticateResponse or None` | Present |
| `load_session` | 663 | `(self, cwd, session_id, mcp_servers, **kwargs) -> LoadSessionResponse or None` | Present |
| `resume_session` | 718 | `(self, cwd, session_id, mcp_servers, **kwargs) -> ResumeSessionResponse` | Present |
| `list_sessions` | 735 | `(self, cursor, cwd, **kwargs) -> ListSessionsResponse` | Present |
| `fork_session` | 758 | `(self, cwd, session_id, mcp_servers, **kwargs) -> ForkSessionResponse` | Present |
| `set_session_mode` | 789 | `(self, mode_id, session_id, **kwargs) -> None` | Present |
| `set_session_model` | 802 | `(self, model_id, session_id, **kwargs) -> None` | Present |
| `set_config_option` | 815 | `(self, config_id, session_id, value, **_kwargs) -> None` | Present |
| `ext_method` | 826 | `(self, method, params) -> dict[str, Any]` | Present |
| `ext_notification` | 833 | `(self, method, params) -> None` | Present |

Capability declaration matches ADR spec:

```python
AgentCapabilities(
    load_session=True,
    session_capabilities=SessionCapabilities(
        fork=SessionForkCapabilities(),
        list=SessionListCapabilities(),
        resume=SessionResumeCapabilities(),
    ),
    prompt_capabilities=PromptCapabilities(
        image=True,
        audio=True,
        embedded_context=True,
    ),
)
```

No `McpCapabilities` -- correct per ADR rationale.

### Decision 3: Subprocess Lifecycle -- COMPLIANT

Spawn flow in `_spawn_child_session()` (lines 381-469) verified:

1. CLI resolution via `shutil.which("gemini")` with `gemini_path` override -- correct.
2. `FileNotFoundError` raised with actionable message if CLI not found -- correct.
3. Args built correctly: `--experimental-acp`, `--model`, optional `--sandbox`, `--allowed-tools`, `--approval-mode`, `--output-format`.
4. Spawn via `self._spawn_fn(proxy_client, gemini_path, *args, cwd=cwd)` using `AsyncExitStack` -- correct.
5. Background tasks tracked: proxy worker task and stderr reader both added to `state.background_tasks`.
6. ACP handshake performed: `child_conn.initialize()` then `child_conn.new_session()`.
7. No `os.environ.copy()`, no synchronous `subprocess.run`, no Windows `cmd.exe` workaround.

### Decision 4: Session Resume -- COMPLIANT

`_SessionState` fields verified (lines 137-159):

- `session_id`, `cwd`, `model`, `mode`, `child_conn`, `child_proc`, `child_session_id`, `exit_stack` -- required fields present.
- `gemini_session_id: str | None = None` -- present.
- `mcp_servers: list[Any]` -- present.
- `background_tasks: list[asyncio.Task[None]]` -- present.
- `created_at: str` -- present with ISO timestamp factory.
- `cancel_event: asyncio.Event` -- present.
- `tool_call_contents: dict[str, list[Any]]` -- present.
- `todo_write_tool_call_ids: set[str]` -- present.

Session management methods verified:

- `load_session` (lines 663-714): Three-branch logic (not found -> recovery spawn, alive -> reuse, dead -> cleanup + respawn). Correct.
- `resume_session` (lines 718-731): Delegates to `load_session`, returns `ResumeSessionResponse`. Correct.
- `list_sessions` (lines 735-754): Iterates `_sessions`, filters by `cwd`, returns `SessionInfo` list. Correct.
- `fork_session` (lines 758-785): Clones source config, spawns new child, assigns new UUID. Correct.

### Decision 7: DI Pattern -- COMPLIANT

Constructor (lines 301-343) accepts:

- `model: str = GeminiModels.LOW` -- correct.
- `debug: bool = False` -- correct.
- `spawn_fn: Callable[..., Any] | None = None` -- correct, defaults to `spawn_agent_process`.
- Additional config params (`gemini_path`, `mode`, `root_dir`, `allowed_tools`, `approval_mode`, `output_format`) with env var fallbacks -- correct, decouples from `get_config()`.

Test DI verified:

- `mock_spawn_fn` (test line 73-80): Plain async context manager, no mocking.
- `capturing_spawn_fn` (test line 131-136): Records args, returns fakes.
- `MockChildConn`, `MockChildProc` (test lines 36-71): Plain classes, no `unittest.mock`, no `monkeypatch`.
- Constructor injection via `spawn_fn=mock_spawn_fn` in fixture (test line 102).

## Pre-Rewrite Issue Resolution

Checklist cross-referencing all CRITICAL and HIGH findings from `[[2026-02-22-gemini-acp-bridge-review]]`:

| ID | Severity | Issue | Status |
|----|----------|-------|--------|
| F-01 | CRITICAL | `McpCapabilities` NameError | RESOLVED -- removed entirely, not imported or referenced |
| F-02 | CRITICAL | `authenticate()` missing `method_id` | RESOLVED -- signature is `(self, method_id: str, **kwargs)` at line 650 |
| F-03 | CRITICAL | All tests fail at fixture setup (`spawn_fn` not accepted) | RESOLVED -- constructor accepts `spawn_fn`, all 25 tests pass |
| F-04 | CRITICAL | Missing 9/15 protocol methods | RESOLVED -- all 15 methods implemented |
| F-05 | HIGH | No DI mechanism for subprocess spawning | RESOLVED -- `spawn_fn` parameter with default |
| F-06 | HIGH | `prepare_process` not updated (out of scope for Phase 1) | N/A -- Phase 1 is bridge rewrite only; provider integration is separate |
| F-07 | HIGH | `GeminiACPBridge` not exported from `__init__.py` | RESOLVED -- exported in `__init__.py` line 5, in `__all__` line 10 |
| F-08 | HIGH | No session persistence in executor (out of scope for Phase 1) | N/A -- executor hardening is Decision 5, separate phase |
| F-09 | HIGH | `SessionCapabilities` advertises `fork=None, list=None, resume=None` | RESOLVED -- uses `SessionForkCapabilities()`, `SessionListCapabilities()`, `SessionResumeCapabilities()` |
| F-10 | HIGH | 17 unused imports | RESOLVED -- only 2 minor unused imports remain (see LOW findings below) |
| F-11 | MEDIUM | `subprocess` imported inside function body | RESOLVED -- `subprocess` no longer imported at all |
| F-12 | MEDIUM | Fire-and-forget `asyncio.create_task` without tracking | RESOLVED -- tasks tracked in `_SessionState.background_tasks`, cleaned up in `_cleanup_session()` |
| F-13 | MEDIUM | `GeminiProxyClient._worker` infinite loop without clean shutdown | RESOLVED -- worker task returned by `start()`, tracked in background_tasks, cancelled on cleanup |
| F-14 | MEDIUM | `TodoWrite` silently dropped | RESOLVED -- converted to `AgentPlanUpdate` with `PlanEntry` objects (lines 575-598) |
| F-15 | MEDIUM | Prompt serialization sends raw pydantic models | RESOLVED -- prompt passed directly to child via `child_conn.prompt()` (line 521-523), no manual serialization |
| F-17 | LOW | No doc comments on public methods | RESOLVED -- all public methods have docstrings |
| F-18 | LOW | Constructor differs from Claude bridge DI pattern | RESOLVED -- follows DI pattern with `spawn_fn` and env-var config |

## Findings

### Critical / High (Must Fix)

No CRITICAL or HIGH issues found.

### Medium / Low (Recommended)

- **[LOW] F-01** `gemini_bridge.py:38,57`: Two unused imports: `ContentToolCallContent` and `TextContentBlock` are imported from `acp.schema` but never referenced in the module body. They appear in the test file but are imported there independently. Removing them would clean up the import block. Note that `PlanEntryStatus`, `PlanEntryPriority`, and `ToolKind` appear unused to AST analysis but are actually used via `cast()` string references, so those are correctly imported.

- **[LOW] F-02** `gemini_bridge.py:504-506`: The `prompt()` method accepts `prompt: list[Any]` instead of the full union type `list[TextContentBlock | ImageContentBlock | AudioContentBlock | ResourceContentBlock | EmbeddedResourceContentBlock]` specified by the `Agent` protocol. This works at runtime because the ACP SDK uses dynamic dispatch, but it sacrifices static type safety. The Claude bridge also uses the full union type. This is a minor typing inconsistency.

- **[LOW] F-03** `gemini_bridge.py:347`: The `on_connect` parameter is typed as `conn: Any` instead of `conn: Client` (from `acp.interfaces`). The Claude bridge also uses `conn: Any`, so this is consistent, but both diverge from the protocol definition. Very low priority.

- **[LOW] F-04** `test_gemini_bridge.py:36,61`: Test double naming uses `Mock` prefix (`MockChildConn`, `MockChildProc`). While these are genuine DI test doubles (plain classes, no mocking framework), the `Mock` prefix may create confusion with the project's no-mocking policy. Consider renaming to `FakeChildConn` / `FakeChildProc` to align with ADR Decision 7's `_FakeSpawnFn` naming convention.

## Test Coverage Assessment

The test suite provides good coverage of the critical paths:

**Well covered:**
- Initialize with capability verification
- New session with flag passthrough
- Prompt proxying to child connection
- Cancel with event set and child delegation
- Cancel-during-prompt race condition (important correctness test)
- Authenticate with correct `method_id` signature
- Close with session cleanup
- Config independence from `get_config()`
- Tool kind mapping, diff generation, content accumulation
- TodoWrite-to-AgentPlanUpdate conversion and progress suppression
- Session management: list, filter, fork, fork_unknown, load (alive/dead/unknown), resume
- Set mode, set model, ext_method, ext_notification

**Not explicitly covered but acceptable:**
- `_cleanup_session()` task cancellation -- exercised indirectly through `close()` and `load_session` (dead child respawn)
- `GeminiProxyClient` proxy methods (`request_permission`, `read_text_file`, etc.) -- pass-through to `bridge._conn`, would require deeper integration tests
- `main()` entry point -- CLI integration, not unit-testable
- Stderr reading in `_spawn_child_session` -- requires real process, appropriate for E2E testing
- Error paths in `forward_update` when `_conn` is None -- defensive code, low risk

## Recommendations

No blocking issues. The following are optional quality improvements:

- Remove the two unused imports (`ContentToolCallContent`, `TextContentBlock`) from `gemini_bridge.py`.
- Consider renaming `MockChildConn`/`MockChildProc` to `FakeChildConn`/`FakeChildProc` for consistency with the DI naming convention.
- Consider adding the full type annotation to `prompt()` for static type safety.

## Notes

This is a substantial improvement from the pre-rewrite state. The previous review found 4 CRITICAL and 6 HIGH issues across a 383-line scaffold that was non-functional (runtime crash on `initialize()`, all tests failing). The rewrite is a 876-line implementation that passes all 25 tests, implements all 15 protocol methods, follows the Claude bridge patterns, uses clean DI for testability, and resolves every issue from the pre-rewrite review. The code is well-structured with clear separation between helpers, session state, proxy client, and protocol methods. Docstrings are present on all public methods. The only findings are LOW-severity style and typing nitpicks.
