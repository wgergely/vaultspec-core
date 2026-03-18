# vaultspec-core

<p align="center">
  <img src="rsc/svg/vaultspec-agent-ok.svg" alt="vaultspec-core" width="180" />
</p>

<p align="center">

[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](./pyproject.toml)
[![CI](https://github.com/wgergely/vaultspec-core/actions/workflows/ci.yml/badge.svg)](https://github.com/wgergely/vaultspec-core/actions/workflows/ci.yml)
[![Docker](https://github.com/wgergely/vaultspec-core/actions/workflows/docker.yml/badge.svg)](https://github.com/wgergely/vaultspec-core/actions/workflows/docker.yml)
[![MCP](https://img.shields.io/badge/MCP-vaultspec--mcp-informational)](./.vaultspec/MCP.md)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

</p>








***Give your AI a structured process and a paper trail - so every decision gets made once, recorded, and built on.***

---

## What is vaultspec-core

vaultspec-core is a Python framework that wraps a structured pipeline around AI-assisted development. Research, decide, plan, execute, review - each stage produces a durable artifact in your repository. `.vaultspec/` holds the rules, templates, and agent personas that shape how AI tools behave. `.vault/` is where the work lands: research notes, decision records, plans, and execution logs.

Two entry points ship with the framework: the `vaultspec-core` CLI for managing your workspace, and `vaultspec-mcp`, an MCP (Model Context Protocol) server that exposes your workspace directly to AI tools like Claude Desktop and Cursor.

For the full directory structure and resource reference, see the [framework reference](./.vaultspec/README.md).

---

## Getting started

### Prerequisites

- Python 3.13 or later
- [uv](https://github.com/astral-sh/uv) - a fast Python package manager

### Install

```bash
uv pip install .
vaultspec-core --version
```

### Initialize a workspace

```bash
vaultspec-core install --target ./my-project
```

To target a specific tool:

```bash
vaultspec-core install claude --target ./my-project
```

After editing any framework files, re-sync:

```bash
vaultspec-core sync
```

---

## The development workflow

Every feature flows through five stages. The AI does the analytical work; you make the call at each checkpoint before work proceeds.

| Stage | You | The AI |
|---|---|---|
| **Research** | Review and approve the findings | Explores the problem, documents options |
| **Decide** | Approve the decision record | Drafts the decision based on research |
| **Plan** | Review and approve the implementation plan | Breaks the decision into concrete steps |
| **Execute** | Stay available if it gets stuck | Works through each step autonomously |
| **Review** | Read the report and decide if the work is ready | Audits the result, flags any issues |

Everything produced - findings, decisions, plans, execution records, and review reports - is saved in `.vault/`.

---

## Working with the vault

### Creating documents

```bash
vaultspec-core vault add research --feature search-api
```

Valid types: `adr`, `audit`, `exec`, `plan`, `reference`, `research`. The command writes a pre-populated template into the right `.vault/` subfolder with required frontmatter filled in.

### Listing and browsing

```bash
vaultspec-core vault list --feature search-api
vaultspec-core vault stats --feature search-api
```

### Running checks

```bash
vaultspec-core vault check all
```

Checks frontmatter validity, wiki-link resolution, feature document trails, and cross-references. Add `--fix` to auto-repair malformed frontmatter, wrong link format, and missing required fields:

```bash
vaultspec-core vault check all --fix
```

### Visualizing relationships

```bash
vaultspec-core vault graph --feature search-api
```

---

## Read more

| Guide | What it covers |
|---|---|
| [Framework reference](./.vaultspec/README.md) | Directory structure, resource tree, and sync model |
| [User guide](./.vaultspec/USERGUIDE.md) | End-to-end workflows, provider setup, hooks, and the MCP server |
| [CLI reference](./.vaultspec/CLI.md) | All commands, flags, and options for `vaultspec-core` |
| [MCP reference](./.vaultspec/MCP.md) | MCP server tools, configuration, and environment variables |

**Getting help:** Open an issue on [GitHub](https://github.com/wgergely/vaultspec-core/issues).

---

## Contributing and license

Contributions are welcome - bug reports, feature ideas, or pull requests. Browse what's in progress on [GitHub Issues](https://github.com/wgergely/vaultspec-core/issues).

vaultspec-core is released under the [MIT License](./LICENSE).
