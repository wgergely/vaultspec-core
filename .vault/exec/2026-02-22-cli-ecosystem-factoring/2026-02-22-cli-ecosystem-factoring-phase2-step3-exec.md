---
tags:
  - '#exec'
  - '#cli-ecosystem-factoring'
date: '2026-02-22'
related:
  - '[[2026-02-22-cli-ecosystem-factoring-plan]]'
---

# cli-ecosystem-factoring phase2 step3

## objective

Refactor `subagent_cli.py` to use `cli_common`.

## outcome

- Added `from vaultspec.cli_common import add_common_args, resolve_args_workspace, run_async, setup_logging` import.
- Removed `_get_version()` function.
- Replaced manual event loop management in `command_run()` (~45 lines) with `run_async(coro, debug=args.debug)` (~20 lines). The coroutine result check now guards against `None` return: `if result is not None and result.response_text:`.
- Replaced 3 common argparse argument definitions in `main()` with `add_common_args(parser)`.
- Replaced workspace re-resolution + `args.root.resolve()` + `args.content_root.resolve()` block with `resolve_args_workspace(args, _default_layout)`.
- Replaced logging setup block with `setup_logging(args, default_format="%(message)s")` (preserving the bare-message format).
- Removed `warnings.filterwarnings("ignore", category=ResourceWarning, ...)` at module level (handled by `run_async`).

Net: ~-30 lines of boilerplate.
