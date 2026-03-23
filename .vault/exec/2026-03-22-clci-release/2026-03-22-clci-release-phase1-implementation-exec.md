---
tags:
  - '#exec'
  - '#clci-release'
date: '2026-03-22'
related:
  - '[[2026-03-22-clci-release-phase1-plan]]'
---

# clci-release phase-1 implementation

Executed all 7 implementation tasks for the uv-native release pipeline.

- Created: `release-please-config.json`
- Created: `.release-please-manifest.json`
- Created: `.github/workflows/release-please.yml`
- Modified: `.github/workflows/publish.yml`
- Created: `.github/release.yml`
- Created: `tests/smoke_test.py`

## Description

**Task 1** - release-please config: manifest mode with `packages."."`
containing `release-type: python`, `package-name: vaultspec-core`,
`bump-minor-pre-major: true`, `bump-patch-for-minor-pre-major: true`,
and changelog section mappings for feat, fix, perf (hidden: docs, chore,
ci, refactor, test).

**Task 2** - release-please workflow: triggers on `push: branches: [main]`,
uses `config-file` and `manifest-file` inputs only (no inline release-type),
concurrency group `release-please` with no cancel-in-progress.

**Task 3** - publish workflow: replaced tag-triggered workflow with
`on: release: types: [published]` trigger. Three-job chain:
build (uv build + upload-artifact) -> smoke-test (checkout + install
wheel/sdist + run smoke_test.py) -> publish-pypi (uv publish with OIDC,
job-level id-token: write + contents: read, pypi environment).
Concurrency group `publish`.

**Task 4** - smoke test: standalone script (not pytest) testing import,
version metadata, MCP server factory (with error handling for import-time
side effects), CLI --version, and CLI --help with expected command presence.

**Task 5** - release.yml: label-based changelog categories for GitHub's
auto-generated release notes (Breaking Changes, Features, Bug Fixes,
Maintenance).

**Task 6** - actionlint: all three workflow files pass locally.

**Task 7** - committed and pushed. Pre-commit hooks pass (ruff, ty).

## Tests

- actionlint passes on all workflow files (ci.yml, release-please.yml,
  publish.yml) - no syntax errors
- smoke test runs locally: all 5 checks pass (import, version=0.1.0,
  create_server returns FastMCP, --version exits 0, --help contains
  expected commands)
- pre-commit hooks pass: ruff lint, ruff format, ty type-check
- CI verification pending on remote PR
