---
tags:
  - '#exec'
  - '#pytest-e2e'
date: '2026-02-21'
related:
  - '[[2026-02-21-pytest-e2e-observability-impl-plan]]'
---

# `pytest-e2e` `impl` `phase2`

Instrumented E2E test classes with retry markers and structured logging.
Removed `pytest-harvest` (`results_bag`) due to incompatibility with
`@flaky` reruns.

- Modified: `test_e2e_a2a.py`
- Modified: `test_french_novel_relay.py`
- Modified: `pyproject.toml`

## Description

Step 2.1: Added `@pytest.mark.flaky(reruns=2, reruns_delay=5)` to four classes:
`TestClaudeE2E`, `TestGeminiE2E`, `TestGoldStandardBidirectional` (in
`test_e2e_a2a.py`), and `TestFrenchNovelRelayLive` (in
`test_french_novel_relay.py`). `TestClaudeA2AExecutor` in
`test_claude_executor.py` was intentionally excluded — it uses in-process DI,
not real LLM calls.

Step 2.2: Initially added `results_bag` fixture from `pytest-harvest` to all
E2E test methods. During live validation against real Claude, discovered
`results_bag` throws `KeyError` on rerun attempts by `pytest-rerunfailures`
(`"Internal Error - This fixture 'results_bag' was already stored for test id..."`). The two plugins are fundamentally incompatible. Replaced all
`results_bag` attribute assignments with structured `logger.info(...)` calls
capturing the same data (latency, model, state). Removed `pytest-harvest`
from `pyproject.toml` dependencies entirely.

Step 2.3: Added `import logging` and `logger = logging.getLogger(__name__)` to
both test files. Added `logger.info(...)` calls before each LLM API request
and after each response with agent name, model, state, and elapsed time.

## Tests

Real E2E validation run against Claude confirmed the observability stack works:
1066 DEBUG-level lines captured in `test-debug.log`, real-time JSONL events
in `test-events.jsonl`. Rate limit error (`rate_limit_event`) surfaced with
full traceback — exactly the visibility improvement targeted by this plan.

After removing `pytest-harvest`, fast suite: 381 passed, 22 deselected, 4.05s.
