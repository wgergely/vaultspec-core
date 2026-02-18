# Getting Started

This guide walks you through installing vaultspec, running your first commands, and completing a full workflow cycle.

## Prerequisites

- **Python 3.13+** -- verify with `python --version`
- **NVIDIA GPU with CUDA 13.0+** -- required for RAG/search features. Verify with `nvidia-smi`
- **pip** -- Python package manager

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd vaultspec

# Install with RAG and development dependencies
pip install -e ".[rag,dev]"
```

The `rag` extra installs PyTorch (CUDA), sentence-transformers, and LanceDB. The `dev` extra installs testing tools (pytest, ruff, etc.).

## First Commands

vaultspec provides three CLI entry points:

| CLI | Purpose |
|-----|---------|
| `cli.py` | Manage agents, rules, skills, and config sync |
| `docs.py` | Vault operations: create, audit, index, search |
| `subagent.py` | Run sub-agents and MCP server |

All scripts live in `.vaultspec/lib/scripts/`.

### List available agents

```bash
python .vaultspec/lib/scripts/cli.py agents list
```

This shows all agent definitions in `.vaultspec/agents/`, each with a tier (HIGH, MEDIUM, LOW) that maps to model capability.

### List rules and skills

```bash
python .vaultspec/lib/scripts/cli.py rules list
python .vaultspec/lib/scripts/cli.py skills list
```

Rules constrain agent behavior. Skills map user intents to agent workflows.

### Audit the vault

```bash
python .vaultspec/lib/scripts/docs.py audit --summary
```

Shows document counts by type (ADR, audit, exec, plan, reference, research) and feature coverage.

## Create Your First Document

Use `docs.py create` to scaffold a new document from a template:

```bash
python .vaultspec/lib/scripts/docs.py create --type research --feature my-feature
```

This creates `.vault/research/YYYY-MM-DD-my-feature-research.md` with proper frontmatter (tags, date, related links) pre-filled from the research template.

Available types: `adr`, `audit`, `exec`, `plan`, `reference`, `research`.

## Build the Search Index

The search index enables semantic search over your vault documents. It requires a GPU.

```bash
# Incremental index (only new/changed files)
python .vaultspec/lib/scripts/docs.py index

# Full re-index
python .vaultspec/lib/scripts/docs.py index --full
```

First run downloads the embedding model (~270MB) and indexes all documents. Subsequent runs use incremental mtime-based change detection.

## Search the Vault

```bash
# Basic search
python .vaultspec/lib/scripts/docs.py search "protocol integration"

# With filters
python .vaultspec/lib/scripts/docs.py search "type:adr feature:rag search results"

# Limit results
python .vaultspec/lib/scripts/docs.py search "agent dispatch" --limit 10

# JSON output
python .vaultspec/lib/scripts/docs.py search "embedding model" --json
```

Search uses hybrid retrieval: BM25 keyword matching + ANN vector similarity, fused with Reciprocal Rank Fusion (RRF). See the [Search Guide](search-guide.md) for full syntax.

## Full Workflow Example

Here is a concrete example of the 5-phase workflow for "adding a new CLI command":

### Phase 1: Research

Tell your AI assistant:

> "Activate `vaultspec-research` to investigate best practices for CLI argument parsing in Python, focusing on argparse subcommand patterns."

This dispatches the `vaultspec-adr-researcher` agent, which produces a research artifact at `.vault/research/YYYY-MM-DD-cli-commands-research.md`.

### Phase 2: Specify

> "Activate `vaultspec-adr` to formalize our decision on the CLI command structure."

This creates an Architecture Decision Record at `.vault/adr/YYYY-MM-DD-cli-commands-adr.md`, documenting the chosen approach with rationale and tradeoffs.

### Phase 3: Plan

> "Activate `vaultspec-write` to create an implementation plan for the new CLI commands."

The `vaultspec-writer` agent produces a step-by-step plan at `.vault/plan/YYYY-MM-DD-cli-commands-plan.md`, referencing the ADR and research.

### Phase 4: Execute

> "Activate `vaultspec-execute` to implement the plan."

Executor agents (simple, standard, or complex depending on task difficulty) implement each step. Execution records are saved to `.vault/exec/YYYY-MM-DD-cli-commands/`.

### Phase 5: Verify

> "Activate `vaultspec-review` to audit the implementation."

The `vaultspec-code-reviewer` agent validates the code against the plan, checking for safety violations and intent compliance.

## Next Steps

- [Concepts](concepts.md) -- understand the SDD methodology, agent tiers, and protocol stack
- [Configuration](configuration.md) -- customize vaultspec with environment variables
- [Search Guide](search-guide.md) -- master the search syntax and understand GPU requirements
- [Framework Manual](../.vaultspec/README.md) -- deep dive into workflows, agents, and diagrams
