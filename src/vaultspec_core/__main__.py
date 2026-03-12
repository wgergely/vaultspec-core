"""Package execution shim for ``python -m vaultspec_core``.

This module delegates directly to the root Typer application defined in
``vaultspec_core.cli`` so package execution and the installed CLI entrypoint
share the same command surface.
"""

from vaultspec_core.cli import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
