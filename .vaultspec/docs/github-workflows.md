# GitHub Workflows

This guide explains how CI/CD is configured in this repository and why each
gate exists.

## Goals

- run quality and verification checks on every push and pull request
- block regressions before merge
- keep dependency risk visible
- publish releases from signed tags using trusted publishing

## Workflow Files

- `.github/workflows/ci.yml`
- `.github/workflows/dependency-review.yml`
- `.github/workflows/publish.yml`
- `.github/workflows/docker.yml`
- `justfile`
- `tests/test_automation_contracts.py`

These files replace prior CI/CD definitions and are the source of truth.
`justfile` is the command authority for local and CI checks.
`test_automation_contracts.py` enforces that workflows and `justfile` stay
synchronized over time.

## CI on Push and Pull Request

`ci.yml` triggers on:

- `push` to any branch
- `pull_request`

It defines four jobs:

1. `workflow-lint`
2. `lint-and-type`
3. `tests` (Ubuntu and Windows matrix)
4. `vault-audit`
5. `dependency-audit` (pip-audit)

### Job: `workflow-lint`

Purpose:

- validate GitHub Actions syntax and runner semantics before merge

Implementation:

- `rhysd/actionlint@v1`

### Job: `lint-and-type`

Purpose:

- enforce code style and static checks early

Checks run:

- `just setup-ci`
- `just lint`
- `just typecheck`

### Job: `tests`

Purpose:

- ensure runtime behavior remains stable on major OS targets

Matrix:

- `ubuntu-latest`
- `windows-latest`

Command:

```bash
just setup-ci
just test
```

This keeps CI deterministic by excluding suites that require external tools,
networked providers, or special credentials.

### Job: `vault-audit`

Purpose:

- continuously verify vault integrity and structure

Command:

```bash
just setup-ci
just vault-audit
```

### Job: `dependency-audit`

Purpose:

- detect known vulnerabilities in Python dependencies

Command:

```bash
just setup-ci
just dependency-audit
```

`dependency-audit` runs inside the project virtual environment via `uv run`,
so the audited environment matches the checked-out workspace instead of a
separate uv tool environment.

## Pull Request Dependency Review

`dependency-review.yml` runs on `pull_request` and uses
`actions/dependency-review-action` with a severity threshold. This catches risky
dependency changes before merge.

## Publishing

`publish.yml` runs on tags matching `v*`.

It performs:

1. package build via `uv build`
2. PyPI publish via `pypa/gh-action-pypi-publish`

The workflow uses OIDC (`id-token: write`) for trusted publishing and avoids
long-lived API tokens in repository secrets.

## Docker Build and Publish

`docker.yml` handles container lifecycle:

- Pull requests: build-only validation (`just docker-build`)
- Pull requests: runtime smoke (`just docker-smoke`)
- Push to `main`: publish GHCR tags `main` and `sha-<shortsha>`
- Push `v*` tags: publish GHCR tags `<version>` and `latest`

Local Docker ergonomics stay centralized in `justfile`.
Registry publication in GitHub Actions uses the standard Docker Actions stack:

- `docker/metadata-action`
- `docker/login-action`
- `docker/build-push-action`
- `actions/attest-build-provenance`

This split avoids re-implementing registry metadata and attestation logic in
shell recipes while keeping local developer commands simple and stable.

## Contract Tests for Automation

`tests/test_automation_contracts.py` validates:

- required `just` recipes exist
- `ci.yml` quality gates invoke `just` recipes
- `ci.yml` includes workflow linting
- `docker.yml` PR job includes both build and smoke checks
- `docker.yml` publish job uses the expected Docker registry actions
- Docker default runtime command is stable

This catches CI/CD drift before merge.

## Security and Reliability Defaults

- workflow-level least privilege permissions (`contents: read`)
- job-level permission escalation only where required (`id-token: write` for publish)
- `concurrency` in CI to cancel superseded runs on the same ref
- pinned major action versions for stable upgrade surfaces

## README Status Badges

README displays:

- Python support level (`3.13+`)
- current CI status (tests/checks via `ci.yml`)
- Docker workflow status and dependency note (`optional`)
- MCP surface badge for `vaultspec-mcp`

These badges provide quick operational status at the repository entry point.

## See Also

- [Release & Deploy Runbook](./release-deploy-runbook.md)
