---
name: vaultspec-projectmanager
description: >-
  Manage GitHub Projects, triage issues, track milestones, provision
  worktrees, coordinate release cycles, and query roadmaps. Operates
  outside the vaultspec pipeline as a project coordination layer.
---

# Project manager skill (vaultspec-projectmanager)

**Announce at start:** "I'm using the `vaultspec-projectmanager` skill to
provide project management context."

Handles project-level coordination outside the vaultspec pipeline. This
skill manages project state (issues, boards, milestones, worktrees) but
never modifies application code, tests, or documentation.
User-triggered only - never activates automatically.

## Prerequisites

Requires an authenticated `gh` CLI and a git repo with a configured remote.

## When to use

- Bootstrapping project context at session start.
- Triaging issues, updating milestones, or managing GitHub Projects.
- Provisioning worktrees for feature branches.
- Reviewing or defining the release roadmap.
- Coordinating cross-repo or cross-milestone work.
- Querying project state - "what's open?", "what's blocking the release?",
  "what should I work on next?"

## Procedure

1. **Load agent persona:** load the `vaultspec-project-coordinator` persona
   defined in the agent persona section. Gather current project state from
   GitHub (issues, milestones, GitHub Projects, labels) and local state
   (branches, worktrees, recent commits).

1. **Synthesize and present:** distill gathered state into an actionable
   summary. Identify blockers, priorities, and gaps.

1. **Query-response cycle:** enter the interaction loop. Gather relevant
   state via `gh` and `git`. Present proposed actions with exact CLI
   invocations. On approval, execute and confirm results. All proposals
   are subject to the operating principles defined in the agent persona.

**Example interaction:**

- User: "What's blocking the release?"
- Agent runs `gh issue list --milestone "0.3.0-alpha" --state open` and
  `gh api repos/{owner}/{repo}/milestones`
- Agent presents open issues grouped by blocker status with proposed next
  actions
- User approves or redirects

## Agent persona

Load the `vaultspec-project-coordinator` agent persona for all project
management work. The persona operates only on project management surfaces:
issues, boards, milestones, labels, worktrees, and status reporting. It
must not modify application code, `.vaultspec/`, or `.vault/` contents.

The persona defines detailed capabilities, operating principles, and hard
boundaries. The skill is ephemeral - it produces no persisted vault
artifacts. All context is gathered and presented within the session.

## Exit criteria

The skill session ends when the user dismisses the project coordinator,
switches to a pipeline skill, or the session ends. No cleanup is needed.
