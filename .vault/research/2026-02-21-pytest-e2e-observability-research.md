---
tags:
  - '#research'
  - '#pytest-e2e'
date: '2026-02-21'
related:
  - '[[2026-02-21-pytest-e2e-observability-adr]]'
---

# `pytest-e2e` research: observability for long-running A2A/E2E tests

The protocol test suite (`src/vaultspec/protocol/`) contains 403 tests. 381 are
fast unit/integration tests (3.5s total). 22 are real-LLM E2E tests marked
`claude`/`gemini` with 180-300s timeouts. Running the full suite appears "stuck"
because vanilla pytest provides zero visibility while these E2E tests execute.

## Current Baseline

| Component      | Version  | Notes                                   |
| -------------- | -------- | --------------------------------------- |
| pytest         | >=7.0.0  | No live logging configured              |
| pytest-asyncio | >=0.21.0 | `asyncio_mode = "auto"`                 |
| pytest-timeout | >=2.3.0  | Only used via `@pytest.mark.timeout(N)` |

No `log_cli`, no `log_file`, no structured reporting configured.

## Core Problems

- **P1 — No live output**: No way to see progress while 180s tests run.

- **P2 — No debug logs on failure**: When a test times out, the stack dump is
  all you get. No application-level logging captured.

- **P3 — Hang vs slow indistinguishable**: A test at 120s could be progressing
  or deadlocked. No heartbeat mechanism.

- **P4 — No structured reports**: Test results lost on Windows thread-method
  timeout (kills the process, no XML/JSON output).

## Findings

### Tier 1: High-Impact, Directly Addresses Problems

#### Built-in Live Logging (no plugin)

The single biggest improvement. Pytest has built-in `log_cli` support:

```toml
log_cli = true
log_cli_level = "INFO"
log_cli_format = "%(asctime)s [%(levelname)8s] %(name)s: %(message)s"
log_cli_date_format = "%H:%M:%S"
log_file = "test-debug.log"
log_file_level = "DEBUG"
```

- Streams INFO+ logs in real time as tests run → solves P1, P3
- Writes full DEBUG traces to file for post-mortem → solves P2
- Timestamps between log lines make stuck-vs-progressing obvious → solves P3
- Requires instrumenting test code with `logging` calls at strategic points

**Gotcha**: Known race condition with background threads and `capfd`/`capsys`
(pytest #13693).

#### pytest-timeout Advanced Config (already installed)

`func_only=true` defers timeout to test body only, excluding fixture
setup/teardown. Critical when fixtures spin up A2A servers.

```toml
timeout = 300
timeout_func_only = true
```

**Windows limitation**: Only `thread` method available. This kills the entire
process on timeout — no fixture teardown, no XML reports. This makes
pytest-reportlog essential as a compensating control.

**Stack dump**: The signal handler dumps all thread stacks on timeout. This is
the primary hang-detection mechanism, but unavailable on Windows (`thread`
method just kills).

#### pytest-reportlog — Real-Time Structured Events

```bash
pytest --report-log=test-events.jsonl
```

Writes one JSON-line per event (collection, test start, test result) as tests
execute. Survives process-killing timeouts because lines are flushed
immediately.

- `tail -f test-events.jsonl` in separate terminal → real-time monitoring
- Machine-parseable for CI dashboards
- Compensates for Windows timeout killing the process (partial results preserved)

Status: Maintained by pytest-dev. Simple, stable, ~1M downloads.

### Tier 2: Valuable Additions

#### pytest-rerunfailures — Retry Flaky LLM Calls

```python
@pytest.mark.flaky(reruns=2, reruns_delay=5)
```

LLM APIs are inherently flaky (rate limits, transient errors, model overload).
Retries with delay avoid failing the whole suite on transient errors.

Status: v16.1 (2025). ~5M monthly downloads. Actively maintained.

**Gotcha**: `reruns * timeout` must not exceed CI job limit. A timed-out test
counts as failure and triggers rerun.

#### pytest-harvest — Capture Intermediate Test Data

```python
def test_claude_response(results_bag):
    results_bag.latency_ms = response.latency
    results_bag.token_count = response.usage.total_tokens
```

Collects metrics across test runs. Useful for tracking LLM latency/cost trends.

Status: v1.10.5. Maintained.

#### pytest-durations — Fixture vs Test Timing

```bash
pytest --pytest-durations=10 --pytest-durations-group-by=function
```

Shows fixture durations separately from test function durations. Identifies
whether slowness is server startup or API calls.

Status: Aug 2025. Actively maintained.

#### pytest-asyncio Loop Scoping (already installed, needs config)

```python
@pytest.mark.asyncio(loop_scope="session")
```

Session-scoped event loops avoid loop create/destroy overhead when tests share
async server state (connection pools, ASGI transports).

### Tier 3: Evaluated and Rejected

| Plugin                   | Reason for rejection                                         |
| ------------------------ | ------------------------------------------------------------ |
| pytest-sugar             | Hides test names until completion — *worse* for long tests   |
| pytest-subprocess        | Fakes subprocess calls — violates no-mocking rule            |
| pytest-timeouts (plural) | Conflicts with pytest-timeout, less maintained               |
| pytest-xprocess          | Only helps with server startup, not test-level observability |
| pytest-monitor           | Resource monitoring useful but orthogonal to core problems   |
| pytest-evals             | Too specialized for LLM eval benchmarks, not test infra      |
| nox                      | Session manager, not a pytest replacement                    |

### Windows-Specific Considerations

- `pytest-timeout` only supports `thread` method on Windows (no `SIGALRM`)
- Thread method kills the process — no teardown, no report generation
- `pytest-reportlog` compensates by writing events in real time (pre-kill)
- `log_file` with DEBUG level persists even if process is killed mid-test
- No stack dump on timeout (signal-method only feature)
