---
title: "What is Spec-Driven Development?"
date: 2026-02-18
type: blog
tags: [sdd, methodology, ai-agents, specifications]
---

## What is Spec-Driven Development?

Software development methodologies have always been about one thing: making
the gap between intent and implementation smaller, more visible, and more
controllable. Test-Driven Development made that gap measurable through tests.
Behavior-Driven Development made it legible through natural language scenarios.
Spec-Driven Development (SDD) makes it traceable through structured
specifications that persist as first-class artifacts throughout the development
lifecycle.

SDD is not a new idea. It is a formalization of practices that disciplined
engineering teams have used for decades. What is new is the urgency: in the
age of AI coding agents, specifications are no longer a nice-to-have. They
are the primary mechanism by which human intent is reliably transmitted to
machine execution.

## Definition: Specifications as First-Class Artifacts

In traditional software development, specifications — when they exist at all
— are ephemeral. They live in Jira tickets, Slack threads, or the engineer's
head. They are consumed and discarded. By the time the code is written, the
specification is gone.

Spec-Driven Development inverts this. Specifications are first-class
artifacts: they are written before code, stored in version control, and
maintained alongside the code they govern. A specification in SDD is not a
throwaway document. It is a durable record of intent that can be referenced,
audited, and updated.

The key insight is that a specification is not just documentation of what
was decided. It is documentation of *why* it was decided, what alternatives
were considered, and what constraints applied. This is the information that
is most valuable and most frequently lost.

In SDD, every significant decision produces an artifact. Those artifacts form
a chain — from the original problem statement, through research and decision
records, through the implementation plan, through execution logs, to the final
code review. At any point, you can trace any line of code back to the decision
that justified it.

## How SDD Differs from TDD and BDD

The three methodology families share a common ancestor — the recognition that
defining expected behavior before writing code produces better outcomes. But
they operate at different levels of abstraction and serve different purposes.

| Dimension | TDD | BDD | SDD |
| :--- | :--- | :--- | :--- |
| Artifact | Tests | Scenarios | Records + plans |
| Author | Developer | Dev + QA + BA | Architect + AI |
| Focus | Correctness | Behavior | Traceability |
| When | Before impl | Before impl | Before impl |
| Persisted | Test files | Gherkin files | `.vault/` docs |
| Answers | "Work?" | "Behave right?" | "Why this way?" |
| Suits | Unit checks | Acceptance | Accountability |

TDD and BDD are primarily verification methodologies. They tell you whether
the code does what you expect. SDD is a *governance* methodology. It tells
you whether the code was built the right way, for the right reasons, with the
right oversight.

SDD is complementary to both. A mature engineering process will use TDD for
unit verification, BDD for acceptance testing, and SDD to ensure that the
architectural decisions behind the implementation are documented and traceable.
They operate at different layers and do not compete.

## The Five-Phase Pipeline

SDD as implemented in vaultspec follows a five-phase pipeline. Each phase
produces a durable artifact. Each artifact is a dependency for the next phase.
The chain is enforced, not optional.

### Phase 1: Research

Before any decision is made, the problem space is explored. A research agent
or engineer investigates existing patterns, evaluates libraries, surveys
alternatives, and identifies constraints. The output is a research artifact
that captures findings in a structured format.

Research is the grounding layer. It is what prevents decisions from being made
on the basis of assumption or convention. In an AI-assisted workflow, it is
what prevents the agent from hallucinating a solution based on training data
that may be outdated or domain-inappropriate.

### Phase 2: Specify

Research findings are formalized into an Architecture Decision Record (ADR).
The ADR captures: the decision made, the alternatives considered, the
constraints that applied, and the rationale for the choice. It is binding —
all subsequent phases must align with it.

The ADR is the memory layer. It is the document that a future engineer or
agent can reference to understand why the code is structured the way it is.
Without it, that understanding evaporates the moment the session ends.

### Phase 3: Plan

The ADR is converted into a step-by-step implementation plan. The plan is
concrete: it specifies what files will be changed, what components will be
created, and in what order. It is presented to a human stakeholder for
approval before execution begins.

The approval gate is not bureaucratic overhead. It is the human oversight
mechanism that ensures the plan is coherent with organizational intent before
resources are committed. It is also the moment at which the human can catch
errors or misalignments that neither the research nor the ADR surfaced.

### Phase 4: Execute

Implementation agents carry out the plan step by step. Each completed step
produces an execution record that documents what was done, what files were
modified, and any deviations from the plan. Deviations are not hidden — they
are surfaced and documented.

The execution phase is where code is actually written. But the code is not
the primary output. The primary output is the execution record that makes the
code auditable.

### Phase 5: Verify

A specialized review agent audits the implementation against the plan and the
ADR. It checks for safety issues, intent compliance, and code quality. The
review produces a code review artifact that is persisted alongside the
execution records. Nothing is marked complete until the review passes.

The verify phase closes the loop: it confirms that what was built matches what
was planned, which was grounded in what was decided, which was based on what
was researched. The chain is complete.

## Why Specs Matter More for AI Agents Than for Humans

The case for SDD in human engineering teams is strong. For AI-assisted teams,
it is compelling.

Human engineers have persistent memory. They remember what was decided in
last quarter's architecture review. They carry implicit context about the
codebase's history and the team's preferences. They can be asked "why did you
do it this way?" and give a meaningful answer.

AI coding agents have none of this. Each session begins without memory of
previous sessions. The agent has no knowledge of your team's architectural
preferences unless they are explicitly provided. It has no memory of the
decision made two sprints ago. It will re-derive decisions, potentially
reaching different conclusions, producing drift.

Specifications solve this problem. A research artifact is the agent's memory
of what was investigated. An ADR is the agent's memory of what was decided
and why. An implementation plan is the agent's memory of what was approved.
Execution records are the agent's memory of what was done.

Without these artifacts, every AI coding session is stateless. With them,
sessions accumulate into a coherent, traceable body of work.

There is a second dimension. Human engineers are accountable for their code
through social mechanisms — code review, team norms, reputational stakes.
AI agents are not. They produce output without accountability. SDD supplies
the missing accountability layer: structured artifacts that make it possible
to audit whether the agent operated within sanctioned boundaries and produced
output that can be justified.

## Industry Momentum

The SDD concept is gaining traction across the industry, and not only in
academic or niche contexts.

**AWS Kiro** (2025) introduced a specification-first approach to AI-assisted
development, where agents are directed by structured "specs" that define
requirements before code generation begins. The product's central premise —
that specs should precede and govern AI output — is the core principle of SDD.

**Thoughtworks Technology Radar** (2025) flagged "spec-first AI development"
as an emerging technique worth watching, noting that teams using structured
specifications with AI agents reported significantly better outcomes than
teams using conversational prompting alone.

**JetBrains** has been investing in structured AI context through its AI
Assistant platform, with specific attention to how architectural context can
be provided to AI agents in a structured, reusable form — a practical
implementation of the specification-as-artifact principle.

**Anthropic's Agent Skills** (released 2025) introduced reusable, structured
capability definitions for Claude Code. While not identical to SDD, Agent
Skills represent the same underlying insight: that structured, persistent
specifications of how AI agents should behave produce more reliable outcomes
than ad hoc instructions.

The regulatory environment is reinforcing this momentum. The EU AI Act's
requirements for technical documentation, human oversight, and audit trails
for high-risk AI applications are most naturally satisfied by SDD-style
workflows. Teams that adopt SDD now are building the compliance infrastructure
they will eventually need.

## vaultspec as an SDD Implementation

vaultspec is an open-source implementation of the SDD methodology for AI
coding agents. It enforces the five-phase pipeline through a system of
structured skills, specialized agents, and persistent artifact storage.

The framework provides:

- **Skills**: Activatable workflow recipes (`vaultspec-research`,
  `vaultspec-adr`, `vaultspec-write`, `vaultspec-execute`,
  `vaultspec-review`) that guide the agent through each pipeline phase.
- **Agents**: Specialized sub-agents dispatched for each phase, each with
  appropriate capability tiers and behavioral constraints.
- **Templates**: Structured document templates for each artifact type, stored
  in `.vaultspec/templates/`, ensuring consistent frontmatter, tagging, and
  linking across all vault documents.
- **The vault**: A `.vault/` directory that accumulates research, ADRs, plans,
  execution records, and reviews — the complete artifact trail that makes the
  codebase auditable.

vaultspec works with Claude Code, Gemini CLI, and Google Antigravity. It is
model-agnostic at the executor level: the same pipeline structure applies
regardless of which model is used for implementation.

The framework does not replace existing development tools. It wraps them in
a governance layer that makes AI-assisted development accountable. Your tests
still run. Your CI still enforces quality gates. But now there is a document
trail that explains why the code was written the way it was — and that trail
is machine-readable, version-controlled, and searchable.

## Getting Started

SDD does not require vaultspec. Any team can adopt the methodology with
nothing more than a consistent convention for creating and storing research
documents, ADRs, and implementation plans before code is written.

But the methodology is most powerful when it is enforced — when the pipeline
is not optional, when artifacts are required before the next phase can begin,
and when the vault accumulates into a searchable knowledge base that future
agents and engineers can draw on.

That is what vaultspec provides: enforcement, not just convention.

---

*vaultspec is an open-source spec-driven development framework. See the
[Getting Started guide](../getting-started.md) to run your first governed
workflow.*
