---
tags:
  - "#exec"
  - "#pytest-e2e"
date: "2026-02-21"
related:
  - "[[2026-02-21-pytest-e2e-observability-impl-plan]]"
  - "[[2026-02-21-pytest-e2e-observability-adr]]"
  - "[[2026-02-21-pytest-e2e-impl-phase1]]"
  - "[[2026-02-21-pytest-e2e-impl-phase2]]"
  - "[[2026-02-21-pytest-e2e-impl-phase3]]"
---

# `pytest-e2e` `impl` summary

Added an observability and reliability stack for long-running A2A/E2E tests.
Three new pytest plugins, built-in live logging, advanced timeout config,
retry markers, and structured logging for LLM metrics capture.

- Modified: `[[pyproject.toml]]`
- Modified: `[[test_e2e_a2a.py]]`
- Modified: `[[test_french_novel_relay.py]]`
- Modified: `[[.gitignore]]`

## Description

Implemented the full plan from [[2026-02-21-pytest-e2e-observability-impl-plan]]
across three phases:

**Phase 1 — Infrastructure**: Added live logging config (`log_cli`,
`log_file`), timeout config (`timeout=300`, `timeout_func_only=true`), and
the `flaky` marker to `[tool.pytest.ini_options]`. Added three new test
dependencies: `pytest-rerunfailures`, `pytest-reportlog`, `pytest-durations`.

**Phase 2 — Test instrumentation**: Applied `@pytest.mark.flaky(reruns=2,
reruns_delay=5)` to four E2E test classes. Added structured `logger.info()`
calls at every LLM API call site (before request, after response) capturing
latency, model, and state.

**Deviation from plan**: `pytest-harvest` (`results_bag`) was rejected during
live validation. The `results_bag` fixture throws `KeyError` on rerun attempts
by `pytest-rerunfailures` — the two plugins are fundamentally incompatible.
Replaced with structured logging. ADR updated to reflect this decision.

**Phase 3 — Housekeeping**: Added `test-events.jsonl` to `.gitignore`.
Verified full fast suite (381 passed, 22 deselected, 4.05s) and E2E test
collection (12 tests, no import errors).

## Tests

- **Fast suite**: 381 passed, 22 deselected, 2 warnings, 4.05s — no regressions.
- **E2E collection**: 12 tests collected without errors across `test_e2e_a2a.py`
  and `test_french_novel_relay.py`.
- **Live validation**: Real E2E run against Claude (`TestClaudeE2E`) confirmed
  the observability stack works — 1066 DEBUG lines captured in `test-debug.log`,
  real-time JSONL events in `test-events.jsonl`, rate limit error surfaced with
  full traceback. The `@flaky` retry mechanism triggered correctly on transient
  failure.
