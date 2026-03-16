---
name: vaultspec-agents
---

# Agent Definitions

Agent definitions are persona files that define specialized roles for the
development pipeline. Each persona specifies a tier, mode (read-only or
read-write), available tools, and behavioral guidelines.

## Utilisation

Agent personas can be utilised in multiple ways, depending on the host CLI's
capabilities and the task's complexity:

- **Direct**: The host CLI loads the persona and operates under its guidelines.
- **Delegated**: The current agent delegates a task to another agent persona,
  using whatever dispatch mechanism the host CLI provides (CLI subcommand, MCP
  tool call, or built-in delegation).
- **Team**: Multiple agent personas collaborate as a self-orchestrating unit
  under shared vaultspec rules.

The choice of mechanism is determined by the host environment. The framework
does not mandate a specific dispatch protocol.

## Available Personas

| Persona | Tier | Role |
|---------|------|------|
| `vaultspec-adr-researcher` | HIGH | Research & ADR formulation |
| `vaultspec-researcher` | HIGH | Discovery & synthesis |
| `vaultspec-code-reference-agent` | MEDIUM | External codebase pattern audit |
| `vaultspec-write-planr` | HIGH | Plan creation & task orchestration |
| `vaultspec-high-executor` | HIGH | Complex architectural implementation |
| `vaultspec-standard-executor` | MEDIUM | Standard feature work |
| `vaultspec-low-executor` | LOW | Straightforward edits & fixes |
| `vaultspec-code-reviewer` | HIGH | Safety & intent audit |
| `vaultspec-docs-curator` | MEDIUM | Vault hygiene & documentation |
