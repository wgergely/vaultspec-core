"""Shared error handling for CLI commands.

Provides :func:`handle_error` which converts domain exceptions into
CLI error exits with optional hint messages.
"""

import typer

from vaultspec_core.cli.json_output import json_format_kwargs


def handle_error(exc: Exception, *, json_output: bool = False) -> None:
    """Convert a domain or OS exception to a CLI error exit.

    Args:
        exc: The caught exception. :class:`VaultSpecError` and
            :class:`OSError` exit with code 1; anything else re-raises.
        json_output: When ``True``, emit the canonical
            ``{"schema": "vaultspec.error.v1", "status": "failed",
            "data": {...}}`` envelope to stdout instead of a plain-text
            ``Error:`` line on stderr, so a ``--json`` consumer can parse
            failures, not just exit codes.
    """
    from vaultspec_core.core.exceptions import VaultSpecError

    if isinstance(exc, (VaultSpecError, OSError)):
        hint = getattr(exc, "hint", None)
        if json_output:
            import json

            from vaultspec_core.cli.rendering import json_envelope

            data: dict[str, str] = {"message": str(exc)}
            if hint:
                data["hint"] = hint
            print(
                json.dumps(
                    json_envelope("error", "failed", data), **json_format_kwargs()
                )
            )
        else:
            typer.echo(f"Error: {exc}", err=True)
            if hint:
                typer.echo(f"  Hint: {hint}", err=True)
        raise typer.Exit(code=1) from exc
    raise exc


def run_app(app: typer.Typer) -> None:
    """Invoke *app*, reporting a domain error that escaped a command body.

    Every command that can raise :class:`VaultSpecError` from its own body
    already routes it through :func:`handle_error`. This is the backstop for
    the ones that cannot: a refusal raised beneath a command, by a shared
    pre-scan step rather than by anything the command called deliberately.
    The corrupt-manifest refusal is the motivating case - it fires inside the
    lazy migration trigger under ``scan_vault``, so it reaches the user
    through whichever vault command happened to scan (issue #455).

    Without this, Typer's rich handler renders such a refusal as a source
    traceback and drops the ``hint`` entirely, which on that path is the one
    line the user actually needs: the manifest is corrupt, delete it and
    re-run install. The exit code is 1, matching :func:`handle_error`.

    Args:
        app: The root Typer application to invoke.

    Raises:
        SystemExit: With code 1 when a :class:`VaultSpecError` escapes.
    """
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        app()
    except VaultSpecError as exc:
        typer.echo(f"Error: {exc}", err=True)
        if getattr(exc, "hint", ""):
            typer.echo(f"  Hint: {exc.hint}", err=True)
        raise SystemExit(1) from exc
