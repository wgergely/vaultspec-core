---
tags:
  - '#exec'
  - '#clci-release'
date: '2026-03-22'
related:
  - '[[2026-03-22-clci-release-phase1-plan]]'
  - '[[2026-03-22-clci-release-adr]]'
  - '[[2026-03-22-clci-release-phase1-review-audit]]'
  - '[[2026-03-22-clci-release-phase1-implementation-exec]]'
---

# clci-release phase-1 summary

Phase 1 complete. All 7 implementation tasks executed, CI green on all 5
checks, PR #5 marked ready for review.

- Created: `release-please-config.json`
- Created: `.release-please-manifest.json`
- Created: `.github/workflows/release-please.yml`
- Modified: `.github/workflows/publish.yml`
- Modified: `.github/workflows/ci.yml` (pinned actionlint Docker tag)
- Created: `.github/release.yml`
- Created: `tests/smoke_test.py`

## Description

Implemented a three-workflow release pipeline for vaultspec-core:

- **release-please.yml** runs on push to main, manages Release PRs with
  auto-generated CHANGELOG.md and version bumps via conventional commits
- **publish.yml** triggered by GitHub Release events (created by
  release-please), runs build -> smoke-test -> publish-pypi chain using
  `uv publish` with OIDC trusted publishing
- **ci.yml** unchanged except pinning actionlint Docker tag from `:latest`
  to `:1.7.11` (security fix from review audit)

Smoke test validates package import, version metadata, MCP server factory,
and both CLI entry points (`--version`, `--help`) against built artifacts.

PR #6 (MCP binary locking fix) merged into feature branch. The fix changes
invocation method to `python -m` but does not affect the `vaultspec-mcp`
console script entry point or `create_server()` - both remain functional.

## Tests

- **actionlint**: all 3 workflow files pass locally (no syntax errors)
- **smoke test**: all 5 checks pass locally (import, version=0.1.0,
  FastMCP factory, --version, --help)
- **pre-commit hooks**: ruff lint, ruff format, ty type-check all pass
- **CI (remote)**: all 5 jobs pass - Workflow Lint, Lint/Type/Config/Link/
  Markdown, Tests, Vault Audit, Dependency Audit
- **Security review**: 3 HIGH findings resolved (actionlint pin, environment
  protection documented, publish CI gate replaced). See
  \[[2026-03-22-clci-release-phase1-review-audit]\]
- **Correctness review**: version flow verified end-to-end, release event
  chain confirmed correct, smoke test feasibility validated

**Post-merge manual steps required (Task 8):**

- Register PyPI trusted publisher (pypi.org > Publishing > GitHub)
- Create `pypi` GitHub environment with required reviewers and branch
  restriction to main
- Ensure branch protection on main requires CI status checks
