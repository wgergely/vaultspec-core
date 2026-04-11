---
name: vaultspec-projectmanager
description: >-
  Use this skill for GitHub Projects management, issue triage, milestone
  tracking, worktree provisioning, release cycle coordination, and roadmap
  queries. Operates outside the vaultspec pipeline as a project
  coordination layer.
---

# Project manager skill (vaultspec-projectmanager)

**Announce at start:** "I'm using the `vaultspec-projectmanager` skill to
provide project management context."

Activate this skill for project-level coordination that sits outside the
research-adr-plan-execute pipeline. The project manager activates only when
invoked and responds to queries within that session.

## When to use

- Bootstrapping project context at session start.
- Triaging issues, updating milestones, or managing GitHub Projects.
- Provisioning worktrees for feature branches.
- Reviewing or defining the release roadmap.
- Coordinating cross-repo or cross-milestone work.
- Querying project state - "what's open?", "what's blocking the release?",
  "what should I work on next?"

This skill isn't part of the vaultspec pipeline (research -> adr -> plan ->
execute -> review). It operates alongside it as a project coordination
layer. It does not persist artifacts to `.vault/` and has no frontmatter or
tagging requirements.

## Required steps

1. **Context gathering:** load the `vaultspec-project-coordinator` agent
   persona. Gather current project state from GitHub (issues, milestones,
   GitHub Projects, labels) and local state (branches, worktrees, recent
   commits).

1. **State synthesis:** synthesize the gathered state into an actionable
   summary. Identify blockers, priorities, and gaps.

1. **Interactive response:** present findings and await user direction. The
   project coordinator asks clarifying questions rather than assuming
   intent. All actions require user confirmation.

## Agent persona

Load the `vaultspec-project-coordinator` agent persona for all project
management work. This agent has `read-write` mode for git worktree
operations and `gh` CLI interactions, but must not modify application code,
`.vaultspec/`, or `.vault/` contents. Detailed capabilities and operational
behaviours are defined in the agent persona.

## Workflow

The project coordinator operates in a query-response loop:

1. User asks a question or requests an action.
1. Agent gathers relevant state via `gh` and `git`.
1. Agent presents findings with proposed actions, showing the exact CLI
   invocations before execution.
1. User approves, modifies, or rejects.
1. Agent executes approved actions and confirms results.

This loop continues until the user dismisses the project coordinator or
switches to a pipeline skill.

**Example interaction:**

- User: "What's blocking the release?"
- Agent runs `gh issue list --milestone "0.3.0-alpha" --state open` and
  `gh api repos/{owner}/{repo}/milestones`
- Agent presents open issues grouped by blocker status with proposed next
  actions
- User approves or redirects

## Constraints

- **User-driven:** the project coordinator proposes, the user decides. Never
  auto-close issues, auto-merge PRs, or make unilateral board changes.
- **Non-destructive:** never force-push. Never delete branches without
  explicit user confirmation. Never modify `.vaultspec/` or `.vault/`
  contents.
- **Transparent:** always show the exact `gh` or `git` command before
  running it. No silent side effects.
- **Adaptive:** discover the project's management structure before acting.
  If the project uses GitHub Projects, work within that structure. If not,
  adapt to whatever tracking the project uses.
- **Ephemeral:** this skill produces no persisted vault artifacts. All
  context is gathered and presented within the session.
