---
tags:
  - "#exec"
  - "#cli-output"
date: "2026-02-23"
related:
  - "[[2026-02-23-cli-output-plan]]"
---
# cli-output phase-1 steps

Execution record for phase-1 (sub-phase a — infrastructure). All four tasks
completed sequentially in a single session. Zero behavioral change to existing
call sites; this phase is purely additive.

## step 1 — create `src/vaultspec/printer.py`

**File created:** `src/vaultspec/printer.py`

Introduced the `Printer` class with:

- `__init__(self, quiet=False, stdout_console=None, stderr_console=None)` —
  defaults construct `Console(stderr=False, highlight=False)` (stdout) and
  `Console(stderr=True, highlight=False)` (stderr). Injection points support
  `StringIO`-backed testing without mocks.
- `out(*args, **kwargs)` — routes to stdout Console; never suppressed.
- `out_json(data, *, indent=2)` — serializes via `json.dumps`, calls `out()`;
  never suppressed.
- `status(msg, *args, **kwargs)` — routes to stderr Console; gated by
  `self.quiet`.
- `warn(msg, *args, **kwargs)` — routes to stderr Console with `style="yellow
  bold"` default; never suppressed.
- `error(msg, *args, **kwargs)` — routes to stderr Console with `style="red
  bold"` default; never suppressed.

`__all__ = ["Printer"]` declared at module level.

## step 2 — wire `args.printer` into `setup_logging()`

**File modified:** `src/vaultspec/cli_common.py`

Added at the end of `setup_logging()`, after the `configure_logging()` call:

```python
from .printer import Printer
args.printer = Printer(quiet=getattr(args, "quiet", False))
```

This is the only change to `cli_common.py`. All existing call sites remain
unmodified; `args.printer` is now available to every command handler that goes
through `setup_logging()`.

## step 3 — export `Printer` from `src/vaultspec/__init__.py`

**File modified:** `src/vaultspec/__init__.py`

Added after the module docstring:

```python
from .printer import Printer

__all__ = ["Printer"]
```

`Printer` is now reachable as `vaultspec.Printer` without importing the
submodule directly. The existing docstring was preserved verbatim.

## step 4 — write unit tests

**File created:** `src/vaultspec/tests/cli/test_printer.py`

13 tests across 5 test classes, exercising all five public methods using
`StringIO`-backed `Console` injection — no mocks, no patching:

- `TestOut` — `out()` writes to stdout buffer; not suppressed when `quiet=True`.
- `TestOutJson` — `out_json()` emits valid JSON; not suppressed when
  `quiet=True`; handles list payloads.
- `TestStatus` — `status()` writes to stderr when `quiet=False`; silent when
  `quiet=True`.
- `TestWarn` — `warn()` writes to stderr; not suppressed when `quiet=True`.
- `TestError` — `error()` writes to stderr; not suppressed when `quiet=True`.
- `TestConstructorDefaults` — default and quiet construction succeed without
  injection.

## verification results

### compile-time

```
python -m py_compile src/vaultspec/printer.py src/vaultspec/cli_common.py src/vaultspec/__init__.py
```

Exit code: 0. No output.

### unit tests

```
python -m pytest src/vaultspec/tests/cli/test_printer.py -v
```

Result: **13 passed in 0.16s**. All assertions green.

### regression check

```
python -m vaultspec sync-all --prune
```

Exit code: 0. No output. No regressions detected.

## files produced or modified

| File | Action |
| :--- | :--- |
| `src/vaultspec/printer.py` | created |
| `src/vaultspec/cli_common.py` | modified (3 lines added to `setup_logging()`) |
| `src/vaultspec/__init__.py` | modified (2 lines added after docstring) |
| `src/vaultspec/tests/cli/test_printer.py` | created |
