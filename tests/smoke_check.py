"""Smoke checks for built distribution artifacts.

Run against an installed wheel or sdist to verify that the package is
importable, exposes expected metadata, and that both console-script entry
points (``vaultspec-core`` and ``vaultspec-mcp``) are functional.

Usage from CI::

    uv run --isolated --no-project --with dist/*.whl tests/smoke_check.py

This script is NOT a pytest test suite.  Functions are named ``check_*``
(not ``test_*``) and the file is named ``smoke_check.py`` (not
``*_test.py``) to prevent pytest from collecting it.  Failures call
``sys.exit(1)`` which would kill the pytest runner.
"""

from __future__ import annotations

import importlib.metadata
import shutil
import subprocess
import sys


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _run_script(name: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a console script, falling back to ``python -m`` if not on PATH."""
    script = shutil.which(name)
    if script:
        cmd = [script, *args]
    else:
        # Fallback: not every install context puts scripts on PATH
        module = name.replace("-", "_")
        if name == "vaultspec-mcp":
            module = "vaultspec_core.mcp_server.app"
        cmd = [sys.executable, "-m", module, *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def check_import() -> None:
    try:
        import vaultspec_core  # noqa: F401
    except ImportError as exc:
        _fail(f"import vaultspec_core raised {exc}")
    print("PASS: import vaultspec_core")


def check_version_metadata() -> None:
    version = importlib.metadata.version("vaultspec-core")
    if not version:
        _fail("importlib.metadata.version returned empty string")
    print(f"PASS: version = {version}")


def check_entry_points_registered() -> None:
    """Verify that [project.scripts] entry points are in wheel metadata."""
    eps = importlib.metadata.entry_points()
    console_scripts = {ep.name for ep in eps if ep.group == "console_scripts"}
    for name in ("vaultspec-core", "vaultspec-mcp"):
        if name not in console_scripts:
            _fail(
                f"console_scripts entry point '{name}' not found in metadata.\n"
                f"  Available: {sorted(console_scripts)}"
            )
    print("PASS: both console_scripts entry points registered")


def check_mcp_server_factory() -> None:
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


def check_cli_version() -> None:
    result = _run_script("vaultspec-core", ["--version"])
    if result.returncode != 0:
        _fail(
            f"vaultspec-core --version exited {result.returncode}\n"
            f"  stderr: {result.stderr.strip()}"
        )
    print(f"PASS: vaultspec-core --version -> {result.stdout.strip()}")


def check_cli_help() -> None:
    result = _run_script("vaultspec-core", ["--help"])
    if result.returncode != 0:
        _fail(
            f"vaultspec-core --help exited {result.returncode}\n"
            f"  stderr: {result.stderr.strip()}"
        )
    for expected in ("install", "sync", "vault"):
        if expected not in result.stdout.lower():
            _fail(f"--help output missing expected command '{expected}'")
    print("PASS: vaultspec-core --help contains expected commands")


def check_mcp_entrypoint() -> None:
    """Verify vaultspec-mcp starts and exits cleanly with --help."""
    result = _run_script("vaultspec-mcp", ["--help"])
    if result.returncode != 0:
        _fail(
            f"vaultspec-mcp --help exited {result.returncode}\n"
            f"  stderr: {result.stderr.strip()}"
        )
    print("PASS: vaultspec-mcp --help exits 0")


if __name__ == "__main__":
    check_import()
    check_version_metadata()
    check_entry_points_registered()
    check_mcp_server_factory()
    check_cli_version()
    check_cli_help()
    check_mcp_entrypoint()
    print("\nAll smoke checks passed.")
