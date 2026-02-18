# Introducing vaultspec to Your Team

Your team's PR review process catches bugs. It does not catch AI agents making
architectural decisions that contradict the system design. It does not catch
an executor choosing the wrong abstraction because it had no ADR to reference.
It does not catch drift — the slow divergence of AI-generated code from the
architecture your team agreed on.

Code review is a correctness gate. vaultspec is a governance layer. They
solve different problems and work together.

This guide covers how to introduce vaultspec to an engineering team: shared
vault setup, rules enforcement, agent tiers, and the compliance angle that
increasingly matters for teams shipping AI-generated code.

## The Team Problem

When multiple developers use AI agents against a shared codebase without a
shared governance layer, the results are predictable:

- Agent A (Claude Code) makes an architectural decision in session 1. Agent B
  (Gemini CLI) contradicts it in session 4. Neither agent knew about the
  other's decision.
- Code reviews flag the contradiction, but the reviewer doesn't know which
  decision was correct — because neither was documented.
- The tech lead arbitrates. This happens repeatedly. Unstructured AI
  development creates a new class of architectural review burden that slows
  the team down.

vaultspec eliminates this by making the `.vault/` directory the shared
source of truth for architectural decisions. Decisions committed to `.vault/`
are visible to every agent on every session. Drift becomes detectable.

## Setup for a Team

### Share the vault in git

The `.vault/` directory should be committed to your repository:

```bash
git add .vault/
git commit -m "Initialize vault"
```

Every ADR, research artifact, and execution record is now shared across the
team. Any agent on any developer's machine can reference previous decisions.

### Sync rules to team members' tools

Run config sync to push vaultspec rules to each team member's tool config:

```bash
python .vaultspec/lib/scripts/cli.py config sync
```

This populates `.claude/CLAUDE.md`, `.gemini/GEMINI.md`, and root `AGENTS.md`
with the framework rules. Each team member runs this once after cloning.

### Establish agent tier conventions

vaultspec agents have three tiers that map to task complexity:

| Tier | Agents | Use for |
| :--- | :--- | :--- |
| HIGH | complex-executor, code-reviewer | Architecture, reviews |
| MED | standard-executor, docs-curator | Feature work |
| LOW | simple-executor | Docs, text changes |

Document your team's tier conventions in `.vaultspec/system/project.md` so
every agent inherits them.

## Governance for AI-Generated Code

The governance value of vaultspec for teams is threefold:

**Consistency** — Every significant AI-generated decision flows through the
same pipeline: research grounds the problem, an ADR formalizes the decision,
a plan structures the implementation, and a review validates the output. The
process is the same regardless of which developer or which AI tool is used.

**Reviewability** — When a senior engineer reviews AI-generated code, they
can trace it back to the ADR that justified it. "Why is this structured this
way?" now has a documented answer. Review quality improves because reviewers
have context.

**Audit trail** — The `.vault/` directory provides a machine-readable,
version-controlled record of every significant decision made by AI agents.
For teams in regulated industries, this is not optional — it is the evidence
that AI was used within a governed process.

## Compliance Angle

Engineering teams using AI agents to write code for regulated applications
face increasing scrutiny. The EU AI Act (full enforcement August 2026) and
similar frameworks require human oversight and technical documentation for
AI systems in scope.

A vaultspec `.vault/` directory is the natural implementation of these
requirements. Research artifacts document the problem space. ADRs document
the decision and alternatives. Plans provide evidence of human approval before
execution. Reviews confirm that implementation matched specification.

Before your first compliance audit that touches AI-generated code, have a
complete `.vault/` for every significant feature. The alternative is
attempting to reconstruct reasoning from git history after the fact.

## Rolling Out to the Team

A pragmatic rollout order:

1. Start with one feature using the full pipeline. Demonstrate the artifact
   trail to the team.
2. Mandate research and ADR for all architectural decisions. Execution
   records are optional initially.
3. Enable the full pipeline for all non-trivial features once the team has
   built the habit.

The pipeline's value compounds. The first ADR is overhead. The tenth is
reference material that saves two hours of archaeology.

## Further Reading

- [Concepts](../concepts.md) — full explanation of the governance model and
  agent architecture
- [Getting Started](../getting-started.md) — detailed installation and first
  workflow
- [CLI Reference](../cli-reference.md) — config sync, agent dispatch,
  and all commands
- [Search Guide](../search-guide.md) — semantic search across the shared
  vault
