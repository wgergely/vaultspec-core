---
tags:
  - '#plan'
  - '#clci-release'
date: '2026-03-22'
related:
  - '[[2026-03-22-clci-release-adr]]'
  - '[[2026-03-22-clci-release-research]]'
  - '[[2026-03-21-cli-release-readiness-audit]]'
---

# clci-release phase-1 plan

Implement the uv-native release pipeline for vaultspec-core: release-please
for versioning and changelog, `uv publish` for PyPI publishing, smoke tests
for build verification. Delivers the project's first repeatable, automated
release mechanism per \[[2026-03-22-clci-release-adr]\].

## Proposed Changes

Three new or modified files in `.github/workflows/`, two release-please
config files at repo root, and a smoke test script under `tests/`. The
existing `ci.yml` remains unchanged - the release-please Release PR is a
regular pull request and CI gates it automatically.

The publish pipeline is triggered by GitHub Release events (created by
release-please when its Release PR merges), making it fully decoupled from
the version management workflow. See \[[2026-03-22-clci-release-adr]\] for
the three-workflow architecture rationale and
\[[2026-03-22-clci-release-research]\] sections 3 and 10 for `uv publish`
and release-please details.

## Tasks

- **Task 1: release-please configuration**

  - Add `release-please-config.json` at repo root using manifest mode
    (config files are the single source of truth - no inline `release-type`
    input in the workflow). Settings inside `packages.".":`:
    `release-type: python`, `package-name: vaultspec-core`,
    `bump-minor-pre-major: true`, `bump-patch-for-minor-pre-major: true`,
    and `changelog-sections` mappings for `feat`, `fix`, `perf`
  - Add `.release-please-manifest.json` at repo root with `{ ".": "0.1.0" }`
    to seed the current version

- **Task 2: release-please workflow**

  - Create `.github/workflows/release-please.yml`
  - Trigger: `on: push: branches: [main]`
  - Permissions: `contents: write`, `pull-requests: write`
  - Single job running `google-github-actions/release-please-action@v4`
    with `config-file: release-please-config.json` and
    `manifest-file: .release-please-manifest.json` (no inline
    `release-type` - config files own all settings)
  - Validate with `actionlint` (already part of CI lint suite)

- **Task 3: publish workflow**

  - Replace `.github/workflows/publish.yml`
  - Trigger: `on: release: types: [published]`
  - Three jobs chained via `needs:`:
    - **build**: checkout, `astral-sh/setup-uv`, `uv build`, upload
      `dist/` via `actions/upload-artifact@v4`
    - **smoke-test**: checkout repo (for `tests/smoke_test.py`),
      `astral-sh/setup-uv`, download dist artifacts, install wheel in
      isolated env (`uv run --isolated --no-project --with dist/*.whl`),
      install sdist similarly, run `tests/smoke_test.py` against each
    - **publish-pypi**: download artifacts, `uv publish` with
      `permissions: id-token: write` and `environment: name: pypi`
  - Top-level `permissions: contents: read`

- **Task 4: smoke test script**

  - Create `tests/smoke_test.py`
  - Test 1: `import vaultspec_core` succeeds
  - Test 2: `importlib.metadata.version("vaultspec-core")` returns a
    non-empty string
  - Test 3: `vaultspec_core.mcp_server.app.create_server()` returns a
    `FastMCP` instance
  - Test 4: subprocess `vaultspec-core --version` exits 0
  - Test 5: subprocess `vaultspec-core --help` exits 0 and output contains
    expected command names
  - Script exits non-zero on any failure (used as CI gate)

- **Task 5: actionlint validation**

  - Run `actionlint` against all workflow files to catch syntax errors
    before push
  - Verify the new workflows pass the existing `workflow-lint` CI job

- **Task 6: commit, push, verify**

  - Commit all new and modified files with a conventional commit message
    (`feat: add release pipeline with release-please and uv publish`)
  - Push to the feature branch
  - Verify CI passes on the PR (lint, type, tests, vault audit, workflow
    lint, dep audit)

## Parallelization

Tasks 1-2 (release-please config + workflow) and Task 4 (smoke test) are
independent and can be implemented in parallel. Task 3 (publish workflow)
depends on Task 4 (references the smoke test script). Tasks 5-6 are
sequential and run after all others.

## Verification

- **Workflow syntax**: `actionlint` passes on all three workflow files
  (`ci.yml`, `release-please.yml`, `publish.yml`)
- **Smoke test runs locally**: `uv build && uv run --isolated --no-project --with dist/*.whl tests/smoke_test.py` passes
- **CI green on PR**: all existing CI jobs pass with the new files present
- **release-please config valid**: JSON schema validates against
  `googleapis/release-please` schema
- **End-to-end verification (post-merge)**: after merging to main,
  release-please opens a Release PR. Merging that PR creates a GitHub
  Release, which triggers publish.yml, which publishes to PyPI. This can
  only be verified after the PR lands on main and the one-time PyPI trusted
  publisher registration is complete.

Note: full end-to-end pipeline verification requires manual PyPI trusted
publisher setup (documented in \[[2026-03-22-clci-release-adr]\]). The CI on
this PR validates workflow syntax, smoke test correctness, and that no
existing checks regress - but the actual PyPI publish can only be tested
after main merge and PyPI configuration.
