---
tags: ['#plan', '#vault-doctor-suite']
date: '2026-02-24'
related:
  - '[[2026-02-24-vault-doctor-suite-adr]]'
  - '[[2026-02-24-vault-doctor-suite-plan]]'
  - '[[2026-02-24-vault-doctor-suite-research]]'
---

# `vault-doctor-suite` P1 plan: Foundation — Models, Registry, Safe Writer, CLI Scaffold, Remove `vault audit`

This phase lays the complete foundation for the doctor suite. It creates the
`src/vaultspec/doctor/` module with its data models, check registry, and
`safe_writer` helper. It then wires `vault doctor` into the CLI and removes
`vault audit` entirely — no shim, no deprecation period. All subsequent phases
depend on the artefacts produced here.

## Proposed Changes

The ADR mandates Option 2: a dedicated `vaultspec vault doctor` command backed
by a registered-check architecture. Before any check domain can be implemented,
the shared scaffolding must exist:

- `doctor/models.py` — `Severity`, `CheckCategory`, `DoctorResult`,
  `DoctorCheck` (the data layer every subsequent phase writes against)

- `doctor/registry.py` — `CheckRegistry`, the coordinator that collects checks,
  filters by category/name/severity, and drives `run()` + `fix()`

- `doctor/fixes/safe_writer.py` — `atomic_write` and `atomic_rename` with
  dry-run support; every fix in every future phase delegates here

- `vault_cli.py` changes — add `doctor` subcommand with the full flag surface
  defined in the ADR; remove `audit` subcommand and all direct wiring of
  `fix_violations`, `get_malformed`, and `verify_vertical_integrity` from the
  CLI layer

- `.pre-commit-config.yaml` — replace the `check-naming` hook that invokes
  `vault audit --verify` with the new `vault-doctor` hook entry

Key ADR constraints honoured here:

- `--dry-run` without `--fix` is rejected with a clear error; validation lives
  in the handler, not in argparse.

- Positional `FILES...` and `-i / --input <file>` are merged into one
  `input_paths` list before being passed to the registry.

- Exit code: 0 when no results at or above `--severity` threshold; 1 otherwise.

## Tasks

- P1-S1: Create `doctor/` module scaffold (directories, `__init__` stubs)
- P1-S2: Implement `doctor/models.py`
- P1-S3: Implement `doctor/registry.py` (`CheckRegistry`)
- P1-S4: Implement `doctor/fixes/safe_writer.py` (`atomic_write`, `atomic_rename`)
- P1-S5: Wire `vault doctor` into `vault_cli.py`; remove `vault audit`
- P1-S6: Update `.pre-commit-config.yaml` `check-naming` hook; update `AGENTS.md`
- P1-S7: Unit tests for registry dispatch, dry-run guard, and safe_writer

## Steps

- Name: Create `doctor/` module scaffold
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p1-s1-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-plan]\]

______________________________________________________________________

- Name: Implement `doctor/models.py` — `Severity`, `CheckCategory`, `DoctorResult`, `DoctorCheck`
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p1-s2-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p1-s1-exec]\]

______________________________________________________________________

- Name: Implement `doctor/registry.py` — `CheckRegistry` with `register`, `run`, `list_checks`
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p1-s3-exec.md`
- Executing sub-agent: vaultspec-complex-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p1-s2-exec]\]

______________________________________________________________________

- Name: Implement `doctor/fixes/safe_writer.py` — `atomic_write`, `atomic_rename` with dry-run
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p1-s4-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p1-s2-exec]\]

______________________________________________________________________

- Name: Wire `vault doctor` into `vault_cli.py`; remove `vault audit` subcommand entirely
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p1-s5-exec.md`
- Executing sub-agent: vaultspec-complex-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p1-s3-exec]\], \[[2026-02-24-vault-doctor-suite-p1-s4-exec]\]

______________________________________________________________________

- Name: Update `.pre-commit-config.yaml` (`check-naming` → `vault-doctor`) and `AGENTS.md`
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p1-s6-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p1-s5-exec]\]

______________________________________________________________________

- Name: Unit tests — registry dispatch, dry-run guard, `safe_writer` no-write contract
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p1-s7-exec.md`
- Executing sub-agent: vaultspec-code-reviewer
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p1-s3-exec]\], \[[2026-02-24-vault-doctor-suite-p1-s4-exec]\], \[[2026-02-24-vault-doctor-suite-p1-s5-exec]\]

## Parallelization

S1 must complete before S2, S3, S4. Once S2 is done, S3 and S4 can run in
parallel (they share only the models module as a read-only dependency). S5
requires S3 (registry) and S4 (safe_writer stubs sufficient for import). S6
and S7 can run concurrently after S5.

## Verification

- `src/vaultspec/doctor/__init__.py`, `models.py`, `registry.py`,
  `checks/__init__.py`, `fixes/__init__.py`, and `fixes/safe_writer.py` all
  exist and import cleanly.

- `vaultspec vault doctor --severity info` exits 0 on an empty vault (no checks
  registered yet returns an empty result list).

- `vaultspec vault doctor --dry-run` (without `--fix`) exits non-zero and emits
  a clear error message.

- `vaultspec vault audit` exits with an `unrecognised command` error (the
  subcommand no longer exists in argparse).

- `safe_writer.atomic_write(path, content, dry_run=True)` returns `False` and
  leaves the file unchanged (verified by stat comparison before/after).

- `safe_writer.atomic_write(path, content, dry_run=False)` returns `True` and
  writes via a temp file + rename (no partial writes on interrupt).

- The `check-naming` hook in `.pre-commit-config.yaml` no longer invokes
  `vault audit --verify`; it has been replaced with the `vault-doctor` entry.

- All existing tests in `src/vaultspec/verification/` and `src/vaultspec/graph/`
  continue to pass (no regressions — those modules are not modified).
