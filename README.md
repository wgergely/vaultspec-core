# vaultspec

> A governed development framework for AI agents

vaultspec enforces a **Research -> Specify -> Plan -> Execute -> Verify** workflow that turns AI coding assistants into accountable engineering partners.

## Why vaultspec?

- **Governance over speed** -- AI agents write code fast but lose context, skip steps, and produce inconsistent output. vaultspec adds structure: every change is researched, specified, planned, executed, and verified.
- **Documentation-first** -- the `.vault/` knowledge base creates a persistent trail of ADRs, research, plans, and execution records that survives context windows.
- **Multi-agent** -- specialized agents (researcher, planner, executor, reviewer) with tiered capability levels handle different kinds of work.
- **Multi-protocol** -- MCP for tool access, ACP for orchestration, A2A for agent-to-agent communication. Full stack.
- **Multi-tool** -- works with Claude Code, Gemini CLI, and Google Antigravity.

## Prerequisites

- Python 3.13+
- NVIDIA GPU with CUDA 13.0+ (required for RAG/search features)
- pip

## Quick Start

```bash
# Clone and install
git clone <repository-url>
cd vaultspec
pip install -e ".[rag,dev]"

# List available agents
python .vaultspec/lib/scripts/cli.py agents list

# Create your first research document
python .vaultspec/lib/scripts/docs.py create --type research --feature my-feature

# Build the search index (requires GPU)
python .vaultspec/lib/scripts/docs.py index

# Search the vault
python .vaultspec/lib/scripts/docs.py search "my query"
```

## The Workflow

```
Research  ->  Specify  ->  Plan  ->  Execute  ->  Verify
   |             |           |          |           |
research/     adr/        plan/      exec/      review
```

1. **Research** (`vaultspec-research`) -- explore the problem space, find patterns and libraries
2. **Specify** (`vaultspec-adr`) -- formalize decisions in Architecture Decision Records
3. **Plan** (`vaultspec-write`) -- convert ADRs into step-by-step implementation plans
4. **Execute** (`vaultspec-execute`) -- implement the plan with specialized sub-agents
5. **Verify** (`vaultspec-review`) -- audit the implementation for safety and intent compliance

Each phase produces artifacts in `.vault/` that form a traceable chain from research to code.

## Documentation

- [Getting Started](docs/getting-started.md) -- step-by-step setup and first workflow
- [Concepts](docs/concepts.md) -- SDD methodology, agents, protocols, architecture
- [Configuration](docs/configuration.md) -- environment variables and settings
- [Search Guide](docs/search-guide.md) -- RAG search syntax and GPU requirements
- [Framework Manual](.vaultspec/README.md) -- detailed workflow, agent reference, and diagrams

## Project Structure

```
.vaultspec/          # Framework: agents, rules, skills, templates, library
  agents/            # Agent persona definitions with tier-based capabilities
  rules/             # Behavioral constraints synced to tool configs
  skills/            # User-invocable workflow skills
  templates/         # Document templates for .vault/ artifacts
  lib/               # Python library, CLI scripts, and test suite
.vault/              # Knowledge vault: ADRs, research, plans, exec records, audits
docs/                # Human documentation
```

## Agent Reference

| Agent | Tier | Role |
| :--- | :--- | :--- |
| `vaultspec-adr-researcher` | HIGH | Lead Researcher |
| `vaultspec-writer` | HIGH | Planner |
| `vaultspec-complex-executor` | HIGH | Senior Engineer |
| `vaultspec-code-reviewer` | HIGH | Reviewer and Safety Officer |
| `vaultspec-standard-executor` | MEDIUM | Engineer |
| `vaultspec-docs-curator` | MEDIUM | Documentation Librarian |
| `vaultspec-reference-auditor` | MEDIUM | Code Auditor |
| `vaultspec-simple-executor` | LOW | Junior Engineer |

See the [Framework Manual](.vaultspec/README.md) for detailed agent descriptions and usage.

## Status

Version 0.1.0 -- active development.

## Development

> [!CAUTION]
> **Framework Development:** This repository is for the development of the framework itself. **DO NOT** run `cli.py config sync` or similar commands to "install" the framework into this root directory. The `.vaultspec/` folder here is the source of truth, and syncing it to the root (e.g., creating a root `AGENTS.md`) will cause recursive context issues and potential data loss during development.
