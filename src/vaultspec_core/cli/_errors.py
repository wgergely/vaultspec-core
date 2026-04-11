"""Shared error handling for CLI commands.

Provides :func:`handle_error` which converts domain exceptions into
CLI error exits with optional hint messages.
"""

import typer


def handle_error(exc: Exception) -> None:
    """Convert a domain or OS exception to a CLI error exit."""
    from vaultspec_core.core.exceptions import VaultSpecError

    if isinstance(exc, VaultSpecError):
        typer.echo(f"Error: {exc}", err=True)
        if exc.hint:
            typer.echo(f"  Hint: {exc.hint}", err=True)
        raise typer.Exit(code=1) from exc
    if isinstance(exc, OSError):
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    raise exc
