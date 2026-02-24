---
tags:
  - "#exec"
  - "#cli-ecosystem-factoring"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-ecosystem-factoring-plan]]"
  - "[[2026-02-22-cli-ecosystem-factoring-research]]"
---
# cli-ecosystem-factoring phase2 step1

## objective

Create `src/vaultspec/cli_common.py` with 6 shared CLI infrastructure functions.

## outcome

Created `src/vaultspec/cli_common.py` (~180 lines) with:

- `get_version(root_dir=None) -> str`: Line-scanning pyproject.toml reader using `vault_cli.py` signature (most flexible). Returns `"unknown"` on failure.
- `add_common_args(parser) -> None`: Adds `--root`, `--content-dir`, `--verbose`/`-v`, `--debug`, `--version`/`-V` to any `ArgumentParser`.
- `setup_logging(args, default_format=None) -> None`: Encapsulates `configure_logging()` + conditional `reset_logging()` dance. Reads `args.debug` and `args.verbose`. Accepts optional `default_format` for `subagent_cli.py`'s `"%(message)s"` case.
- `resolve_args_workspace(args, default_layout) -> WorkspaceLayout`: Post-parse workspace re-resolution. Sets `args.root` and `args.content_root` as side effects.
- `run_async(coro, *, debug=False) -> T`: Windows `ProactorEventLoopPolicy`, `ResourceWarning` suppression, `asyncio.sleep(0.250)` pipe cleanup on Windows. On exception: log error, traceback if debug, `sys.exit(1)`.
- `cli_error_handler(debug) -> ContextManager`: `contextlib.contextmanager` try/yield/except that logs error, traceback if debug, `sys.exit(1)`.

Module is importable without side effects (verified: `python -c "from vaultspec.cli_common import get_version; print('OK')"` succeeds with no I/O).

Note: Phase 1 running in parallel updated `cli_common.py`'s `TYPE_CHECKING` block to use `vaultspec.config` instead of `vaultspec.core`.
