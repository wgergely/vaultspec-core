"""Centralized test constants for vaultspec test suite.

This module consolidates all test-only constants that were previously
scattered across multiple conftest.py files.  Import from here instead
of redefining values in individual conftest modules.

NOTE: This module must NOT import from core.config -- test constants
are independent of the production configuration system.
"""

from __future__ import annotations

import pathlib

#: Repository root (one directory above: tests/ -> repo)
PROJECT_ROOT: pathlib.Path = pathlib.Path(__file__).resolve().parent.parent

#: src/vaultspec_core/ — the library source root
LIB_SRC: pathlib.Path = PROJECT_ROOT / "src" / "vaultspec_core"

#: CLI entry points are now modules inside the vaultspec_core package
SCRIPTS: pathlib.Path = PROJECT_ROOT / "src" / "vaultspec_core"

#: test-project/ fixture directory (git-tracked .vault/ seed corpus)
TEST_PROJECT: pathlib.Path = PROJECT_ROOT / "test-project"

#: test-project/.vault/ documentation vault
TEST_VAULT: pathlib.Path = TEST_PROJECT / ".vault"

TEST_PORT_BASE: int = 10001
TEST_PORT_EXECUTION: int = 10010

TIMEOUT_QUICK: int = 15
TIMEOUT_INTEGRATION: int = 120
TIMEOUT_E2E: int = 180
TIMEOUT_CLAUDE_E2E: int = 60
TIMEOUT_GEMINI_E2E: int = 60
TIMEOUT_MCP_E2E: int = 180
TIMEOUT_FULL_CYCLE: int = 180
TIMEOUT_A2A_E2E: int = 300

DELAY_SHORT: float = 0.2
DELAY_MEDIUM: float = 0.3
DELAY_LONG: float = 1.0

ACP_TIMEOUT_READ: float = 10.0
ACP_TIMEOUT_MESSAGE: float = 30.0
