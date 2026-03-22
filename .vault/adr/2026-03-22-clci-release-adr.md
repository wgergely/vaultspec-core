---
tags:
  - '#adr'
  - '#clci-release'
date: '2026-03-22'
related:
  - '[[2026-03-22-clci-release-research]]'
  - '[[2026-03-21-cli-release-readiness-audit]]'
---

# clci-release adr: release pipeline via release-please and uv publish | (**status:** `accepted`)

## Problem Statement

vaultspec-core has no release pipeline. Version is hardcoded at `0.1.0` in
pyproject.toml, the existing `publish.yml` workflow has no CI gate, no
changelog generation, no GitHub Release creation, and no strategy for
standalone binary distribution. The project cannot be versioned, packaged,
or published in a repeatable, automated way.

## Considerations

**Versioning approach** - two viable options were evaluated in
\[[2026-03-22-clci-release-research]\]:

- **release-please (chosen):** PR-based release automation from Google.
  Parses conventional commits, opens a Release PR with version bump and
  CHANGELOG.md update, creates GitHub Release on merge. Human review gate
  before every release. Conflicts with `hatch-vcs` (which derives version
  from git tags dynamically) - the two are mutually exclusive.
- **hatch-vcs + manual tagging (rejected):** simpler setup, no commit
  discipline, but no changelog automation and no review gate.

**Publishing tool** - the project already uses `uv` throughout:

- **`uv publish` (chosen):** native uv command with OIDC trusted publishing.
  Single tool for build + publish. Simpler workflow YAML than the
  `pypa/gh-action-pypi-publish` action.
- **`pypa/gh-action-pypi-publish` (rejected):** battle-tested but adds an
  external action when `uv publish` achieves the same OIDC flow natively.

**TestPyPI staging** - evaluated against comparable projects (httpie, black,
poetry). Pure-Python `py3-none-any` wheels do not benefit from TestPyPI
staging. The smoke test pattern (install built wheel in CI, run it) catches
the same class of packaging errors. Skipped.

**Sigstore attestations** - `uv publish` does not generate PEP 740
attestations. Adding them requires either the pypa action or a separate
attestation generation step. Deferred to a future phase - not worth pipeline
complexity at alpha stage.

**Standalone binary distribution** - PyApp (Hatch ecosystem, Rust
bootstrapper) is preferred over PyInstaller/Nuitka for hatchling projects.
Self-update capability, uses real pip/uv for installation, smaller launcher
binary. Deferred to Phase 2.

**Entry point strategy** - the package ships two console scripts:
`vaultspec-core` (CLI) and `vaultspec-mcp` (MCP stdio server). For PyPI
distribution, both are installed from the same package. For standalone
binaries, two separate PyApp builds from the same wheel (different
`PYAPP_EXEC_SPEC`) - MCP servers are configured by path in tool configs,
so a dedicated binary is cleaner than subcommand routing.

## Constraints

- Project is alpha-stage (`0.x`) with a small team
- Must not require manual version string maintenance
- Must gate publishing on CI (lint + test) passing
- Must produce GitHub Releases with categorized notes for visibility
- Python 3.13+ only (narrows audience to developers comfortable with uv)
- Conventional commits are a new discipline for this project

## Implementation

### Phase 1 - uv-native release pipeline

**Workflow architecture (three separate workflows):**

- `ci.yml` (existing, unchanged) - triggers on `push: branches: [main]`
  and `pull_request`. Runs lint, type-check, tests, vault audit, dep audit.
  The release-please Release PR is a pull request, so CI runs on it
  automatically - no reusable workflow extraction needed.
- `release-please.yml` (new) - triggers on `push: branches: [main]`.
  Runs `google-github-actions/release-please-action@v4` with
  `release-type: python`. Creates/updates the Release PR. When the Release
  PR merges, release-please creates a GitHub Release with a git tag.
- `publish.yml` (replace existing) - triggers on
  `on: release: types: [published]`. Builds, smoke tests, and publishes to
  PyPI. Completely decoupled from release-please - it just reacts to the
  GitHub Release event. This means CI has already passed on the Release PR
  before it could be merged.

**Version management (release-please):**

- Add `release-please-config.json` and `.release-please-manifest.json`
- Keep static `version` in pyproject.toml (no `hatch-vcs`)
- release-please bumps version, generates CHANGELOG.md, creates GitHub
  Release on PR merge
- Configure `bump-minor-pre-major: true` and
  `bump-patch-for-minor-pre-major: true` for pre-1.0 behavior
- Adopt conventional commits: `feat:`, `fix:`, `feat!:` minimum

**Publish workflow (`publish.yml`) job chain:**

```
build -> smoke-test -> publish-pypi
```

- **build:** `uv build`, upload dist artifacts via `actions/upload-artifact`
- **smoke-test:** download artifacts, install wheel and sdist in isolated
  environments, run `tests/smoke_test.py`
- **publish-pypi:** download artifacts, `uv publish` with OIDC trusted
  publishing, `pypi` GitHub environment

**Smoke test script (`tests/smoke_test.py`):**

- `vaultspec-core --version` exits 0 and prints a version string
- `vaultspec-core --help` exits 0 and typer renders help
- `import vaultspec_core` succeeds (package importable)
- `vaultspec_core.mcp_server.app.create_server()` returns a FastMCP
  instance (MCP server entry point functional)

**PyPI trusted publisher setup (manual, one-time):**

- Register on pypi.org: owner=`wgergely`, repo=`vaultspec-core`,
  workflow=`publish.yml`, environment=`pypi`
- Create `pypi` environment in GitHub repo settings

### Phase 2 - standalone binaries (PyApp)

- Add PyApp matrix build to release workflow (Rust toolchain in CI)
- Configure: `PYAPP_UV_ENABLED=true`, `PYAPP_DISTRIBUTION_EMBED=true`
- Two binaries: `vaultspec-core` (`PYAPP_EXEC_MODULE=vaultspec_core`) and
  `vaultspec-mcp` (`PYAPP_EXEC_SPEC=vaultspec_core.mcp_server.app:run`)
- Build targets: linux-x86_64, macos-x86_64, macos-aarch64, windows-x86_64
- Attach to GitHub Releases with `checksums.sha256`
- Revisit Sigstore attestations at this stage

### Phase 3 - package managers

- Scoop bucket with JSON manifest pointing to GH Release binaries
- Homebrew tap (Python formula initially, binary formula post-Phase 2)
- Chocolatey/winget only if user demand exists

## Rationale

**release-please over hatch-vcs:** the PR review gate is the deciding
factor. For a project transitioning from no release process, having a human
explicitly merge a Release PR (reviewing the changelog and version bump)
prevents accidental or premature releases. The conventional commit overhead
is minimal - `feat:` and `fix:` cover most commits, and non-conventional
commits are silently ignored (see \[[2026-03-22-clci-release-research]\]
section 10.1).

**Three workflows over one monolithic workflow:** keeping `ci.yml`,
`release-please.yml`, and `publish.yml` as separate workflows is simpler
than a reusable workflow extraction. The current CI has 5 jobs with complex
tool setup (lychee, taplo, just, actionlint). Extracting into
`workflow_call` introduces GitHub Actions limitations (nested secrets,
matrix constraints). Since CI already runs on all PRs - including the
release-please Release PR - there is no need to duplicate CI in the
publish workflow. The `on: release: types: [published]` trigger on
`publish.yml` naturally gates on CI having passed.

**`uv publish` over pypa action:** the project uses uv for everything
(dependency management, builds, test running). Using `uv publish` keeps the
toolchain homogeneous and simplifies the workflow YAML. The Astral reference
workflow (`astral-sh/trusted-publishing-examples`) validates this approach
(see \[[2026-03-22-clci-release-research]\] section 3).

**Skip TestPyPI:** comparable pure-Python CLI projects (httpie, black,
poetry) do not use TestPyPI. Smoke tests that install the built wheel and
run `vaultspec-core --help` catch packaging errors (missing files, broken
imports) more effectively than TestPyPI round-trips.

**Defer Sigstore:** `uv publish` does not generate attestations natively.
Adding the pypa action alongside `uv publish` solely for attestations adds
complexity without immediate user value at alpha stage.

**PyApp over PyInstaller:** PyApp is part of the Hatch ecosystem (same
author), uses the same `python-build-standalone` distributions as uv, and
supports self-update. It produces a thin Rust launcher (~5 MB) rather than
bundling the entire interpreter (80-120 MB). The trade-off (Rust toolchain
in CI) is acceptable.

**Two binaries over one:** MCP servers are configured by absolute path in
tool configs (e.g., Claude Code's `mcp_servers.json`). A dedicated
`vaultspec-mcp` binary is cleaner than requiring
`"command": "vaultspec-core", "args": ["mcp", "serve"]`. The two PyApp
builds share the same wheel and CI job - minimal duplication.

## Consequences

- **Conventional commits required:** all contributors must use `feat:`,
  `fix:`, etc. prefixes. Non-conventional commits won't appear in changelogs
  or trigger version bumps. Consider adding a commit-msg hook (via `prek`)
  or CI check to enforce the format over time.
- **No `hatch-vcs`:** version is static in pyproject.toml, managed by
  release-please. Dev builds between releases will show the last released
  version (not a dev suffix like hatch-vcs provides). Acceptable trade-off
  for the review gate. Note: `get_version()` in `cli_common.py` already
  uses `importlib.metadata` as primary with pyproject.toml as dev fallback
  - this works correctly with static versioning and requires no changes.
- **Node.js dependency:** release-please is a Node tool. The GitHub Action
  abstracts this, but it's a non-Python dependency in the release chain.
- **Three workflow files:** `ci.yml` (existing), `release-please.yml` (new),
  `publish.yml` (replaced). This is more files than a monolithic approach
  but each has a single responsibility and is independently testable.
- **Phase 2 adds Rust to CI:** PyApp requires `cargo` in the build matrix.
  The `dtolnay/rust-toolchain` action handles this, but it increases CI
  build time.
- **Sigstore gap:** until attestations are added, PyPI will not show a
  "verified" badge for vaultspec-core uploads.
