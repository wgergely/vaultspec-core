---
tags:
  - '#adr'
  - '#audit-findings'
date: '2026-03-30'
related:
  - '[[2026-03-30-audit-findings-plan]]'
  - '[[2026-03-27-cli-ambiguous-states-audit]]'
  - '[[2026-03-27-cli-ambiguous-states-resolver-adr]]'
  - '[[2026-03-27-cli-ambiguous-states-gitignore-adr]]'
  - '[[2026-03-23-audit-fixes-research]]'
  - '[[2026-03-27-cli-ambiguous-states-prior-art-research]]'
---

# `audit-findings` adr: triage charter for the 91-finding rolling audit

Status: Accepted
Supersedes: n/a
Superseded by: n/a

## context

The cli-ambiguous-states rolling audit produced 91 open findings across 6 rounds of review. Individual decisions about how to resolve each finding live in the finding-level work (commit messages, PR diffs, and the inherited decisions recorded in `[[2026-03-27-cli-ambiguous-states-resolver-adr]]` and `[[2026-03-27-cli-ambiguous-states-gitignore-adr]]`). This ADR captures the *meta* decision that made those 91 items shippable: how we triaged, grouped, and sequenced them.

Without this record the audit-findings feature carries a plan (`[[2026-03-30-audit-findings-plan]]`) with no backing ADR, violating the vaultspec pipeline contract that every plan trace to an architectural decision.

## decision

Triage the 91 findings by **root cause** and **risk class**, not by finding ID or round. Concretely:

1. **De-duplicate by root cause.** Audit IDs across rounds frequently describe the same underlying defect. Merge every such cluster into a single work item so that each fix is applied exactly once.
1. **Partition by risk class into five ordered phases.**
   1. Data-loss first - anything that can silently corrupt or lose user content.
   1. Visibility next - signals that a user-facing operation behaves differently from what the CLI reports.
   1. Correctness third - defects that produce a wrong result without user-visible signal.
   1. Hardening fourth - defences in depth (input validation, error paths, timeouts).
   1. Coverage last - test gaps that do not correspond to a known defect.
1. **Inherit the resolver and gitignore decisions** recorded in `[[2026-03-27-cli-ambiguous-states-resolver-adr]]` and `[[2026-03-27-cli-ambiguous-states-gitignore-adr]]`. These set the architectural invariants for the entire cli-ambiguous-states surface; audit-findings consumes them rather than re-ratifying them.
1. **No partial plans.** Every finding either lands in a phase or is explicitly closed with rationale. No "open" state after triage.

The companion plan (`[[2026-03-30-audit-findings-plan]]`) operationalises this triage across the five phases.

## consequences

### positive

- The audit-findings feature is now fully traceable: research (`[[2026-03-23-audit-fixes-research]]`) -> ADR (this document) -> plan -> execution.
- Risk-ordered phasing means data-loss class fixes ship ahead of hardening, so a partial merge of the 91 items still reduces the top-line risk surface.
- Inheriting prior ADRs avoids duplicating architectural ratifications that the cli-ambiguous-states feature already made.

### negative

- Operators reading only this ADR will not find the detailed mitigation designs for individual findings; they must cross-read the inherited ADRs.
- "Root-cause de-duplication" is a judgement call; the triage author's clustering is not mechanically re-checkable.

### neutral

- Future audit-findings plans (follow-up rounds) may choose to re-tag under a different feature rather than extend this one.

## plan reference

See `[[2026-03-30-audit-findings-plan]]` for the phased execution.
