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

---

## The Workflow

ValutSpec enforces a **Research → Specify → Plan → Execute → Verify**
workflow with a governed document trail - all tied together by **feature** tags.
These are the skills and agents you'll be using to develop a feature:

- **Research**: Gathers information, evidence and references for anchoring.
  - Skills: `vaultspec-research`, `vaultspec-reference`
  - Agents: `vaultspec-researcher`, `vaultspec-reference-auditor`
- **Specify**: Uses the gathered evidence to make binding architectural decisions.
  - Skills: `vaultspec-adr`, `vaultspec-adr-researcher`
  - Agents: `vaultspec-write`
- **Plan**: Convert ADRs into step-by-step implementation plans.
  - Skills: `vaultspec-write`
  - Agents: `vaultspec-writer`
- **Execute**: Implement the plan with specialized sub-agents.
  - Skills: `vaultspec-execute`
  - Agents: `vaultspec-[simple|standard|complex]-executor`
- **Verify**: Audit the implementation for safety and intent compliance.
  - Skills: `vaultspec-review`
  - Agents: `vaultspec-code-reviewer`

## Vault

The `.vault/` shadows the code and contains the expanding document trail for design
decisions and execution details.

> **_TIP:_** Use the **vaultspec-curate** skill, to edit maintain the quality and
> structure of the vault.

### Obsidian

You can use to navigate the vault using Obsidian. The graph view is especially
useful for visualization and see feature clusters, effort.

### Semantic Search

The bundled MCP server enables semantic search over the vault contents.
Consult CUDA requirements below. Core governance features (Research → Specify →
Plan → Execute → Verify) work without a GPU.

## Documentation

- [Concepts & Tutorial](.vaultspec/docs/concepts.md) -- worked example,
  SDD methodology, agents, and protocols
- [CLI Reference](.vaultspec/docs/cli-reference.md) -- all commands and
  configuration variables
- [Search Guide](.vaultspec/docs/search-guide.md) -- RAG search syntax,
  filter tokens, and GPU requirements
- [Framework Manual](.vaultspec/README.md) -- detailed workflow, agent
  reference, and diagrams

## Hooks

vaultspec supports event-driven hooks that fire automatically at key lifecycle
points in the workflow. Hooks are YAML files stored in `.vaultspec/rules/hooks/`
and execute whenever a lifecycle event fires — such as after creating a vault
document, updating the index, completing an audit, or running `sync-all`. Both
shell commands and agent dispatches are supported as hook actions, letting you
automate post-phase tasks like running linters, notifying agents, or triggering
follow-up reviews. See [`.vaultspec/docs/hooks-guide.md`](.vaultspec/docs/hooks-guide.md)
for the complete guide.

## CUDA Requirements

```bash
uv pip install -e ".[rag,dev]" --extra-index-url https://download.pytorch.org/whl/cu130
```

The `[rag]` optional dependency group powers the semantic vault search index
_(torch >= 2.9.0, CUDA 13.0+, compute capability >= 7.5)_.

 Always use `--extra-index-url`(not `--index-url`) when installing `[rag]` dependencies.
 Without it, the installer pulls CPU-only PyTorch from PyPI, which fails at runtime
 with `GPUNotAvailableError`.
