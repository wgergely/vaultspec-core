---
tags:
  - "#plan"
  - "#team-hardening"
date: "2026-02-23"
related:
  - "[[2026-02-23-task-tool-dispatch-research]]"
  - "[[2026-02-22-protocol-stack-deep-audit-research]]"
  - "[[2026-02-21-a2a-layer-audit-research]]"
  - "[[2026-02-20-a2a-team-p1-plan]]"
---
# team-hardening phase-1 plan

Fix the three remaining bugs that block real team functionality in the A2A multi-agent system. Each bug is independently scoped and can be fixed in parallel. All three must pass before the team feature is considered production-ready.

## Proposed Changes

Three bugs were identified during live A2A team testing and cross-referenced against reference implementations (`tmp-ref/adk-python`, `tmp-ref/a2a-python-sdk`, `tmp-ref/acp-python-sdk`, `tmp-ref/a2a-samples`).

### Bug C1 — Claude executor fails inside Claude Code session

**Symptom**: `ClaudeA2AExecutor` fails when the parent process is a Claude Code session (i.e., `CLAUDECODE` env var is set). The executor strips `CLAUDECODE` from the env dict, but the ordering is fragile: `options.env = sdk_env` is assigned *after* `self._options_factory(**kwargs)` already captured `os.environ`. Any code path that reads env at construction time will see the unstripped env.

**Root cause**: In `src/vaultspec/protocol/a2a/executors/claude_executor.py:176-204`, the clean `sdk_env` is computed and assigned to `options.env` *after* `_options_factory` has already been called. The `ClaudeAgentOptions` constructor likely reads env vars at construction, not at connect time.

**Fix**: Move the env stripping into `kwargs` *before* `_options_factory()` is called, so the options object is constructed with the clean env from the start:
- Compute `sdk_env` at line ~176, before `kwargs` is assembled.
- Pass `env=sdk_env` in `kwargs` so `_options_factory(**kwargs)` receives it.
- Remove the post-construction `options.env = sdk_env` assignment.
- Add a fallback in `GeminiACPBridge` / `ClaudeACPBridge` that also strips `CLAUDECODE` from child process env (belt-and-suspenders for the bridge subprocess path).

**Files**:
- `src/vaultspec/protocol/a2a/executors/claude_executor.py` (lines 176–204)
- `src/vaultspec/protocol/acp/claude_bridge.py` (env forwarding in `_spawn_child_session`)

**Tests**:
- `src/vaultspec/protocol/a2a/tests/test_claude_executor.py` — add test asserting `CLAUDECODE` absent from options env even when set in `os.environ`
- Test that `connect()` succeeds when `CLAUDECODE=1` is in `os.environ`

---

### Bug C2 — Gemini session resume → "Method not found"

**Symptom**: On the second A2A call to the same `context_id`, `GeminiA2AExecutor` passes `resume_session_id` to `run_subagent()`. `run_subagent` calls `conn.resume_session(...)` over the ACP connection. Gemini CLI's ACP server rejects with "Method not found".

**Root cause**: `resume_session` is a real ACP method but is gated as `unstable=True` in `tmp-ref/acp-python-sdk/src/acp/agent/router.py:72`. The ACP connection is opened with `use_unstable_protocol=False` (the default), so the method is rejected by the router. More importantly, `resume_session` is the *wrong* mechanism for A2A multi-turn: the canonical pattern (ADK reference: `tmp-ref/adk-python/src/google/adk/a2a/converters/request_converter.py:111`) uses `context_id` → `session_id` get-or-create at the server side. No client-side session resume is needed or appropriate.

**Fix**: Remove the `_session_ids` cache and `resume_session_id` forwarding from `GeminiA2AExecutor`. Each A2A turn spawns a fresh Gemini ACP session (`new_session`). Multi-turn continuity is the responsibility of the server-side `GeminiACPBridge`, which already implements `load_session` / `resume_session` for the ACP-level persistence — that is a separate concern from A2A task dispatch.

**Files**:
- `src/vaultspec/protocol/a2a/executors/gemini_executor.py`
  - Remove `self._session_ids: dict[str, str] = {}` (line 128)
  - Remove `self._session_ids_lock = asyncio.Lock()` (line 129)
  - Remove the `async with self._session_ids_lock: prev_session = ...` block (lines 173–174)
  - Remove `resume_session_id=prev_session` kwarg from `self._run_subagent(...)` call (line 182)
  - Remove the `if result.session_id:` block that caches the session (lines 259–261)

**Tests**:
- `src/vaultspec/protocol/a2a/tests/test_gemini_executor.py`
  - Add test: second call to same `context_id` does NOT pass `resume_session_id`
  - Verify `run_subagent` is called with `resume_session_id=None` (or absent) on second turn
  - Add test that `_session_ids` attribute does not exist on executor (regression guard)

---

### Bug M1 — Agent name collision silently collapses mixed teams

**Symptom**: When two agents with the same `card.name` are added to a team (e.g., two `"Research Agent"` instances at different URLs), the second one silently overwrites the first in `members` dict. The team loses a member with no error.

**Root cause**: In `src/vaultspec/orchestration/team.py:487-493`, members are keyed by `card.name or url`. `AgentCard.name` is a human-readable display label, not a unique identity. All reference implementations (`tmp-ref/adk-python`, `tmp-ref/a2a-python-sdk`) have the same issue: `AgentCard` has no stable unique identifier beyond URL. URL is the correct unique key.

**Fix**: Key members by `card.url` (normalized, stripped of trailing slash). Keep `card.name` only for display/logging. The `TeamMember.name` field should remain the human-readable name but the dict key should be URL-based.

**Files**:
- `src/vaultspec/orchestration/team.py`
  - Line 487: change `member_name = card.name or url` to `member_key = url.rstrip("/")`
  - Line 488: change `members[member_name]` to `members[member_key]`
  - Line 489: `name=card.name or url` (preserve display name in struct)
  - Line 497: log uses `card.name` for readability, key uses URL
- Anywhere `session.members[name]` is used to look up by name must be updated to look up by URL key, or a secondary name-to-url index must be maintained for display purposes.

**Tests**:
- `src/vaultspec/orchestration/tests/test_team.py`
  - Add test: two agents with same `card.name` at different URLs → both present in `members`
  - Add test: lookup by URL key succeeds after form_team
  - Add test: `TeamMember.name` still holds the display name from `card.name`

---

## Tasks

- `phase-1: Bug C2 (Gemini session resume)`
    1. Remove `_session_ids` cache fields from `GeminiA2AExecutor.__init__`
    2. Remove `prev_session` lookup and `resume_session_id` kwarg from `execute()`
    3. Remove session caching in success path
    4. Update `test_gemini_executor.py` with regression tests

- `phase-2: Bug M1 (Name collision)`
    1. Change member dict key from `card.name` to normalized URL in `team.py`
    2. Audit all `session.members[x]` access sites for key type assumptions
    3. Update `test_team.py` with collision tests

- `phase-3: Bug C1 (Claude executor env ordering)`
    1. Move `sdk_env` construction before `kwargs` assembly in `claude_executor.py`
    2. Pass `env=sdk_env` in kwargs so `_options_factory` receives clean env
    3. Remove post-construction `options.env = sdk_env` assignment
    4. Add belt-and-suspenders env strip in `claude_bridge.py` child spawn
    5. Update `test_claude_executor.py` with env-stripping tests

## Parallelization

Phase 1 (C2) and Phase 2 (M1) are fully independent — no shared files. They can be worked in parallel by separate agents.

Phase 3 (C1) touches `claude_executor.py` which is separate from both. It can also run in parallel, but requires live diagnosis to confirm the exact root cause before committing a fix. Recommend starting Phase 3 after Phase 1 and Phase 2 are green, to reduce noise during root-cause investigation.

## Verification

Mission success requires:

1. **Unit tests pass** for all three modified executor/team files with no new skips or mocks.
2. **Regression guard**: `GeminiA2AExecutor` test confirms `resume_session_id` is never forwarded on second turn.
3. **Name collision guard**: `test_team.py` confirms two same-named agents at different URLs both survive `form_team`.
4. **Env stripping guard**: `test_claude_executor.py` confirms `CLAUDECODE` is absent from the options object at construction time, not just after `connect()`.
5. **Integration**: `test_integration_a2a.py` and `test_team_lifecycle.py` pass without modification.
6. **Live smoke test** (if possible): `vaultspec team create` with two agents at different URLs, verify both members appear in `list` output.

Note: Bug C1 may require live diagnosis under a real Claude Code session to confirm the exact failure mode. If the env-ordering fix does not resolve it, deeper investigation of `ClaudeAgentOptions` constructor behavior is required before marking C1 resolved.
