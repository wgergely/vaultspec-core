"""Smoke tests for built distribution artifacts.

Run against an installed wheel or sdist to verify that the package is
importable, exposes expected metadata, and that both CLI entry points
(``vaultspec-core`` and ``vaultspec-mcp``) are functional.

Usage from CI::

    uv run --isolated --no-project --with dist/*.whl tests/smoke_test.py

This script is NOT a pytest test suite.  It runs as a plain Python script
and exits non-zero on the first failure so that it can gate the publish
workflow without requiring the full dev dependency set.
"""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def test_import() -> None:
    try:
        import vaultspec_core  # noqa: F401
    except ImportError as exc:
        _fail(f"import vaultspec_core raised {exc}")
    print("PASS: import vaultspec_core")


def test_version_metadata() -> None:
    version = importlib.metadata.version("vaultspec-core")
    if not version:
        _fail("importlib.metadata.version returned empty string")
    print(f"PASS: version = {version}")


def test_mcp_server_factory() -> None:
    try:
        from vaultspec_core.mcp_server.app import create_server

        server = create_server()
    except Exception as exc:
        _fail(
            f"create_server() raised {type(exc).__name__}: {exc}\n"
            "  This may be caused by import-time side effects in "
            "register_vault_tools when running in a bare environment."
        )
    cls_name = type(server).__name__
    if cls_name != "FastMCP":
        _fail(f"create_server() returned {cls_name}, expected FastMCP")
    print("PASS: create_server() returns FastMCP")


def test_cli_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "vaultspec_core", "--version"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        _fail(
            f"vaultspec-core --version exited {result.returncode}\n"
            f"  stderr: {result.stderr.strip()}"
        )
    print(f"PASS: --version -> {result.stdout.strip()}")


def test_cli_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "vaultspec_core", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        _fail(
            f"vaultspec-core --help exited {result.returncode}\n"
            f"  stderr: {result.stderr.strip()}"
        )
    for expected in ("install", "sync", "vault"):
        if expected not in result.stdout.lower():
            _fail(f"--help output missing expected command '{expected}'")
    print("PASS: --help contains expected commands")


if __name__ == "__main__":
    test_import()
    test_version_metadata()
    test_mcp_server_factory()
    test_cli_version()
    test_cli_help()
    print("\nAll smoke tests passed.")
