---
tags:
  - '#plan'
  - '#audit-fixes'
date: '2026-02-22'
related:
  - '[[2026-02-22-audit-fixes-adr]]'
  - '[[2026-03-23-audit-fixes-research]]'
---

# Plan: Audit Remediations (Logging & Robustness)

This plan executes the fixes mandated by `2026-02-22-audit-fixes-adr` to improve logging and robustness across the codebase.

## Phase 1: RAG Resilience

- [ ] **Target:** `src/vaultspec/rag/api.py`
- [ ] **Action:** Wrap `get_document` call (or internal logic) in a try-except block for `GPUNotAvailableError`.
- [ ] **Logic:** If GPU is missing, log a warning and return `None` (or raise a specific `RagUnavailableError` that callers handle), triggering the existing filesystem fallback path.

## Phase 2: CLI Logging Refactor

- [ ] **Target:** `src/vaultspec/cli.py`
- [ ] **Action 1:** Initialize logging.
  - [ ] Call `configure_logging()` at the start of `main()`.
- [ ] **Action 2:** Replace `print`.
  - [ ] Identify `print()` calls used for informational/status output.
  - [ ] Replace with `logger.info()` or `logger.warning()`.
  - [ ] *Constraint:* Keep `print()` for structured data output meant for stdout (like `skills list` or `config show`) or ensure the logger writes to stderr. (Review `logging_config.py` to confirm stderr target).

## Phase 3: Hydration Visibility

- [ ] **Target:** `src/vaultspec/vaultcore/hydration.py`
- [ ] **Action:** Add `logging` import and `logger`.
- [ ] **Action:** Instrument the replacement logic.
  - [ ] Log warning if a key is missing in the context.
  - [ ] Log info on successful hydration (at debug level).

## Phase 4: Verification

- [ ] **Test RAG:** Run a RAG command (simulating no GPU if possible, or verify logic via unit test).
- [ ] **Test CLI:** Run `cli.py skills list` and check that logs appear (if verbose) and output remains clean.
- [ ] **Test Hydration:** Verify logs during a `vault create` operation.
