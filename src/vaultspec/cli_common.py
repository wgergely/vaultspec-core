"""Shared CLI infrastructure (argument parsing, logging, async runner) for all vaultspec
entry points.

Utilities:
    get_default_layout:    Resolve and cache the default WorkspaceLayout.
    get_version:           Read the package version from pyproject.toml.
    add_common_args:       Register standard flags on an ArgumentParser.
    setup_logging:         Configure logging from parsed args.
    resolve_args_workspace: Re-resolve the workspace when --root/--content-dir is set.
    run_async:             Run an async coroutine on a fresh event loop.
    cli_error_handler:     Context manager for clean unhandled-exception exit.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Coroutine, Generator

    from .config import WorkspaceLayout

logger = logging.getLogger(__name__)

T = TypeVar("T")

_default_layout: WorkspaceLayout | None = None


def get_default_layout() -> WorkspaceLayout:
    """Return the cached default WorkspaceLayout, resolving it on first call.

    Resolves the workspace rooted at ``.vaultspec/`` relative to the current
    working directory and caches the result for subsequent calls.

    Returns:
        The resolved ``WorkspaceLayout`` for the current project.

    Raises:
        WorkspaceError: If no valid workspace can be resolved.
    """
    global _default_layout
    if _default_layout is None:
        from .config import resolve_workspace

        _default_layout = resolve_workspace(framework_dir_name=".vaultspec")
    return _default_layout


def get_version(root_dir: Path | None = None) -> str:
    """Read the package version, preferring importlib.metadata for pip-installed usage.

    Tries ``importlib.metadata.version("vaultspec")`` first (correct when
    pip-installed), then falls back to pyproject.toml line-scanning for
    development mode (running from source without install).

    Args:
        root_dir: Directory containing ``pyproject.toml`` for the fallback path.
            Falls back to ``Path.cwd()`` if ``None``.

    Returns:
        The version string, or ``"unknown"`` if it cannot be determined.
    """
    try:
        from importlib.metadata import version

        return version("vaultspec")
    except Exception:
        pass
    search_root = root_dir if root_dir is not None else Path.cwd()
    toml_path = search_root / "pyproject.toml"
    if toml_path.exists():
        for line in toml_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "unknown"


def add_verbosity_args(parser: argparse.ArgumentParser) -> None:
    """Add verbosity flags to a subcommand parser.

    Adds ``--verbose``/``-v``, ``--debug``, and ``--quiet``/``-q`` as a
    mutually-exclusive group.  Call this on each subparser so that flags
    placed *after* the subcommand name are recognised.

    Uses ``default=argparse.SUPPRESS`` so that unspecified flags do not
    override values already set by the top-level parser.

    Args:
        parser: The argument parser to add verbosity arguments to.
    """
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Enable verbose output (INFO level)",
    )
    verbosity.add_argument(
        "--debug",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Enable debug logging (DEBUG level)",
    )
    verbosity.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Suppress informational output (WARNING level only)",
    )


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add the standard top-level arguments to a parser.

    Adds ``--root``, ``--content-dir``, verbosity flags
    (``--verbose``/``--debug``/``--quiet``), and ``--version``/``-V``.

    Args:
        parser: The argument parser to add common arguments to.
    """
    parser.add_argument(
        "--root", type=Path, default=None, help="Override workspace root directory"
    )
    parser.add_argument(
        "--content-dir",
        type=Path,
        default=None,
        help="Content source directory (rules, agents, skills)",
    )

    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output (INFO level)",
    )
    verbosity.add_argument(
        "--debug", action="store_true", help="Enable debug logging (DEBUG level)"
    )
    verbosity.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress informational output (WARNING level only)",
    )

    parser.add_argument(
        "--version", "-V", action="version", version=f"%(prog)s {get_version()}"
    )


def setup_logging(args: Any, default_format: str | None = None) -> None:
    """Configure logging after argument parsing.

    Must be called after ``parser.parse_args()`` so that ``args.debug``,
    ``args.verbose``, and ``args.quiet`` are available.

    Args:
        args: Parsed argument namespace. Must expose ``debug``, ``verbose``,
            and ``quiet`` boolean attributes (all default to ``False`` if missing).
        default_format: Optional log format string. When ``None``, the default
            Rich handler is used in TTY mode, plain format otherwise.
    """
    from .logging_config import configure_logging, reset_logging

    debug = getattr(args, "debug", False)
    verbose = getattr(args, "verbose", False)
    quiet = getattr(args, "quiet", False)

    if debug:
        reset_logging()
        configure_logging(debug=True)
    elif quiet:
        reset_logging()
        configure_logging(quiet=True)
    elif verbose:
        reset_logging()
        configure_logging(level="INFO")
    else:
        configure_logging(log_format=default_format)

    from .printer import Printer

    args.printer = Printer(quiet=getattr(args, "quiet", False))


def resolve_args_workspace(
    args: Any, default_layout: WorkspaceLayout
) -> WorkspaceLayout:
    """Re-resolve the workspace when ``--root`` or ``--content-dir`` overrides are set.

    Sets ``args.root`` and ``args.content_root`` on the namespace as side
    effects so that downstream command handlers can read them directly.

    Args:
        args: Parsed argument namespace. Reads ``args.root`` and
            ``getattr(args, "content_dir", None)``.
        default_layout: The workspace layout resolved at module import time.
            Used as the default when no overrides are present.

    Returns:
        Either the re-resolved layout (when overrides are present) or
        ``default_layout`` unchanged.
    """
    from .config import resolve_workspace

    content_dir = getattr(args, "content_dir", None)
    if args.root is not None or content_dir is not None:
        layout = resolve_workspace(
            root_override=args.root,
            content_override=content_dir,
            framework_dir_name=".vaultspec",
        )
    else:
        layout = default_layout

    args.root = layout.output_root.resolve()
    args.content_root = layout.content_root.resolve()

    from .core import init_paths

    init_paths(layout)

    return layout


def run_async[T](coro: Coroutine[Any, Any, T], *, debug: bool = False) -> T:
    """Run a coroutine on a new event loop with Windows-safe teardown.

    Applies ``WindowsProactorEventLoopPolicy`` on Windows and suppresses
    ``ResourceWarning`` during the run. A short grace period is added on
    Windows before loop close to flush pending pipe callbacks.

    On unhandled exceptions (other than ``KeyboardInterrupt`` / ``SystemExit``),
    logs the error and calls ``sys.exit(1)``.

    Args:
        coro: The coroutine to run.
        debug: If ``True``, print a full traceback on unhandled exceptions.

    Returns:
        The return value of the coroutine.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            return loop.run_until_complete(coro)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        logger.error("Error: %s", exc, exc_info=debug)
        sys.exit(1)
    finally:
        if sys.platform == "win32":
            with contextlib.suppress(Exception):
                loop.run_until_complete(asyncio.sleep(0.250))
        loop.close()


@contextlib.contextmanager
def cli_error_handler(debug: bool) -> Generator[None]:
    """Context manager that catches unhandled exceptions and exits cleanly.

    On any unhandled exception (except ``KeyboardInterrupt`` and
    ``SystemExit``): logs the error, optionally prints a traceback, and
    calls ``sys.exit(1)``.

    Args:
        debug: If ``True``, print a full traceback on unhandled exceptions.
    """
    try:
        yield
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        logger.error("Error: %s", exc, exc_info=debug)
        sys.exit(1)
