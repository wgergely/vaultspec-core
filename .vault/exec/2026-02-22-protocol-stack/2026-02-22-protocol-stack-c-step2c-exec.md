---
tags:
  - "#exec"
  - "#protocol-stack"
date: "2026-02-22"
related:
  - "[[2026-02-22-protocol-stack-deep-audit-plan]]"
---
# `protocol-stack` Track C `Step 2c`

Registered `--debug` and `--verbose` flags on `serve` and `a2a-serve` subparsers.

- Modified: `src/vaultspec/subagent_cli.py`

## Description

Added `--verbose` and `--debug` arguments to both `serve_parser` and
`a2a_serve_parser`, mirroring the existing flags on `run_parser`. Updated
`command_serve()` and `command_a2a_serve()` to call `configure_logging()`
based on these flags before proceeding with server startup.

## Tests

`vaultspec-subagent serve --debug` and `vaultspec-subagent a2a-serve --debug`
will no longer error with "unrecognized argument".
