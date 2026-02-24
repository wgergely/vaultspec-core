---
tags:
  - "#exec"
  - "#cli-ecosystem-factoring"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-ecosystem-factoring-plan]]"
---
# cli-ecosystem-factoring phase2 step2

## objective

Refactor `cli.py` to use `cli_common`.

## outcome

- Added `from vaultspec.cli_common import add_common_args, get_version, resolve_args_workspace, setup_logging` import.
- Replaced `_get_version()` function body with comment `# get_version imported from cli_common`.
- Replaced 5 common argparse argument definitions in `main()` with `add_common_args(parser)`.
- Replaced logging setup block (reset_logging + configure_logging conditionals) with `setup_logging(args)`.
- Replaced post-parse workspace re-resolution block with `resolve_args_workspace(args, _default_layout)` + `init_paths(layout)`.

Net: -15 lines in `main()` boilerplate.
