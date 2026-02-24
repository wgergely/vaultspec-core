---
tags:
  - "#exec"
  - "#pytest-e2e"
date: "2026-02-21"
related:
  - "[[2026-02-21-pytest-e2e-observability-impl-plan]]"
---
# `pytest-e2e` `impl` `phase1`

Added pytest observability config and four new test dependencies.

- Modified: `[[pyproject.toml]]`

## Description

Step 1.1: Added to `[tool.pytest.ini_options]`: `log_cli`, `log_cli_level`,
`log_cli_format`, `log_cli_date_format`, `log_file`, `log_file_level`,
`timeout=300`, `timeout_func_only=true`. Registered the `flaky` marker.

Step 1.2: Added `pytest-rerunfailures>=16.0`, `pytest-reportlog>=0.4.0`,
and `pytest-durations>=1.0.0` to both `[dependency-groups] dev` and
`[project.optional-dependencies] dev`. `pytest-harvest` was initially added
but later removed — see phase2 for details.

Step 1.3: Ran `uv sync --group dev` -- all packages installed successfully.

## Tests

No test changes in this phase. Dependency installation verified by successful
`uv sync` with no resolution errors.
