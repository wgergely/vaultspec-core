---
tags:
  - '#research'
  - '#vault-doctor-suite'
date: '2026-02-24'
related: []
---

# `vault-doctor-suite` research: Audit of Existing Verification Capabilities and Gap Analysis

## Findings

### 1. Current Verification Architecture

The verification system lives across three modules:

- **`src/vaultspec/verification/api.py`** — primary validation and repair entry point
- **`src/vaultspec/graph/api.py`** — graph-based link analysis
- **`src/vaultspec/vaultcore/models.py`** — schema definitions and per-field validation
- **`src/vaultspec/vaultcore/links.py`** — `[[wikilink]]` extraction
- **`src/vaultspec/vaultcore/scanner.py`** — vault directory walking

The surface exposed via CLI is `vaultspec vault audit` with flags `--verify`, `--fix`, `--graph`,
`--summary`, `--features`. The pre-commit hook `check-naming` calls `vault audit --verify` on
staged markdown files.

### 2. Existing Check Inventory

#### Structural Checks (`verify_vault_structure`)

- Unsupported top-level directories inside `.vault/`
- Stray files in `.vault/` root (other than `README.md`)

#### Per-File Checks (`verify_file`)

- Filename matches `YYYY-MM-DD-<feature>-<type>.md` pattern
- Exactly 2 tags present (Rule of Two)
- Exactly one directory tag (`#adr`, `#audit`, `#exec`, `#plan`, `#reference`, `#research`)
- Directory tag matches the file's actual directory
- Exactly one feature tag matching `^#[a-z0-9-]+$`
- Date field present and ISO 8601 (`YYYY-MM-DD`)
- All `related` entries are valid `[[wikilink]]` format

#### Integrity Checks (`verify_vertical_integrity`)

- Every feature tag that appears anywhere in the vault has a corresponding `#plan` document

#### Graph-Based Checks (`VaultGraph`)

- `get_invalid_links()` — wikilinks pointing to non-existent documents (already implemented but
  **not wired into `--verify`**)

- `get_orphaned()` — documents with zero incoming links (already implemented but **not wired
  into `--verify`**)

#### Auto-Repair (`fix_violations`)

Six repair actions exist, all applied in-place with no dry-run option:

| Action             | Trigger                    | Repair                          |
| ------------------ | -------------------------- | ------------------------------- |
| `add_tags`         | `tags` field absent        | Insert empty list               |
| `add_doc_type_tag` | No directory tag           | Infer from directory and insert |
| `add_feature_tag`  | Only one tag               | Append `#uncategorized`         |
| `add_date`         | `date` field absent        | Set to today's date             |
| `rename_suffix`    | Suffix wrong for directory | Rename file                     |
| `add_date_prefix`  | No date prefix             | Prepend today's date            |

A dry-run pattern is established in `sync_files()` / `sync_skills()` (accepting `dry_run: bool`)
but has **not been extended to `fix_violations()`**.

### 3. Gap Analysis

#### Gap A — No Dry-Run for Fix

`fix_violations()` writes and renames files immediately. There is no way to preview what would
change before applying. This is the single highest-risk gap given that fix operations include file
renames.

#### Gap B — Broken Wikilinks Not in Verify Pipeline

`VaultGraph.get_invalid_links()` detects `[[target]]` entries where `target` has no corresponding
vault document. This check exists but is only surfaced via `--graph`, not `--verify`. Broken links
therefore do not block pre-commit hooks.

#### Gap C — Orphans Not in Verify Pipeline

`VaultGraph.get_orphaned()` detects documents with zero incoming references. Same situation as
Gap B — exists in `--graph` but not `--verify`. An orphaned exec log or orphaned research document
is a silent problem.

#### Gap D — Chain Integrity: Only Vertical (Feature → Plan)

The current chain check only validates one direction: every feature must have a plan. It does not
check the _documentary chain_ within a feature:

- **Plan → ADR**: A plan with no linked ADR is a chain break. The architectural rationale is
  undocumented.

- **ADR → Research**: An ADR with no linked research is a chain break. The decision lacks
  evidence.

- **Exec → Plan**: An exec log with no linked plan in its `related` field is a chain break.
  (Templates mandate this link but it is not currently verified.)

- **Unlinked research/reference**: Research or reference documents not referenced by any plan or
  ADR are effectively orphaned knowledge.

These are _soft_ chain breaks (advisory violations) because the user explicitly controls linking.
However they represent documentary drift that accumulates silently.

#### Gap E — Frontmatter Format Drift Not Fully Covered

Several frontmatter formatting issues pass current validation undetected:

| Drift Class                       | Description                                                      | Current Status             |
| --------------------------------- | ---------------------------------------------------------------- | -------------------------- |
| Filename date ≠ frontmatter date  | `2026-02-10-foo-plan.md` has `date: "2026-02-11"`                | Not checked                |
| Filename feature ≠ tag feature    | `2026-02-10-bar-plan.md` has `#baz` feature tag                  | Not checked                |
| Unquoted date                     | YAML parses `date: 2026-02-18` as a date object, not a string    | Not checked                |
| CRLF line endings                 | Windows-style line endings corrupt frontmatter parsing           | Not checked                |
| Extra/unknown fields              | `summary:`, `status:`, `author:` in frontmatter — outside schema | Not checked                |
| Duplicate tags                    | `tags: ["#plan", "#plan", "#foo"]`                               | Not checked                |
| Tags as scalar                    | `tags: "#plan"` instead of a list                                | Parser may silently handle |
| Trailing whitespace in tag values | `"#plan "` (space before closing quote)                          | Not checked                |
| BOM characters                    | Partially handled in `fix_violations` but not in `--verify`      | Partial                    |
| Missing `related` field           | Field absent entirely vs present as empty list                   | Not normalized             |

#### Gap F — Feature Coverage Audit

There is no report showing, per feature, which document types exist and which are missing.
`list_features()` returns a set of names. `verify_vertical_integrity()` checks plan coverage.
But there is no matrix view like:

```
feature: editor-demo
  [✓] plan      2026-02-05-editor-demo-plan.md
  [✓] research  2026-02-05-editor-demo-research.md
  [✓] adr       2026-02-05-editor-demo-adr.md
  [✗] exec      (none)
  [✗] audit     (none)
```

This is useful for tracking feature lifecycle completeness.

#### Gap G — No Topological Chain Traversal

The graph tracks `in_links` and `out_links` per document but does not provide:

- Chain path queries (given a plan, traverse to all reachable exec logs)
- Cycle detection (A links to B links to A)
- Reachability analysis (which exec logs are unreachable from their plan)

These are advanced capabilities but relevant to the doctor suite's dependency graphing goal.

### 4. Existing Doctor Command vs Vault Doctor

`vaultspec doctor` exists in `src/vaultspec/core/commands.py` and checks system-level
prerequisites (Python version, CUDA, optional Python dependencies). It is a _system health_ check,
not a _vault content health_ check. The proposed vault doctor suite is orthogonal: it checks the
document trail, not the runtime environment.

### 5. Design Constraints

#### Safety First

Any fix operation that touches the filesystem must have a dry-run counterpart. Renames are
especially dangerous — a misidentified suffix change could corrupt file history.

#### Commit-Hook Compatibility

Checks added to the verify pipeline must be fast (sub-second for typical vaults of 100–500 docs).
Graph construction is O(n) in document count. Chain integrity traversal is O(n + edges). Both
are acceptable.

#### Severity Model

Not all violations are equal. A missing `date` field is a correctable annoyance. A broken
wikilink may indicate deleted content. An exec log with no parent plan is a chain break. A
structured severity model (`error`, `warning`, `info`) allows consumers (CLI, pre-commit,
MCP tools) to filter by threshold.

#### Composability

Checks should be individually addressable. A user should be able to run only link checks, only
chain checks, or the full suite. This maps to a registered-check pattern.

### 6. Comparable Patterns in the Codebase

The `sync_files()` dry-run pattern is the best existing precedent: accept a `dry_run: bool`,
log planned actions with `[DRY-RUN]` prefix, return the same result type without writing. This
pattern should be replicated in `fix_violations()` and any new auto-repair functions.

The `VerificationError` dataclass is the right return type for all new checks. It carries `path`
and `message`. For chain checks, `path` will be the source document and `message` will name the
missing link target type.

A `severity` field should be added to `VerificationError` to classify violations without breaking
existing callers.

### 7. Summary of New Check Domains

| Domain                             | Gap | Check Type     | Fixable                      |
| ---------------------------------- | --- | -------------- | ---------------------------- |
| Dry-run fix safety                 | A   | Infrastructure | N/A                          |
| Broken wikilinks in verify         | B   | Error          | Advisory only                |
| Orphans in verify                  | C   | Warning        | No (requires human judgment) |
| Exec → Plan chain                  | D   | Error          | Advisory only                |
| Plan → ADR chain                   | D   | Warning        | Advisory only                |
| ADR → Research chain               | D   | Warning        | Advisory only                |
| Filename/frontmatter date drift    | E   | Error          | Yes (rename or update field) |
| Filename/frontmatter feature drift | E   | Error          | Yes (rename or update field) |
| Unquoted date                      | E   | Warning        | Yes (rewrite frontmatter)    |
| CRLF endings                       | E   | Warning        | Yes (normalize to LF)        |
| Extra fields                       | E   | Info           | Advisory only                |
| Duplicate tags                     | E   | Error          | Yes (deduplicate)            |
| BOM in verify                      | E   | Warning        | Yes (strip BOM)              |
| Feature coverage matrix            | F   | Info           | No                           |
| Chain traversal / cycles           | G   | Warning        | Advisory only                |
