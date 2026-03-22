# Vaultspec Framework Manual

Vaultspec is a governed development framework for AI-assisted engineering. For installation and project overview, read the [repository README](../README.md).

Use this manual to develop features from initial research through to shipped code. Every step produces a durable record in `.vault/`, so you make decisions once and build on them.

## How to Start a New Feature

Starting a feature means working through a structured sequence: research, decide, plan, execute, and review. You approve each phase before the next begins.

### Research

Ask your AI tool to research the problem space. Describe what you're trying to build and what you need to understand before committing to an approach.

> "Research authentication options for the API gateway - compare JWT, session tokens, and OAuth2"

The `vaultspec-research` skill explores trade-offs, documents options, and writes structured findings to `.vault/research/`. Review the output, correct any gaps, and approve when you're satisfied the problem space is well understood.

Depending on the complexity of the feature, you may want to do multiple rounds of research. Each round produces its own record, and later stages reference all of them.

### Grounding Research in Code

If you need to explicitly ground the research against an existing codebase - understanding how a system currently works, finding reference implementations, or auditing existing patterns - invoke the `vaultspec-code-research` skill.

> "How does the notification service currently handle delivery retries? Show me the retry logic and backoff strategy."

This produces a `.vault/reference/` record with code-grounded analysis: actual snippets, architectural observations, and patterns extracted from the codebase. These reference records feed directly into the next phase alongside your research.

You don't always need code research. For greenfield features or well-understood domains, general research may be enough. For features that touch existing systems, code research prevents decisions based on wrong assumptions.

### Architectural Decisions

Once you've gathered enough context, formalize it into concrete architectural decisions using the `vaultspec-adr` skill. An Architecture Decision Record (ADR) draws on the research findings and captures binding decisions about the approach.

> "Create an ADR recommending PostgreSQL full-text search for the REST API based on the research findings"

The ADR lands in `.vault/adr/` and captures the context, the decision, its consequences, and links back to the research and reference records that informed it. ADRs are binding - they define the boundaries, library dependencies, and shape of the feature. The plan that follows must conform to what the ADR specifies.

Review the ADR carefully. This is where you commit to an approach. Sign off before moving to planning.

### Planning

With approved ADRs in hand, call the `vaultspec-write` skill to produce an implementation plan. It reads the ADR and breaks the decision into phased, concrete steps.

> "Write an implementation plan for the search feature based on the ADR"

The plan lands in `.vault/plan/` and defines what gets built, in what order, and with what acceptance criteria. Review the scope - confirm the phases make sense, nothing is missing, and nothing overreaches the ADR's boundaries. Approve before execution begins.

### Execution

Once the plan is approved, you have options for how to execute it.

**Direct execution.** Call the `vaultspec-execute` skill to work through the plan step by step. The AI delegates to specialized agent personas defined in the framework, each with a specific role and tool access level. Step records land in `.vault/exec/`.

> "Execute the search implementation plan"

**Parallel sub-agents.** For larger features, execution can dispatch multiple agents working on independent steps simultaneously, using the agent definitions bundled with the framework.

Regardless of execution mode, code review is mandatory after completing a step or the full plan.

### Review and Auditing

After execution, invoke the `vaultspec-code-review` skill to audit the completed work for safety, intent, and quality.

> "Review the changes from the search implementation"

The review produces a `.vault/audit/` record with issues triaged by severity (LOW, MEDIUM, HIGH, CRITICAL). Critical and high-severity issues must be resolved before the feature closes. A clean review means the work is ready to ship.

For ongoing vault maintenance - fixing broken links, validating frontmatter, cleaning up stale references - use the `vaultspec-curate` skill.

> "Audit the vault for broken links and missing references"

## Customizing the Framework

Everything under `.vaultspec/rules/` is yours to edit. The `spec` CLI group manages these resources without requiring you to touch files directly:

```bash

# Add a custom rule

vaultspec-core spec rules add --name my-project-conventions

# Add a skill with a description

vaultspec-core spec skills add --name my-deploy --description "Deploy to staging"

# List what you have

vaultspec-core spec rules list
vaultspec-core spec skills list
vaultspec-core spec agents list
```

After any change, sync pushes your framework content into each provider's config directory (`.claude/`, `.gemini/`, `.agents/`, `.codex/`):

```bash
vaultspec-core sync              # all providers
vaultspec-core sync claude       # one provider
vaultspec-core sync --dry-run    # preview without writing
```

See the [CLI reference](./CLI.md#spec-commands) for the full `spec` command surface.

## Managing Vault Records

The `vault` CLI group manages documents in `.vault/` - creating from templates, listing, validating, and visualizing dependencies. See the [CLI reference](./CLI.md#vault-commands) for all commands and options.

## MCP Integration

The MCP server is an alternative integration path for MCP-capable clients like Claude Code. It exposes vault discovery and document creation over stdio transport without requiring file-based sync. `vaultspec-core install` scaffolds an `.mcp.json` that invokes the server via `uv run python -m vaultspec_core.mcp_server.app` (module invocation avoids binary locking on Windows). See the [MCP reference](./MCP.md) for setup and tool documentation.

## Related Documentation

| Document                          | What it covers                                        |
| --------------------------------- | ----------------------------------------------------- |
| [Repository README](../README.md) | Project overview, installation, and getting started   |
| [CLI Reference](./CLI.md)         | All commands, flags, and options for `vaultspec-core` |
| [MCP Reference](./MCP.md)         | MCP server tools, setup, and configuration            |

For bug reports and feature requests, open an issue on the [vaultspec-core issue tracker](https://github.com/wgergely/vaultspec-core/issues).
