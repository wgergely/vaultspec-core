---
tags:
  - '#audit'
  - '#clci-release'
date: '2026-03-22'
related:
  - '[[2026-03-22-clci-release-phase1-plan]]'
  - '[[2026-03-22-clci-release-adr]]'
---

# clci-release Code Review

<!-- Persistent log of audit findings appended below. -->

<!-- Use: {TOPIC}-### | {LEVEL} | {Summary} \n {DESCRIPTION} format-->

## Security Review

PINNING-001 | HIGH | `docker://rhysd/actionlint:latest` uses unpinned `:latest` tag
ci.yml line 30 uses `:latest` Docker tag for actionlint. Mutable tag is a supply chain risk. Fix: pin to specific version tag.

ENVIRONMENT-001 | HIGH | `pypi` environment needs protection rules configured
Both existing and planned `publish.yml` reference `environment: name: pypi`. Without required reviewers and deployment branch restrictions in GitHub repo settings, the environment gate is cosmetic. Fix: plan must document that `pypi` environment requires required reviewers and branch restriction to `main` only.

PUBLISH-GAP-001 | HIGH | Existing publish.yml has no CI gate (resolved by plan)
Current `publish.yml` triggers on `push: tags: [v*]` with no CI dependency. Any user with push access can create a tag on any commit and publish to PyPI. The plan's replacement trigger (`on: release: types: [published]`) with release-please flow resolves this.

PINNING-002 | MEDIUM | All actions pinned to floating major version tags, not SHAs
Current practice uses `@v4`, `@v7` etc. SHA pinning is more secure for publish-path actions. Noted for future hardening.

PERMISSIONS-001 | MEDIUM | release-please.yml needs `contents: write` and `pull-requests: write`
Acceptable minimum for release-please. Mitigated by trigger being `push: branches: [main]` only.

CONCURRENCY-001 | MEDIUM | Plan does not specify concurrency controls for new workflows
Neither `release-please.yml` nor `publish.yml` have concurrency groups. Rapid pushes to main could cause overlapping release-please runs. Fix: add concurrency groups to plan.

TRIGGER-001 | MEDIUM | `on: release: types: [published]` can be manually triggered by collaborators
Any collaborator with write access can manually create a GitHub Release. Mitigated by `pypi` environment protection rules (ENVIRONMENT-001).

PINNING-003 | LOW | `taiki-e/install-action@v2` installs latest lychee and taplo versions
Tool versions not pinned. Noted for future hardening.

SECRETS-001 | LOW | `uv publish` OIDC token logging caution
Ensure `--verbose` flag is never used in the publish step.

ARCHITECTURE-001 | LOW | Branch protection is a prerequisite for this architecture
The three-workflow architecture relies on CI passing on the Release PR. If branch protection is misconfigured (no required status checks), the gate disappears. Document as prerequisite.

## Correctness Review

PUBLISH-PERMISSIONS-001 | MEDIUM | publish-pypi job must explicitly include `contents: read`
When job-level permissions are specified, they replace (not merge with) top-level permissions. The `publish-pypi` job specifies `id-token: write` and must also include `contents: read` for artifact download. Fix: update plan to note both permissions.

SMOKE-TEST-001 | MEDIUM | `create_server()` may have import-time side effects in isolated env
`register_vault_tools()` imports modules that may reference `vaultspec_core.core` internals. If any perform file-system operations at import time, the test could fail in a bare CI environment. Fix: smoke test should wrap in try/except with clear error message.

MISSING-RELEASE-YML-001 | MEDIUM | `.github/release.yml` recommended by research, omitted from plan
release-please generates its own changelog, so this is supplementary. Low practical impact but a gap between research and plan.

RELEASE-PLEASE-CONFIG-001 | LOW | Research config has `release-type` at top level; plan correctly puts it inside `packages."."`
Implementer must follow plan structure, not research snippet.

ACTIONLINT-SETUP-UV-001 | LOW | Plan references `astral-sh/setup-uv` without version pin
Implementer should pin to `@v7` matching existing CI.

CONCURRENCY-002 | LOW | No concurrency group on release-please.yml
Concurrent runs on rapid pushes to main could race on Release PR. Low risk since release-please is idempotent.

VERSION-FLOW-001 | INFO | Version chain is complete and correct
pyproject.toml -> uv build -> wheel metadata -> importlib.metadata.version() -> --version. No gaps.

CI-RELEASE-PR-001 | INFO | Release PRs will trigger all CI jobs
ci.yml triggers on `pull_request` without branch filter. Confirmed correct.

WORKFLOW-TRIGGER-001 | INFO | Release event chain is correct
push to main -> release-please -> Release PR -> merge -> tag + release -> publish.yml fires. Confirmed correct.
