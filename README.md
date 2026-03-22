# vaultspec-core

[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](./pyproject.toml)
[![CI](https://github.com/wgergely/vaultspec-core/actions/workflows/ci.yml/badge.svg)](https://github.com/wgergely/vaultspec-core/actions/workflows/ci.yml)
[![Docker](https://github.com/wgergely/vaultspec-core/actions/workflows/docker.yml/badge.svg)](https://github.com/wgergely/vaultspec-core/actions/workflows/docker.yml)
[![MCP](https://img.shields.io/badge/MCP-vaultspec--mcp-informational)](./.vaultspec/MCP.md)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

______________________________________________________________________

## A research and decision driven framework for your coding agents - with a paper trail.

Vaultspec is a spec-driven development rulebook for your AI coders. It enforces a structured pipeline around AI-assisted development - research, decide, plan, execute, review - and provides tools to manage the document storage.

Each stage produces durable markdown artifacts in your repository that allow collaborating agents to share context and you to track development progress.

______________________________________________________________________


## How it works

vaultspec-core structures AI-assisted development into a repeatable pipeline centered around `features`. Two directories form the backbone:

- **`.vaultspec/`** holds the framework configuration - rules, templates, agent personas, and system prompts that shape how AI tools behave.
- **`.vault/`** is the paper trail - research notes, architecture decision records (ADRs), implementation plans, execution logs, and review and audit trails.

Two entry points ship with the framework:

- **`vaultspec-core`** is the CLI that manages your workspace - installing, syncing, and validating framework resources. See the [CLI reference](./.vaultspec/CLI.md) for the full command surface.
- **`vaultspec-mcp`** is an [MCP](https://modelcontextprotocol.io/) server that exposes vault discovery and document creation to MCP-capable clients like Claude Code. See the [MCP reference](./.vaultspec/MCP.md) for setup and tool documentation.

The [framework manual](./.vaultspec/README.md) walks through the development workflow and explains how to customize rules, skills, agents, and system prompts.

______________________________________________________________________

## Getting started

### Prerequisites

- Python 3.13 or later
- [uv](https://github.com/astral-sh/uv) - a fast Python package manager

### Install from source

vaultspec-core is not yet published on PyPI. Install from the repository:

```bash
git clone https://github.com/wgergely/vaultspec-core.git
cd vaultspec-core
uv sync

vaultspec-core --version
```

### Initialize a workspace

```bash
vaultspec-core install --target ./my-project
```

This scaffolds `.vaultspec/` and `.vault/` inside the target directory, seeds the builtin rules, agents, skills, and templates, syncs resources to provider config directories, and writes an `.mcp.json` for MCP-capable clients.

To install for a specific AI tool only:

```bash
vaultspec-core install claude --target ./my-project
```

After editing any framework files under `.vaultspec/`, re-sync to push changes to provider directories:

```bash
vaultspec-core sync
```

### Start using it

Open your AI tool in the project directory. The `install` step synced rules, skills, and agent personas into each provider's config directory (`.claude/`, `.gemini/`, `.agents/`, `.codex/`) and wrote an `.mcp.json` for MCP-capable clients. Your AI tool will pick these up automatically.

The framework requires research and architectural decisions before coding begins. Just describe what you want to build in natural language:

> "Research options for adding full-text search to the API"

The synced rules guide the AI to follow the pipeline - it will produce structured research findings in `.vault/research/`, then progress through architectural decisions, planning, execution, and review. Each stage writes records to `.vault/` and references the output of earlier stages.

You can also invoke skills explicitly to start a specific stage. The bundled skills (`vaultspec-research`, `vaultspec-adr`, `vaultspec-write`, `vaultspec-execute`, `vaultspec-code-review`) read the relevant vault records and structure the AI's output accordingly.

The [framework manual](./.vaultspec/README.md) walks through each stage in detail with examples.

______________________________________________________________________

## The development workflow

Every feature flows through five stages. The AI does the analytical work; you approve each checkpoint before the next stage starts.

| Stage        | You                                          | The AI                                  |
| ------------ | -------------------------------------------- | --------------------------------------- |
| **Research** | Review and approve the findings              | Explores the problem, documents options |
| **Decide**   | Approve the decision record                  | Drafts an ADR based on research         |
| **Plan**     | Review and approve the implementation plan   | Breaks the decision into concrete steps |
| **Execute**  | Stay available if the AI gets stuck          | Works through each step autonomously    |
| **Review**   | Read the report and decide if the work ships | Audits the result, flags any issues     |

Everything produced - findings, ADRs, plans, execution records, and review reports - is saved in `.vault/`.

______________________________________________________________________

## Working with the vault

The `vault` subcommand manages documents in `.vault/`. A few common operations:

```bash

# Scaffold a new document from a template

vaultspec-core vault add research --feature search-api

# List and inspect documents

vaultspec-core vault list --feature search-api
vaultspec-core vault stats --feature search-api

# Validate frontmatter, links, and cross-references (--fix to auto-repair)

vaultspec-core vault check all --fix

# Visualize the dependency graph for a feature

vaultspec-core vault graph --feature search-api
```

Valid document types: `adr`, `audit`, `exec`, `plan`, `reference`, `research`. See the [CLI reference](./.vaultspec/CLI.md#vault-commands) for the full command surface.

______________________________________________________________________

## Further reading

| Guide                                      | What it covers                                        |
| ------------------------------------------ | ----------------------------------------------------- |
| [Framework manual](./.vaultspec/README.md) | Development workflow, skills, and customization       |
| [CLI reference](./.vaultspec/CLI.md)       | All commands, flags, and options for `vaultspec-core` |
| [MCP reference](./.vaultspec/MCP.md)       | MCP server tools, setup, and configuration            |

### Getting help

Open an issue on [GitHub](https://github.com/wgergely/vaultspec-core/issues).

______________________________________________________________________

## Contributing and license

Contributions are welcome - bug reports, feature ideas, or pull requests. Browse what's in progress on [GitHub Issues](https://github.com/wgergely/vaultspec-core/issues).

vaultspec-core is released under the [MIT License](./LICENSE).
