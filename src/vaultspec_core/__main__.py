"""Package execution shim for ``python -m vaultspec_core``.

This module delegates directly to the root Typer application defined in
``vaultspec_core.cli`` so package execution and the installed CLI entrypoint
share the same command surface.
"""

from vaultspec_core.cli import app
from vaultspec_core.cli._errors import run_app
from vaultspec_core.console import configure_stdio


def main() -> None:
    # Make typer.echo safe on legacy Windows codepages (cp1252) before any
    # command runs; see vaultspec_core.console.configure_stdio (issue #111).
    configure_stdio()
    run_app(app)


if __name__ == "__main__":
    main()
