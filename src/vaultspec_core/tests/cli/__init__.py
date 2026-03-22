"""Tests for the vaultspec-core CLI entry points and path-resolution flows.

Covers sync, install, uninstall, vault, spec, and global-option commands
against the unified :mod:`vaultspec_core.cli` surface via Typer's
``CliRunner``. Shared fixtures live in :mod:`.conftest`.
"""
