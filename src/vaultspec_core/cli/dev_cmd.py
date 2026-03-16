"""Dev command group -- developer-facing utilities (test runner, etc.)."""

from __future__ import annotations

import logging
from typing import Annotated

import typer

logger = logging.getLogger(__name__)

dev_app = typer.Typer(
    help="Developer utilities: test runner and diagnostics.",
    no_args_is_help=True,
)


@dev_app.command("test")
def cmd_test(
    target: Annotated[
        str, typer.Option("--category", "-c", help="Test category (unit, api, etc.)")
    ] = "all",
    module: Annotated[
        str | None, typer.Option("--module", "-m", help="Filter by module")
    ] = None,
    extra_args: Annotated[
        list[str] | None, typer.Argument(help="Extra pytest args")
    ] = None,
) -> None:
    """Run the packaged test surface with optional pytest passthrough."""
    from vaultspec_core.core.commands import test_run

    test_run(category=target, module=module, extra_args=extra_args)
