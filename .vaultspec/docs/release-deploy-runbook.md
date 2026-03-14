# Release and Cloud Deploy Runbook

This runbook defines the exact local and GitHub steps to release
`vaultspec-core` and publish Docker images to GHCR with continuous audit gates.

## Preconditions

- Python `3.13+`
- `uv` installed and available in PATH
- `docker` installed for local image validation
- `just` installed
- `actionlint` installed locally, or Docker available so `just workflow-lint`
  can fall back to the official `rhysd/actionlint` container
- GitHub repository with Actions enabled

## Local Developer Flow

Run the same commands CI executes:

```bash
just pr-test
```

If these pass locally, push your branch and open a pull request.

Important:

- You do not deploy a local image into GitHub Actions as a runner container.
- You commit the `Dockerfile` and workflow definitions.
- GitHub-hosted runners then rebuild the image from source on PRs, `main`, and release tags.

## Pull Request Gate Flow

On every PR, GitHub Actions runs:

- `CI` workflow:
  - workflow lint
  - lint (`just lint`)
  - typecheck (`just typecheck`)
  - tests (`just test`)
  - vault audit (`just vault-audit`)
  - dependency audit (`just dependency-audit`, run in the project venv)
- `Dependency Review` workflow:
  - blocks risky dependency changes
- `Docker` workflow:
  - image build (`just docker-build`)
  - runtime smoke (`just docker-smoke`)

Merge only when all required checks are green.

## Main Branch Flow

On merge/push to `main`:

- CI and dependency checks run again
- Docker workflow rebuilds from source and publishes GHCR images:
  - `ghcr.io/wgergely/vaultspec-core:main`
  - `ghcr.io/wgergely/vaultspec-core:sha-<shortsha>`

## Version Release Flow

Create and push a version tag:

```bash
git tag v0.1.1
git push origin v0.1.1
```

GitHub executes:

- `publish.yml` to build and publish package to PyPI
- `docker.yml` to rebuild from source and publish GHCR images:
  - `ghcr.io/wgergely/vaultspec-core:v0.1.1`
  - `ghcr.io/wgergely/vaultspec-core:latest`

## Required GitHub Configuration

### Repository Settings

- Enable Actions for the repository
- Protect `main` branch with required status checks:
  - `Lint and Type Check`
  - `Tests (ubuntu-latest)`
  - `Tests (windows-latest)`
  - `Vault Audit`
  - `Dependency Audit (pip-audit)`
  - `Dependency Review`
  - `Docker Build (PR Validation)`

### Package Permissions (GHCR)

- Ensure workflow token can write packages:
  - `permissions: packages: write` is present in `docker.yml`

### PyPI Trusted Publishing

- Configure PyPI trusted publisher for this repository and workflow
- Keep `publish.yml` with `id-token: write`

## Operational Notes

- `justfile` is the command authority. Keep command changes in `justfile` first.
- Workflows should call `just` recipes for local-equivalent checks.
- Registry publication should use Docker's official GitHub Actions rather than shelling out custom tag logic.
- `tests/test_automation_contracts.py` enforces the sync contract between
  workflows, Docker, and `justfile`.
