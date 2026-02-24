---
tags:
  - "#exec"
  - "#cli-ecosystem-factoring"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-ecosystem-factoring-plan]]"
---
# cli-ecosystem-factoring phase2 step5

## objective

Refactor `vault_cli.py` to use `cli_common`.

## outcome

- Added `from vaultspec.cli_common import get_version, setup_logging` import.
- Removed `_get_version(root_dir=None)` function.
- Updated `_make_parser()` to use `get_version()` from `cli_common` (was `_get_version()`).
- Replaced logging setup block in `main()` (`if args.debug / elif args.verbose / else: configure_logging()`) with `setup_logging(args)`.
- `_resolve_root()` helper retained: it follows a per-command pattern distinct from `resolve_args_workspace()` and serves `vault_cli`'s backwards-compatible `--root` behavior.

Net: -12 lines.
