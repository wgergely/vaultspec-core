---
tags: ['#plan', '#vault-doctor-suite']
date: '2026-02-24'
related:
  - '[[2026-02-24-vault-doctor-suite-adr]]'
  - '[[2026-02-24-vault-doctor-suite-plan]]'
  - '[[2026-02-24-vault-doctor-suite-p1-plan]]'
---

# `vault-doctor-suite` P2 plan: Structure and Links Checks

This phase implements the `STRUCTURE` and `LINKS` check categories. Both are
driven by existing infrastructure: `verify_vault_structure()` (in
`src/vaultspec/verification/api.py`) for structural checks and `VaultGraph`
(in `src/vaultspec/graph/api.py`) for link checks. The phase also introduces
`doctor/fixes/frontmatter.py` with the first fixable check: `malformed-related`.

Phase 2 depends on Phase 1 completing (models, registry, and safe_writer must
exist). It is independent of Phases 3–5 and can be executed in parallel with
them once the P1 foundation is in place.

## Proposed Changes

Three new check functions are introduced in `src/vaultspec/doctor/checks/`:

**structure.py**

- `check_unsupported_dirs` — delegates to `verify_vault_structure()`, wraps
  each `VerificationError` as a `Severity.ERROR` `DoctorResult`. No fix.

- `check_stray_files` — detects files in the `.vault/` root other than
  `README.md`. `Severity.WARNING`. No fix.

**links.py**

- `check_broken_wikilinks` — builds `VaultGraph`, calls `get_invalid_links()`,
  emits `Severity.ERROR` per `(source, target)` pair. No fix available.

- `check_orphaned_docs` — uses `VaultGraph.get_orphaned()`, emits
  `Severity.WARNING` per orphan node. No fix.

- `check_malformed_related` — per-file scan of `related` entries that are not
  valid `wikilink` format. `Severity.ERROR`, `fixable=True`.

**fixes/frontmatter.py** (partial — extended in P4)

- `fix_malformed_related(path, dry_run)` — rewrites the `related` field,
  removing non-wikilink entries. Uses `safe_writer.atomic_write`. Does not
  invent replacement links.

All checks accept `input_paths: list[Path] | None`. When provided, results are
filtered to only paths in `input_paths` (for `broken-wikilinks` and `orphaned-docs`,
the full graph is still built; results are filtered post-build).

## Tasks

- P2-S1: Implement `doctor/checks/structure.py` and register both checks
- P2-S2: Implement `doctor/checks/links.py` — broken-wikilinks and orphaned-docs checks
- P2-S3: Implement `check_malformed_related` in `doctor/checks/links.py`
- P2-S4: Implement `fix_malformed_related` in `doctor/fixes/frontmatter.py`
- P2-S5: Unit tests for structure and links checks

## Steps

- Name: Implement `doctor/checks/structure.py` — `unsupported-dirs` and `stray-files`
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p2-s1-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p1-plan]\], \[[2026-02-24-vault-doctor-suite-plan]\]

______________________________________________________________________

- Name: Implement `doctor/checks/links.py` — `broken-wikilinks` and `orphaned-docs` checks
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p2-s2-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p1-plan]\], \[[2026-02-24-vault-doctor-suite-plan]\]

______________________________________________________________________

- Name: Implement `check_malformed_related` in `doctor/checks/links.py`
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p2-s3-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p2-s2-exec]\]

______________________________________________________________________

- Name: Implement `fix_malformed_related` in `doctor/fixes/frontmatter.py`
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p2-s4-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p1-plan]\], \[[2026-02-24-vault-doctor-suite-p2-s3-exec]\]

______________________________________________________________________

- Name: Unit tests — structure checks, links checks, malformed-related fix, `--input` scoping, dry-run contract
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p2-s5-exec.md`
- Executing sub-agent: vaultspec-code-reviewer
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p2-s1-exec]\], \[[2026-02-24-vault-doctor-suite-p2-s2-exec]\], \[[2026-02-24-vault-doctor-suite-p2-s3-exec]\], \[[2026-02-24-vault-doctor-suite-p2-s4-exec]\]

## Parallelization

S1 and S2 are independent of each other and can run in parallel after P1 is
done. S3 depends on S2 (extends the same file). S4 depends on S3 (the fix
function references the check's output contract). S5 depends on all of S1–S4.

## Verification

- `vaultspec vault doctor --category structure` on a vault with an unknown
  subdirectory emits at least one `Severity.ERROR` result.

- `vaultspec vault doctor --category structure` on a conformant vault emits zero
  ERROR results (stray-file WARNINGs may appear depending on fixture state).

- `vaultspec vault doctor --category links` against a vault containing a doc
  that links to a non-existent target emits `Severity.ERROR` with `check = "broken-wikilinks"`.

- `vaultspec vault doctor --category links` against a vault with an isolated doc
  (no in-links) emits `Severity.WARNING` with `check = "orphaned-docs"`.

- `vaultspec vault doctor --category links` against a vault with a `related`
  entry of `"not-a-wikilink"` emits `Severity.ERROR` with `check = "malformed-related"` and `fix_available = True`.

- `--input` scoping: broken link in file A, `--input file_B` → zero results
  (filter works correctly).

- `fix_malformed_related(path, dry_run=True)` returns a result with
  `fix_applied = False` and a non-empty `fix_detail`; file content unchanged.

- `fix_malformed_related(path, dry_run=False)` returns `fix_applied = True`;
  `related` field contains only valid `wikilink` entries.

- No regressions in `src/vaultspec/graph/tests/` or
  `src/vaultspec/verification/tests/` test suites.
