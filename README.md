# vaultspec-core

`vaultspec-core` is a Python package for spec-driven workspace management.

It operates a workspace around structured `.vaultspec/` and `.vault/`
artifacts: initialize the workspace, sync framework resources, create and audit
vault records, inspect hooks, assess readiness, and expose the same workspace
through a local MCP server.

## What It Ships

Installing the package gives you two executables:

- `vaultspec-core` for workspace setup, vault operations, framework resource sync,
  hooks, and readiness/doctoring
- `vaultspec-mcp` for a local stdio MCP server over the same workspace

## Requirements

- Python `3.13+`

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
- [Framework Manual](./.vaultspec/README.md) for `.vaultspec/` structure and framework resources
