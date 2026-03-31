---
name: vaultspec-cli
---

# vaultspec-core CLI

This project is managed by the `vaultspec-core` CLI. Use it to sync
framework content, manage vault documents, and inspect workspace health.

## Running the CLI

If the current virtual environment has `vaultspec-core` installed, run it
directly:

```
vaultspec-core <command>
```

Otherwise, use `uv run` to invoke it from the project's managed environment:

```
uv run vaultspec-core <command>
```

## Commands

```
vaultspec-core install [provider]      Deploy the framework
vaultspec-core sync [provider]         Sync rules, skills, agents, configs
vaultspec-core doctor                  Diagnose workspace health
vaultspec-core spec rules list         List framework rules
vaultspec-core spec skills list        List workflow skills
vaultspec-core spec agents list        List agent definitions
vaultspec-core spec system show        Show assembled system prompts
vaultspec-core vault add <type> <name> Create a new .vault/ document
vaultspec-core vault list [--type T]   List vault documents
vaultspec-core vault check [checker]   Run vault health checks
vaultspec-core vault stats             Show vault statistics
```

## Example

```
uv run vaultspec-core sync --dry-run
uv run vaultspec-core vault add research my-feature
uv run vaultspec-core doctor
```
