---
name: vaultspec-cli
---

# Vaultspec Core CLI

Use the `vaultspec-core` CLI to manage and the `.vault/` contents. Use it to sync
framework content, manage `.vault/` documents, and inspect vault health.

## Usage

If the current virtual environment has `vaultspec-core` installed, run it
directly as `vaultspec-core` or `uv run vaultspec-core` in uv managed environments.

## CLI Commands

Vault healt and management:

```
vault add <type> <name> Create a new .vault/ document
vault list [--type T]   List vault documents
vault check [checker]   Run vault health checks
vault stats             Show vault statistics
```

Spec management:

```
install [provider]      Deploy the framework
sync [provider]         Sync rules, skills, agents, configs
doctor                  Diagnose workspace health
spec rules list         List framework rules
spec skills list        List workflow skills
spec agents list        List agent definitions
spec system show        Show assembled system prompts
```
