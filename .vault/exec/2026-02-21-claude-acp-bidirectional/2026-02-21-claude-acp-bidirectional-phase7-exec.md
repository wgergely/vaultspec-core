---
tags:
  - '#exec'
  - '#claude-acp-bidirectional'
date: '2026-02-21'
related:
  - '[[2026-02-21-claude-acp-bidirectional-impl-plan]]'
  - '[[2026-02-21-claude-acp-bidirectional-phases1-6]]'
---

# `claude-acp-bidirectional` Phase 7 — Test Updates

Test alignment for all 6 ADR decisions implemented in Phases 1-6.

- Modified: `src/vaultspec/protocol/acp/tests/test_bridge_lifecycle.py`
- Validated: `src/vaultspec/protocol/acp/tests/test_bridge_resilience.py`
- Validated: `src/vaultspec/protocol/acp/tests/test_bridge_streaming.py`

## Description

### Step 1: Fix Failing Cancel Test (ADR Decision 5)

- Renamed `test_cancel_marks_session_disconnected` → `test_cancel_sets_cancel_event_keeps_connected`
- Updated assertions: cancel now sets `cancel_event` but keeps `connected=True` (non-destructive)
- This was the only failing test from the Phase 1-6 implementation

### Existing Test Coverage (Added During Phases 1-6)

Tests were added inline during implementation. Coverage summary:

**Cancel/Abort (ADR Decision 5) — 7 tests in `test_bridge_resilience.py`:**

- `test_cancel_sets_flag` — bridge-level `_cancelled` flag
- `test_cancel_sets_flag_with_session` — per-session `cancel_event`
- `test_cancel_flag_set_before_interrupt` — ordering guarantee
- `test_prompt_resets_cancelled_flag` — `cancel_event` reset on new prompt
- `test_cancelled_during_streaming_returns_cancelled` — stop_reason mapping
- `test_cancelled_skips_emit_for_remaining_messages` — stream suppression
- `test_cancel_then_new_prompt_works_normally` — session stays alive
- `test_cancel_does_not_disconnect` — no disconnect, no state mutation

**TodoWrite-to-Plan (ADR Decision 4) — 3 tests in `test_bridge_streaming.py`:**

- `test_emit_assistant_intercepts_todo_write` — AgentPlanUpdate emission
- `test_emit_stream_event_intercepts_todo_write` — stream-level interception
- `test_emit_user_message_suppresses_todo_write` — result suppression

**Content Accumulation & Kind Mapping (ADR Decision 3) — 2 tests in `test_bridge_streaming.py`:**

- `test_emit_assistant_accumulates_content` — diff content, kind mapping, raw_input
- `test_emit_user_message_accumulates_result` — result content, raw_output

**Error Handling (ADR Decision 6) — 2 tests in `test_bridge_streaming.py`:**

- `test_error_result_sets_end_turn` — `is_error` returns `"end_turn"` not `"refusal"`
- `test_exception_sets_end_turn` — generic exception returns `"end_turn"`

## Results

- **225/225** ACP bridge unit tests pass
- **260/261** total protocol tests pass (1 pre-existing E2E failure: `test_claude_a2a_responds` — upstream `rate_limit_event` bug)
