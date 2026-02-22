---
tags:
  - "#exec"
  - "#protocol-stack"
date: "2026-02-22"
related:
  - "[[2026-02-22-protocol-stack-deep-audit-plan]]"
---

# `protocol-stack` Track A `Steps 1e-1f`

Fixed Gemini executor session reuse and updated multi-turn test assertions.

- Modified: `src/vaultspec/protocol/a2a/executors/gemini_executor.py`
- Modified: `tests/protocol/isolation/test_subagent_gemini.py`
- Modified: `tests/protocol/isolation/test_subagent_claude.py`

## Description

**Step 1e:** In `GeminiA2AExecutor.execute()`, before creating the subagent
task, look up stored session ID for the current `context_id` from
`self._session_ids` and pass it as `resume_session_id`. This aligns Gemini
executor with Claude executor behavior.

**Step 1f:** Added `assert result2.session_id == result1.session_id` to both
`test_gemini_state_multi_turn` and `test_claude_state_multi_turn`. This
verifies actual session resume — not just state retrieval.

## Tests

Multi-turn tests now validate the full session resume chain from step 1a
through 1e. No mocking — tests use real ACP connections.
