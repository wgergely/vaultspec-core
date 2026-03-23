---
tags:
  - '#exec'
  - '#cli-target-refactor'
date: '2026-03-05'
related:
  - '[[2026-03-05-cli-target-refactor-plan]]'
---

# `cli-target-refactor` `phase4` `step2`

Secured Hook execution context.

- Modified: `src/vaultspec/hooks/engine.py`

## Description

- Updated `_execute_shell` to clone `os.environ` and inject `VAULTSPEC_TARGET_DIR`.
- Ensured `subprocess.Popen` is explicitly provided with `cwd=_t.TARGET_DIR` so scripts correctly context-switch to the requested target directory rather than running destructively in the terminal's physical directory.

## Tests

- Execution correctly clones environment context for safe sub-process isolation.
