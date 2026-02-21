---
tags:
  - "#plan"
  - "#pytest-e2e"
date: "2026-02-21"
related:
  - "[[2026-02-21-pytest-e2e-observability-adr]]"
  - "[[2026-02-21-pytest-e2e-observability-research]]"
---

# `pytest-e2e` `impl` plan

Add an observability and reliability stack for long-running A2A/E2E tests per
[[2026-02-21-pytest-e2e-observability-adr]]. Four new pytest plugins, built-in
live logging, advanced timeout config, retry markers, and metrics capture.

## Proposed Changes

The ADR specifies seven implementation items. This plan groups them into three
phases: infrastructure (config + deps), test instrumentation (markers +
metrics), and housekeeping (gitignore + verification).

All changes are additive — no existing test logic is modified, only markers and
fixtures are added to existing test classes.

## Tasks

<!-- IMPORTANT: This document must be updated between execution runs to
     track progress. -->

- `Phase 1 — Infrastructure`
    1. `Update pyproject.toml pytest config` — Add `log_cli`, `log_cli_level`,
       `log_cli_format`, `log_cli_date_format`, `log_file`, `log_file_level`,
       `timeout`, and `timeout_func_only` to `[tool.pytest.ini_options]`.
       Add `flaky` marker registration. File: `pyproject.toml` lines 90-107.
    2. `Add new test dependencies` — Add `pytest-rerunfailures>=16.0`,
       `pytest-reportlog>=0.4.0`, `pytest-harvest>=1.10.0`, and
       `pytest-durations>=1.0.0` to both `[dependency-groups] dev` (lines
       56-66) and `[project.optional-dependencies] dev` (lines 69-79) in
       `pyproject.toml`.
    3. `Install new dependencies` — Run `uv sync --group dev` to install
       the new packages.
- `Phase 2 — Test Instrumentation`
    1. `Add retry markers to E2E test classes` — Add
       `@pytest.mark.flaky(reruns=2, reruns_delay=5)` to the five real-LLM
       test classes:
       - `TestClaudeE2E` in `test_e2e_a2a.py:280`
       - `TestGeminiE2E` in `test_e2e_a2a.py:319`
       - `TestGoldStandardBidirectional` in `test_e2e_a2a.py:366`
       - `TestFrenchNovelRelayLive` in `test_french_novel_relay.py:185`
       - `TestClaudeExecutorLive` in `test_claude_executor.py:135` (verify
         marker presence first)
    2. `Add results_bag metrics to E2E tests` — Instrument the test methods
       in the five classes above with `results_bag` fixture parameter and
       record `latency_ms`, `model`, and `state` after each LLM call.
       This involves adding `results_bag` as a method parameter and
       assigning attributes after the timing section in each test.
    3. `Add logging to E2E test files` — Add `import logging` and
       `logger = logging.getLogger(__name__)` to `test_e2e_a2a.py` and
       `test_french_novel_relay.py`. Add `logger.info(...)` calls before
       each LLM API call and after each response (approximately 2 log lines
       per API call site — ~10 total across both files).
- `Phase 3 — Housekeeping`
    1. `Update .gitignore` — Add `test-debug.log` and `test-events.jsonl`
       entries. Note: `*.log` is already gitignored (line 69); verify
       `test-events.jsonl` is not covered. Add explicit entry for
       `test-events.jsonl`.
    2. `Verify fast tests still pass` — Run
       `pytest src/vaultspec/protocol/ -m "not (claude or gemini)" -q`
       and confirm all 381 tests pass with the new config (live logging
       output visible, no regressions).
    3. `Verify plugin loading` — Run
       `pytest --co -q src/vaultspec/protocol/a2a/tests/test_e2e_a2a.py`
       to confirm the new plugins load without conflicts and E2E tests
       collect with the `flaky` marker visible.

## Parallelization

Phase 1 steps 1-2 are a single file edit (pyproject.toml) — sequential.
Phase 1 step 3 depends on 1-2. Phase 2 steps 1-3 touch different concerns
in the same files but can be done as a single pass per file. Phase 3 steps
are independent of each other but depend on Phase 1-2 completing.

Recommended: Execute sequentially — the total scope is small (~30 minutes)
and file-level conflicts make parallelization counterproductive.

## Verification

- **Fast suite unchanged**: `pytest src/vaultspec/protocol/ -m "not (claude or gemini)" -q` — 381 passed, <5s.
- **Live logging visible**: Running with `-s` shows timestamped log lines
  in the console output for tests that emit `logger.info(...)`.
- **Plugins loaded**: `pytest --co` shows no import errors or plugin
  conflicts. `flaky` marker recognized.
- **reportlog works**: `pytest --report-log=test-events.jsonl src/vaultspec/protocol/tests/test_sandbox.py -q` produces a valid JSONL file.
- **harvest works**: A quick unit test with `results_bag` fixture collects
  data without error.
- **No mock usage**: Grep confirms no `unittest.mock`, `monkeypatch`, or
  `pytest-mock` imports were introduced.

Full E2E validation (running real LLM tests) is deferred — the instrumentation
is additive and will be exercised on the next intentional E2E run via
`pytest src/vaultspec/protocol/ -m "claude or gemini" --report-log=test-events.jsonl`.
