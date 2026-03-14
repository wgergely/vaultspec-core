# vaultspec-core

_Provisional headline: governed workflows for AI-assisted engineering._

[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](./pyproject.toml)
[![Tests](https://github.com/wgergely/vaultspec-core/actions/workflows/ci.yml/badge.svg)](https://github.com/wgergely/vaultspec-core/actions/workflows/ci.yml)
[![Docker](https://github.com/wgergely/vaultspec-core/actions/workflows/docker.yml/badge.svg)](https://github.com/wgergely/vaultspec-core/actions/workflows/docker.yml)
![Docker Requirement](https://img.shields.io/badge/docker-optional-lightgrey.svg)
[![MCP](https://img.shields.io/badge/MCP-vaultspec--mcp-informational)](./.vaultspec/docs/vault-query-guide.md)

`vaultspec-core` is a Python package for spec-driven workspace management.

It operates a workspace around structured `.vaultspec/` and `.vault/`
artifacts: initialize the workspace, sync framework resources, create and audit
vault records, inspect hooks, assess readiness, and expose the same workspace
through a local MCP server.

> [!IMPORTANT]
> CI is enforced on both push and pull requests. Every change is gated by lint,
> type checks, tests, vault audit verification, dependency vulnerability
> checks, and Docker build/publish validation.
> Local Docker builds are developer smoke checks. GitHub Actions rebuilds from
> source and publishes images to GHCR on `main` and version tags.

## Headline Options

Pick one as the final project strapline:

1. `vaultspec-core: governed workflows for AI-assisted engineering`
2. `Ship AI-assisted changes with auditable specs, plans, and execution records`
3. `A spec-driven runtime for disciplined AI engineering in local workspaces`
4. `From idea to verified delivery: research, decisions, plans, execution`
5. `Make AI coding accountable: structured workflows, durable records, real audits`

## What It Ships

Installing the package gives you two executables:

- `vaultspec-core` for workspace setup, vault operations, framework resource sync,
  hooks, and readiness/doctoring
- `vaultspec-mcp` for a local stdio MCP server over the same workspace

## Requirements

- Python `3.13+`
- Docker is **not required** for local development or CI

## Install

Verified source install:

```bash
python -m pip install .
```

Optional build step, if you need distributable artifacts:

```bash
python -m build
```

## Quick Start

Create or enter a workspace, then initialize it:

```bash
vaultspec-core init
```

Sync framework resources into the workspace:

```bash
vaultspec-core sync-all
```

Create a vault artifact:

```bash
vaultspec-core vault add --type research --feature example-feature --title "Initial research"
```

Audit the vault:

```bash
vaultspec-core vault audit --summary
```

Inspect available hooks:

```bash
vaultspec-core hooks list
```

Check workspace health when needed:

```bash
vaultspec-core readiness
vaultspec-core doctor
```

## Operating Model

`vaultspec-core` is workspace-bound: run it inside a workspace that already contains
`.vaultspec/`, or create one with `vaultspec-core init`.

At a high level, the live CLI covers:

- workspace setup and health: `init`, `readiness`, `doctor`
- framework resource sync: `sync-all`
- vault artifacts: `vault add`, `vault audit`
- workspace surfaces and configuration: `rules`, `skills`, `agents`, `config`,
  `system`, `hooks`
- test surface: `test`

Use the CLI reference for the full command tree and option details.

## MCP Server

`vaultspec-core` includes `vaultspec-mcp`, a local stdio MCP server for
vault-centric workspace access. The client launches it as a subprocess and
communicates over stdin/stdout, so protocol output must stay on stdout and logs
should go to stderr.

Minimal MCP client configuration example:

```json
{
  "mcpServers": {
    "vaultspec-core": {
      "command": "vaultspec-mcp",
      "args": [],
      "env": {
        "VAULTSPEC_TARGET_DIR": "/absolute/path/to/workspace"
      }
    }
  }
}
```

The live MCP server is separate from the CLI. There is no live
`vaultspec-core mcp` subcommand.

## Documentation

- [CLI Reference](./.vaultspec/docs/cli-reference.md) for commands, options, and environment variables
- [Vault Query Guide](./.vaultspec/docs/vault-query-guide.md) for MCP retrieval workflows
- [Hooks Guide](./.vaultspec/docs/hooks-guide.md) for hook events and shell actions
- [Concepts](./.vaultspec/docs/concepts.md) for the workspace and artifact model
- [Documentation Workflow](./.vaultspec/docs/documentation-workflow.md) for bounded research, authoring, and editorial review
- [GitHub Workflows](./.vaultspec/docs/github-workflows.md) for CI/CD gates and publishing flow
- [Release & Deploy Runbook](./.vaultspec/docs/release-deploy-runbook.md) for local-to-cloud release steps and required GitHub settings
- [Framework Manual](./.vaultspec/README.md) for `.vaultspec/` structure and framework resources
