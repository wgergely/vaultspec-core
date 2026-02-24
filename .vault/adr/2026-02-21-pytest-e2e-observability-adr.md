---
tags:
  - "#adr"
  - "#pytest-e2e"
date: "2026-02-21"
related:
  - "[[2026-02-21-pytest-e2e-observability-research]]"
---
# `pytest-e2e` adr: E2E test observability and reliability stack | (**status:** `accepted`)

## Problem Statement

The protocol test suite (403 tests) includes 22 real-LLM E2E tests with
180-300s timeouts. Running the full suite appears "stuck" because vanilla
pytest provides zero live output, no debug log capture, and no way to
distinguish hanging from slow-but-progressing tests. On Windows, the
`thread`-method timeout kills the process, losing all reports.

## Considerations

- **Live visibility**: Developers need real-time feedback during 3-5 minute
  tests. Silence is indistinguishable from a hang.
- **Debug capture**: Full application-level logs must be preserved on both
  success and failure/timeout for post-mortem analysis.
- **Flaky APIs**: LLM backends (Claude, Gemini) produce transient failures
  (rate limits, overload, network). Tests must tolerate this without masking
  real regressions.
- **Metrics**: LLM latency, token usage, and model version should be tracked
  per test run for trend analysis and cost monitoring.
- **CI compatibility**: Solution must work on Windows (primary dev platform)
  where `SIGALRM`-based timeouts are unavailable.
- **Dependency budget**: Minimize new dependencies; prefer built-in pytest
  features where sufficient.

## Constraints

- Windows-only: `pytest-timeout` limited to `thread` method (kills process on
  timeout, no stack dump, no fixture teardown).
- No mocking: All tests exercise real code paths and real LLM APIs.
- E2E tests must remain opt-out (run by default, exclude with markers).

## Implementation

### 1. Built-in Live Logging (no new dependency)

Add to `[tool.pytest.ini_options]` in `pyproject.toml`:

```toml
log_cli = true
log_cli_level = "INFO"
log_cli_format = "%(asctime)s [%(levelname)8s] %(name)s: %(message)s"
log_cli_date_format = "%H:%M:%S"
log_file = "test-debug.log"
log_file_level = "DEBUG"
```

Instrument E2E test modules and executor code with `logging.getLogger(__name__)`
calls at key points (before API call, after response, on retry).

### 2. pytest-timeout Advanced Config (already installed)

```toml
timeout = 300
timeout_func_only = true
```

Excludes fixture setup/teardown from timeout budget. Tests that spin up A2A
ASGI servers in fixtures won't be penalized for startup time.

### 3. New Dependencies

Add to `[project.optional-dependencies]` test extras:

| Package | Version | Purpose |
|---------|---------|---------|
| pytest-rerunfailures | >=16.0 | Retry flaky LLM tests (2 retries, 5s delay) |
| pytest-reportlog | >=0.4.0 | Real-time JSON event stream (survives process kill) |
| ~~pytest-harvest~~ | ~~>=1.10.0~~ | ~~Capture LLM metrics~~ — **REJECTED**: incompatible with `@flaky` reruns (KeyError on rerun) |
| pytest-durations | >=1.0.0 | Separate fixture vs test function timing |

### 4. E2E Test Markers

E2E tests remain **opt-out** (run by default). Exclude with:

```bash
pytest src/vaultspec/protocol/ -m "not (claude or gemini)"
```

### 5. Retry Policy for E2E Tests

Apply `@pytest.mark.flaky(reruns=2, reruns_delay=5)` to all test classes
marked `@pytest.mark.claude` or `@pytest.mark.gemini`. Maximum added time
per flaky test: 2 x timeout (worst case: 600s for a 300s-timeout test).

### 6. Metrics Collection

~~pytest-harvest `results_bag`~~ — **Rejected** during implementation.
`results_bag` throws `KeyError` when `pytest-rerunfailures` triggers a rerun
(`"Internal Error - This fixture 'results_bag' was already stored for test
id..."`). The two plugins are fundamentally incompatible.

**Replacement**: Structured `logger.info(...)` calls capturing latency, model,
and state at each API call site. Combined with `log_file = "test-debug.log"`
at `DEBUG` level, this provides equivalent metrics capture without plugin
conflicts.

### 7. Real-Time Reporting

Default invocation for E2E runs:

```bash
pytest src/vaultspec/protocol/ --report-log=test-events.jsonl
```

Add `test-events.jsonl` and `test-debug.log` to `.gitignore`.

## Rationale

- **Opt-out E2E**: User preference. Keeps the default suite comprehensive.
  Developers who want fast feedback use `-m "not (claude or gemini)"`.
- **2 retries, 5s delay**: Balances resilience against CI cost. Single retry
  insufficient for consecutive rate-limit errors; 3+ retries wastes time.
- **Structured logging over pytest-harvest**: `results_bag` is incompatible
  with `@flaky` reruns. Structured `logger.info(...)` calls provide equivalent
  metrics capture without plugin conflicts.
- **pytest-reportlog**: Critical on Windows where thread-method timeout kills
  the process. JSON events flushed before kill, preserving partial results.
- **pytest-durations**: Low-cost addition that immediately surfaces whether
  slowness is fixture setup or test body — actionable without investigation.
- **Built-in log_cli over pytest-sugar**: Sugar hides test names until
  completion, *worse* for long tests. Built-in logging is more reliable.

## Consequences

- **3 new dev dependencies** added to the test extras (pytest-harvest rejected).
- **test-debug.log** and **test-events.jsonl** generated in project root on
  test runs; must be gitignored.
- E2E tests with retries can take up to 3x their base timeout in worst case.
  CI job timeouts must account for this (recommend 30-minute job limit).
- Instrumenting existing E2E tests with `logging` calls and `results_bag` is
  a one-time effort (~15 minutes per test file).
- `log_cli = true` adds terminal noise for unit test runs. Developers running
  fast tests may prefer `--log-cli-level=WARNING` override.
