---
tags:
  - '#exec'
  - '#graph-hardening'
date: '2026-03-22'
related:
  - '[[2026-03-22-graph-hardening-plan]]'
---

# graph-hardening phase 4 - check_dangling checker

## Summary

Created the `check_dangling` checker that surfaces dangling wiki-links as
ERROR-severity diagnostics and wired it into the check suite and CLI.

## Changes

- **Created** `src/vaultspec_core/vaultcore/checks/dangling.py`

  - `check_dangling()` iterates `graph.get_invalid_links()` and emits an
    ERROR diagnostic per `(source, target)` pair.
  - Feature filter: skips sources that lack the requested feature tag.
  - `--fix` support: `_remove_related_entries()` parses the YAML frontmatter
    and removes `target` lines from the `related:` list block only.
    Body wiki-links are left untouched.
  - `supports_fix=True`, check name `"dangling"`.

- **Modified** `src/vaultspec_core/vaultcore/checks/__init__.py`

  - Imported `check_dangling` from `.dangling`.
  - Added to `__all__`.
  - Inserted into `run_all_checks()` after `check_links`, before
    `check_orphans`. Updated docstring to reflect eight checkers.

- **Modified** `src/vaultspec_core/cli/vault_cmd.py`

  - Added `vault check dangling` subcommand with `--fix`, `--feature`,
    `--verbose`, `--target` options following the `cmd_check_references`
    pattern.

## Verification

- `uv run ruff check` - all checks passed on modified files.
- `uv run ruff format` - 1 file reformatted (dangling.py).
- `uv run python -m ty check src/vaultspec_core` - all checks passed.
- `uv run pytest src/vaultspec_core/graph/tests/test_graph.py -x -q` -
  53 passed.
- `uv run vaultspec-core vault check dangling` - reports 156 errors with
  source paths and unresolved target names.
- `uv run vaultspec-core vault check all` - dangling section appears after
  links, before orphans. Exit code 1 with total error count.
