---
tags: ["#plan", "#vault-doctor-suite"]
date: "2026-02-24"
related:
  - "[[2026-02-24-vault-doctor-suite-adr]]"
  - "[[2026-02-24-vault-doctor-suite-plan]]"
  - "[[2026-02-24-vault-doctor-suite-p1-plan]]"
---

# `vault-doctor-suite` P3 plan: Chain Integrity Checks

This phase introduces the `CHAIN` check category — the most architecturally
significant new check domain. Chain checks verify that the document authoring
chain (exec → plan → ADR → research) is complete and properly linked through
`related` frontmatter fields. They require both a `VaultGraph` (for link
resolution) and `DocType` awareness (for discriminating doc types by directory).

Phase 3 is independent of Phase 2 (links/structure) and Phase 4 (drift). It
can be executed in parallel with those phases once Phase 1 is complete.

## Proposed Changes

A new module `src/vaultspec/doctor/checks/chain.py` implements four checks:

| Check name | Severity | Fixable | Description |
|---|---|---|---|
| `exec-plan-link` | ERROR | No | Exec `related` must contain a valid plan wikilink |
| `plan-adr-link` | WARNING | No | Plan should have at least one linked ADR |
| `adr-research-link` | WARNING | No | ADR should have at least one linked research |
| `feature-plan-coverage` | ERROR | No | Every feature tag must have a plan (wraps `verify_vertical_integrity`) |

All four checks accept `input_paths: list[Path] | None`. For path-scoped runs,
each check walks only the relevant document set (exec docs, plan docs, etc.)
filtered to `input_paths`. The `feature-plan-coverage` check always scans the
full vault — `input_paths` filters which results are returned, not which
features are examined (to avoid false negatives from partial scans).

Link resolution follows the existing `VaultGraph` semantics: a link target is
considered valid when its stem (filename without extension) is a node in the
graph. The chain checks resolve `related` wikilink stems against graph nodes
and check each resolved node's `doc_type` against the expected type.

`verify_vertical_integrity()` from `src/vaultspec/verification/api.py` is
wrapped directly — its return value (`list[VerificationError]`) is mapped to
`list[DoctorResult]` with `Severity.ERROR` and `check = "feature-plan-coverage"`.

No fix functions are introduced in this phase. All four chain checks are
advisory: they surface gaps but cannot repair a missing document.

## Tasks

- P3-S1: Implement `check_exec_plan_link` in `doctor/checks/chain.py`
- P3-S2: Implement `check_plan_adr_link` in `doctor/checks/chain.py`
- P3-S3: Implement `check_adr_research_link` in `doctor/checks/chain.py`
- P3-S4: Implement `feature-plan-coverage` wrapper in `doctor/checks/chain.py`
- P3-S5: Register all chain checks in the registry and write unit tests

## Steps

- Name: Implement `check_exec_plan_link` — ERROR when exec `related` has no valid plan link
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p3-s1-exec.md`
- Executing sub-agent: vaultspec-complex-executor
- References: [[2026-02-24-vault-doctor-suite-adr]], [[2026-02-24-vault-doctor-suite-p1-plan]], [[2026-02-24-vault-doctor-suite-plan]]

---

- Name: Implement `check_plan_adr_link` — WARNING when plan `related` has no valid ADR link
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p3-s2-exec.md`
- Executing sub-agent: vaultspec-complex-executor
- References: [[2026-02-24-vault-doctor-suite-adr]], [[2026-02-24-vault-doctor-suite-p3-s1-exec]]

---

- Name: Implement `check_adr_research_link` — WARNING when ADR `related` has no valid research link
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p3-s3-exec.md`
- Executing sub-agent: vaultspec-complex-executor
- References: [[2026-02-24-vault-doctor-suite-adr]], [[2026-02-24-vault-doctor-suite-p3-s2-exec]]

---

- Name: Implement `feature-plan-coverage` — wrap `verify_vertical_integrity()` as CHAIN check
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p3-s4-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: [[2026-02-24-vault-doctor-suite-adr]], [[2026-02-24-vault-doctor-suite-p1-plan]], [[2026-02-24-vault-doctor-suite-p3-s3-exec]]

---

- Name: Register chain checks in `CheckRegistry`; write `test_chain.py` unit tests
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p3-s5-exec.md`
- Executing sub-agent: vaultspec-code-reviewer
- References: [[2026-02-24-vault-doctor-suite-adr]], [[2026-02-24-vault-doctor-suite-p3-s1-exec]], [[2026-02-24-vault-doctor-suite-p3-s2-exec]], [[2026-02-24-vault-doctor-suite-p3-s3-exec]], [[2026-02-24-vault-doctor-suite-p3-s4-exec]]

## Parallelization

S1 through S4 are logically sequential (each builds on the pattern established
by the prior step), but they touch the same file (`chain.py`) so must be done
in sequence. S5 is strictly dependent on S1–S4.

## Verification

- `vaultspec vault doctor --category chain` against a fixture vault containing
  an exec doc whose `related` field has no plan wikilink → at least one
  `Severity.ERROR` result with `check = "exec-plan-link"`.
- `vaultspec vault doctor --category chain` against a fixture vault containing
  a plan doc whose `related` field has no ADR wikilink → at least one
  `Severity.WARNING` result with `check = "plan-adr-link"`.
- `vaultspec vault doctor --category chain` against a fixture vault containing
  an ADR doc whose `related` field has no research wikilink → at least one
  `Severity.WARNING` result with `check = "adr-research-link"`.
- `vaultspec vault doctor --category chain` against a fixture vault with a fully
  linked chain (exec → plan → ADR → research) → zero chain results for those
  docs.
- `feature-plan-coverage` wraps `verify_vertical_integrity()` correctly: a
  feature tag with no plan document emits `Severity.ERROR` with
  `check = "feature-plan-coverage"`.
- `--input` scoping: chain break in file A, `--input file_B` → zero results
  for file B (filter works for exec-plan-link and plan-adr-link checks).
- `fix_available = False` on all four chain check results (no fixes are
  implemented in this phase).
- No regressions in `src/vaultspec/verification/tests/` (the wrapped function
  is not modified, only re-exported through the doctor layer).
