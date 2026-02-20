# VaultSpec

![CI](https://github.com/wgergely/vaultspec/actions/workflows/ci.yml/badge.svg)
![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
![Status: Alpha](https://img.shields.io/badge/status-alpha-orange)

The workflow leaves a managed document trail, **the vault**. The vault is
traceable and trackable: developers and agents can find the research that
justified decisions, the ADR that formalized them, the plan the agents
executed, and the individual agent summaries who coded them. It is a living
knowledge base that grows with your codebase, ensuring that every decision
is documented and auditable.

ValutSpec enforces a **Research → Specify → Plan → Execute → Verify**
workflow with a governed document trail.

---

## The Workflow

VaultSpec enformces the following workflow for major features:

- **Research**: Gathers information, evidence and references for anchoring.
  - Skills: `vaultspec-research`, `vaultspec-reference`
  - Agents: `vaultspec-researcher`, `vaultspec-reference-auditor`
- **Specify**: Uses gathered evidence to make architectural decisions.
  These are considered formal and binding.
  - Skills: `vaultspec-adr`, `vaultspec-adr-researcher`
  - Agents:
- **Plan**: Convert ADRs into step-by-step implementation plans.
  - Skills: `vaultspec-write` | Agents: `vaultspec-writer`
- **Execute**: Implement the plan with specialized sub-agents.
  - Skills: `vaultspec-execute` | Agents: `vaultspec-*-executor`
- **Verify**: Audit the implementation for safety and intent compliance.
  - Skills: `vaultspec-review` | Agents: `vaultspec-code-reviewer`

Each phase produces artifacts in `.vault/` that form a traceable chain from
research to code.

## Prerequisites

- Python 3.13+
- pip
- **NVIDIA GPU** with CUDA 13.0+ and compute capability >= 7.5 (Turing+: RTX 2000+, T4+, A-series, H-series) -- required only for the RAG index backend (the `[rag]` optional dependency group that powers semantic search). Core governance features (Research → Specify → Plan → Execute → Verify) work without a GPU.

## Quick Start

```bash
# Clone and install
git clone https://github.com/wgergely/vaultspec
cd vaultspec
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate
pip install -e ".[rag,dev]" --extra-index-url https://download.pytorch.org/whl/cu130
```

> **Note:** The `[rag]` optional dependency group powers the semantic search index
> (torch >= 2.9.0, CUDA 13.0+, compute capability >= 7.5). Core governance features
> (Research → Specify → Plan → Execute → Verify) work without a GPU — omit `[rag]`
> and skip the `docs.py index` step. Always use `--extra-index-url` (not `--index-url`)
> when installing `[rag]` dependencies: without it, pip installs CPU-only PyTorch from
> PyPI, which fails at runtime with `GPUNotAvailableError`.

```bash
# Verify your installation
python .vaultspec/lib/scripts/cli.py doctor

# List available agents
python .vaultspec/lib/scripts/cli.py agents list

# Create your first research document
python .vaultspec/lib/scripts/docs.py create --type research --feature my-feature

# Build the search index (requires GPU)
python .vaultspec/lib/scripts/docs.py index

# Search the vault
python .vaultspec/lib/scripts/docs.py search "my query"
```

## Worked Example

Here is what a governed feature looks like end to end. Each phase invokes
a skill; each skill produces an artifact in `.vault/`.

```text
/vaultspec-research   →  .vault/research/2026-02-18-health-endpoint-research.md
/vaultspec-adr        →  .vault/adr/2026-02-18-health-endpoint-adr.md
/vaultspec-write      →  .vault/plan/2026-02-18-health-endpoint-phase1-plan.md
/vaultspec-execute    →  .vault/exec/2026-02-18-health-endpoint/step1..N.md
/vaultspec-review     →  .vault/exec/2026-02-18-health-endpoint/review.md
```

Every decision is traceable from research to code. See the
[Concepts & Tutorial](.vaultspec/docs/concepts.md) for the full worked example
with sample artifact output at each phase.

## Documentation

- [Concepts & Tutorial](.vaultspec/docs/concepts.md) -- worked example,
  SDD methodology, agents, and protocols
- [CLI Reference](.vaultspec/docs/cli-reference.md) -- all commands and
  configuration variables
- [Search Guide](.vaultspec/docs/search-guide.md) -- RAG search syntax,
  filter tokens, and GPU requirements
- [Framework Manual](.vaultspec/README.md) -- detailed workflow, agent
  reference, and diagrams

## Project Structure

```text
.vaultspec/          # Framework: agents, rules, skills, templates, library
  agents/            # Agent persona definitions with tier-based capabilities
  rules/             # Behavioral constraints synced to tool configs
  skills/            # User-invocable workflow skills
  templates/         # Document templates for .vault/ artifacts
  lib/               # Python library, CLI scripts, and test suite
.vault/              # Knowledge vault: ADRs, research, plans, exec records, audits
  .vaultspec/docs/   # Deployed documentation: concepts, CLI reference, search guide
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

See the [Framework Manual](.vaultspec/README.md) for detailed agent
descriptions and usage.

## Status

Version 0.1.0 -- active development.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines and warnings.
