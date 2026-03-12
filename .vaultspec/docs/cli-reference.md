# CLI Reference

## Overview

`vaultspec-core` is the packaged command-line interface for managing a vaultspec
workspace: vault documents, synced rule assets, configuration, system prompts,
hooks, and workspace checks.

`vaultspec-mcp` is a separate executable that exposes MCP tools for vault and
workspace queries. It is not a `vaultspec-core` subcommand.

Related guides:

- [README](../../README.md) for install and quick start
- [Vault Query Guide](./vault-query-guide.md) for MCP retrieval workflows
- [Hooks Guide](./hooks-guide.md) for hook configuration and events

## `vaultspec-core` Root Options

Use root options before the command or namespace:

```text
vaultspec-core [--target PATH] [--verbose] [--debug] [--version] <command> ...
```

| Option | Meaning |
| --- | --- |
| `-t`, `--target PATH` | Override the target workspace directory |
| `-v`, `--verbose` | Enable verbose logging |
| `-d`, `--debug` | Enable debug logging |
| `-V`, `--version` | Print the installed version and exit |

## Command Tree

```text
vaultspec-core
  vault
    add
    audit
  rules
    list add show edit remove rename sync
  skills
    list add show edit remove rename sync
  agents
    list add show edit remove rename sync
  config
    show sync
  system
    show sync
  hooks
    list run
  sync-all
  test
  doctor
  init
  readiness
```

## `vault`

Manage `.vault/` documents.

### Commands

```text
vaultspec-core vault add
vaultspec-core vault audit
```

### `vault add`

Create a vault document from a supported document type and feature name.

Typical usage:

```bash
vaultspec-core vault add --type research --feature cli-reference --title "Rewrite CLI reference"
```

Use this command when you want a new document scaffolded into `.vault/`.

### `vault audit`

Audit the vault for summary and verification issues.

Typical usage:

```bash
vaultspec-core vault audit
```

The live packaged interface exposes only `add` and `audit` under `vault`.

## `rules`

Manage files in the rules namespace.

### Commands

```text
vaultspec-core rules list
vaultspec-core rules add
vaultspec-core rules show
vaultspec-core rules edit
vaultspec-core rules remove
vaultspec-core rules rename
vaultspec-core rules sync
```

### High-signal flags

| Command | Key flags |
| --- | --- |
| `rules add` | `--name`, `--content`, `--force` |
| `rules remove` | `--force` |
| `rules sync` | `--prune`, `--dry-run` |

Example:

```bash
vaultspec-core rules add --name my-rule --content "Use explicit approvals for plan execution."
vaultspec-core rules sync --dry-run
```

## `skills`

Manage skill definitions.

### Commands

```text
vaultspec-core skills list
vaultspec-core skills add
vaultspec-core skills show
vaultspec-core skills edit
vaultspec-core skills remove
vaultspec-core skills rename
vaultspec-core skills sync
```

### High-signal flags

| Command | Key flags |
| --- | --- |
| `skills add` | `--name`, `--description`, `--force`, `--template` |
| `skills remove` | `--force` |
| `skills sync` | `--prune`, `--dry-run` |

Example:

```bash
vaultspec-core skills add --name docs-author --description "Writes concise user-facing docs"
vaultspec-core skills sync --prune
```

## `agents`

Manage agent definitions.

### Commands

```text
vaultspec-core agents list
vaultspec-core agents add
vaultspec-core agents show
vaultspec-core agents edit
vaultspec-core agents remove
vaultspec-core agents rename
vaultspec-core agents sync
```

### High-signal flags

| Command | Key flags |
| --- | --- |
| `agents add` | `--name`, `--description`, `--force` |
| `agents remove` | `--force` |
| `agents sync` | `--prune`, `--dry-run` |

Example:

```bash
vaultspec-core agents add --name docs-editor --description "Performs editorial review"
vaultspec-core agents sync --dry-run
```

There is no live `agents set-tier`, `--tier`, or `--template` surface in the
packaged CLI.

## `config`

Inspect or sync tool-facing configuration files.

### Commands

```text
vaultspec-core config show
vaultspec-core config sync
```

### High-signal flags

| Command | Key flags |
| --- | --- |
| `config sync` | `--dry-run`, `--force` |

Example:

```bash
vaultspec-core config show
vaultspec-core config sync --dry-run
```

`config sync` does not have a live `--prune` flag.

## `system`

Inspect or sync assembled system prompt output.

### Commands

```text
vaultspec-core system show
vaultspec-core system sync
```

### High-signal flags

| Command | Key flags |
| --- | --- |
| `system sync` | `--dry-run`, `--force` |

Example:

```bash
vaultspec-core system show
vaultspec-core system sync --force
```

`system sync` does not have a live `--prune` flag.

## `hooks`

List or manually run shell-based hooks loaded from `.vaultspec/rules/hooks`.

### Commands

```text
vaultspec-core hooks list
vaultspec-core hooks run <event> [--path PATH]
```

### Supported events

- `vault.document.created`
- `config.synced`
- `audit.completed`

### `hooks run`

`hooks run` accepts:

- positional `event`
- optional `--path`

Example:

```bash
vaultspec-core hooks run vault.document.created --path .vault/research/2026-03-11-cli-reference.md
```

Only shell hook actions are in scope for the live interface.

## Top-level Commands

### `sync-all`

Sync rules, skills, agents, config, and system outputs together.

Key flags: `--prune`, `--dry-run`, `--force`

```bash
vaultspec-core sync-all --dry-run
```

### `test`

Run the packaged test entry point with optional pytest passthrough arguments.

```text
vaultspec-core test [--category CATEGORY] [--module MODULE] [pytest args...]
```

| Option | Values |
| --- | --- |
| `-c`, `--category` | `all`, `unit`, `api`, `quality` |
| `-m`, `--module` | `cli`, `vault`, `protocol`, `core` |

Example:

```bash
vaultspec-core test --category unit --module cli -k sync
```

The CLI category surface is limited to the values above even if the underlying
test suite uses broader pytest markers.

### `doctor`

Run workspace and environment checks.

```bash
vaultspec-core doctor
```

No user-facing flags are important for the packaged interface.

### `init`

Initialize a vaultspec workspace scaffold.

Key flag: `--force`

```bash
vaultspec-core init
vaultspec-core init --force
```

### `readiness`

Report workspace readiness.

Key flag: `--json`

```bash
vaultspec-core readiness
vaultspec-core readiness --json
```

## `vaultspec-mcp`

`vaultspec-mcp` is a separate executable for MCP clients. It is not invoked as
`vaultspec-core mcp`.

### Tool Surface

| Tool | Purpose |
| --- | --- |
| `query_vault(query?, feature?, type?, related_to?, recent?, limit=20)` | Query vault documents |
| `feature_status(feature)` | Report the status of a feature |
| `create_vault_document(type, feature, title, extra_context="")` | Create a vault document |
| `list_spec_resources(resource)` | List framework resources by kind |
| `get_spec_resource(resource, name)` | Read a specific framework resource |
| `workspace_status(check=all\|readiness\|health)` | Report workspace status |
| `audit_vault(summary=True, verify=False, fix=False)` | Audit the vault |

This tool surface is the authoritative packaged MCP interface.

## Configuration Variables

The live packaged interface resolves these environment variables:

| Variable | Purpose |
| --- | --- |
| `VAULTSPEC_TARGET_DIR` | Target workspace directory |
| `VAULTSPEC_DOCS_DIR` | Vault docs directory name |
| `VAULTSPEC_FRAMEWORK_DIR` | Framework directory name |
| `VAULTSPEC_CLAUDE_DIR` | Claude output directory name |
| `VAULTSPEC_GEMINI_DIR` | Gemini output directory name |
| `VAULTSPEC_ANTIGRAVITY_DIR` | Antigravity output directory name |
| `VAULTSPEC_IO_BUFFER_SIZE` | I/O buffer size |
| `VAULTSPEC_TERMINAL_OUTPUT_LIMIT` | Captured terminal output limit |
| `VAULTSPEC_EDITOR` | Editor command for interactive edits |
