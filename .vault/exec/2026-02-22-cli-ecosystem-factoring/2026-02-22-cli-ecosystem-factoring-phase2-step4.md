---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#exec"
  - "#cli-ecosystem-factoring"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-ecosystem-factoring-plan]]"
---

# cli-ecosystem-factoring phase2 step4

## objective

Refactor `team_cli.py` to use `cli_common`.

## outcome

- Added `from vaultspec.cli_common import add_common_args, cli_error_handler, resolve_args_workspace, run_async, setup_logging` import.
- Removed `_get_version()` function.
- Replaced 5 async try/except scaffolds (command_create, command_assign, command_broadcast, command_message, command_spawn, command_dissolve) with `with cli_error_handler(args.debug): run_async(_fn(), debug=args.debug)` pattern.
- Each command's local `async def _fn()` closure is preserved; only the wrapping boilerplate changes.
- Replaced 5 common argparse argument definitions in `main()` with `add_common_args(parser)`.
- Replaced workspace re-resolution block with `resolve_args_workspace(args, _default_layout)`.
- Replaced logging setup block with `setup_logging(args)`.

Net: ~-45 lines across command functions and main().
