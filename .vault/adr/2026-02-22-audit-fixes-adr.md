---
tags:
  - '#adr'
  - '#audit-fixes'
date: '2026-02-22'
related:
  - '[[2026-02-22-codebase-audit]]'
  - '[[2026-02-22-codebase-audit-research]]'
---

# ADR: Audit Remediations (Logging & Robustness)

## Context

A comprehensive codebase audit `[[2026-02-22-codebase-audit]]` identified three key areas for improvement:

1. **RAG Resilience:** The `get_document` API crashes on non-GPU systems when RAG is enabled.
1. **CLI Logging:** The `cli.py` module uses `print` statements instead of the structured logging infrastructure.
1. **Hydration Visibility:** The `hydration.py` module silently swallows errors during template hydration.

## Decision

We will apply targeted fixes to address these findings.

### 1. RAG: Explicit GPU Check

We will **NOT** enable CPU fallback for RAG operations, as it is too slow for production use. Instead, we will catch `GPUNotAvailableError` in `src/vaultspec/rag/api.py` and log a clear warning (or error, depending on context) before gracefully degrading to non-RAG behavior (filesystem scan) or exiting, rather than crashing with an unhandled exception.

### 2. CLI: Standardized Logging

We will refactor `src/vaultspec/cli.py` to use the `logging` module.

- **Initialization:** Invoke `configure_logging()` at the start of `main()`.
- **Replacement:** Replace `print(...)` with `logger.info(...)`, `logger.warning(...)`, or `logger.error(...)` as appropriate.
- **Stream:** Ensure logs go to `stderr` (via `logging_config`) to keep `stdout` clean for piped output (e.g., `skills list`).

### 3. Hydration: Error Reporting

We will instrument `src/vaultspec/vaultcore/hydration.py` with logging.

- **Log Failures:** Emit `logger.warning` or `logger.error` when a template variable cannot be resolved or replacement fails.
- **Traceability:** Include the filename and the specific variable key in the log message.

## Consequences

- **Positive:** Improved system stability on non-GPU hardware; better observability for CLI operations; easier debugging of template issues.
- **Negative:** CLI output might become slightly more verbose if not tuned correctly (we will rely on default levels).

## Validation

- Run `cli.py` commands and verify log output format.
- Simulate a template error and verify the log message.
