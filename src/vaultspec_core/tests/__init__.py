"""Shared test surface for :mod:`vaultspec_core`.

Houses the CLI test suite under ``cli/``, exercising :mod:`vaultspec_core.cli`
commands (``sync``, ``install``, ``uninstall``, ``vault``, ``spec``) via
Typer's ``CliRunner``. Additional subpackage test suites (e.g.
:mod:`vaultspec_core.metrics.tests`) live alongside their respective packages.
"""
