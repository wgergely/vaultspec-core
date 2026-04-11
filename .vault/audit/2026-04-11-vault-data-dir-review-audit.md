---
tags:
  - '#audit'
  - '#vault-data-dir'
date: '2026-04-11'
related:
  - '[[2026-04-11-vault-data-dir-review-audit]]'
---

# `vault-data-dir` Code Review

<!-- Persistent log of audit findings appended below. -->

DOCSTRING-001 | LOW | `is_supported_directory` docstring is now inaccurate
The docstring says "True if the directory is in `SUPPORTED_DIRECTORIES`" but
the method now also checks `AUXILIARY_DIRECTORIES`. Should read something like
"True if the directory is recognized (document or auxiliary)".
File: `src/vaultspec_core/vaultcore/models.py` line 174.

GITIGNORE-001 | MEDIUM | `.gitignore` change broadens scope beyond #56
The original issue is about `vault check structure` flagging `data/`. The
`.gitignore` change from `.vault/` (ignore everything) to four specific
subdirectories means `.vault/` document dirs (`adr/`, `plan/`, etc.) are now
trackable by git. This is a behavioral change to version control, not just
the structure checker. Verify this is intentional for the source repo.

PRECOMMIT-001 | LOW | Unrelated `.pre-commit-config.yaml` change bundled
`doctor` -> `spec doctor` namespace fix from PR #55 is bundled into this PR.
Not a bug, but muddles the PR scope. Acceptable for a small fix branch.

TESTS-001 | PASS | Test coverage is adequate
Five tests cover: `data/` allowed, `logs/` allowed, unknown rejected, hidden
dirs allowed, all dirs combined. Uses real filesystem via `tmp_path`. No mocks.

SCOPE-001 | PASS | Implementation is minimal and correct
`AUXILIARY_DIRECTORIES` is a clean separation from `SUPPORTED_DIRECTORIES` -
auxiliary dirs won't get document tags or type mappings. `get_tag_for_directory`
correctly returns `None` for auxiliary dirs since it only checks `DocType`.
