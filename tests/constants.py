"""Centralized test constants for vaultspec test suite.

This module consolidates all test-only constants that were previously
scattered across multiple conftest.py files.  Import from here instead
of redefining values in individual conftest modules.

NOTE: This module must NOT import from core.config -- test constants
are independent of the production configuration system.
"""

from __future__ import annotations

import pathlib

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

#: Repository root (one directory above: tests/ -> repo)
PROJECT_ROOT: pathlib.Path = pathlib.Path(__file__).resolve().parent.parent

#: src/vaultspec/ — the library source root
LIB_SRC: pathlib.Path = PROJECT_ROOT / "src" / "vaultspec"

#: CLI entry points are now modules inside the vaultspec package
SCRIPTS: pathlib.Path = PROJECT_ROOT / "src" / "vaultspec"

#: test-project/ fixture directory (git-tracked .vault/ seed corpus)
TEST_PROJECT: pathlib.Path = PROJECT_ROOT / "test-project"

#: test-project/.vault/ documentation vault
TEST_VAULT: pathlib.Path = TEST_PROJECT / ".vault"

# ---------------------------------------------------------------------------
# GPU fast corpus (13 representative docs covering all 5 doc_types)
# ---------------------------------------------------------------------------

GPU_FAST_CORPUS_STEMS: frozenset[str] = frozenset(
    [
        # adr (4)
        "2026-02-05-editor-demo-architecture",
        "2026-02-06-displaymap-architecture-design",
        "2026-02-06-main-window-architecture",
        "2026-02-07-dispatch-architecture",
        # plan (2)
        "2026-02-05-editor-demo-phase1-plan",
        "2026-02-06-main-window-master-plan",
        # exec (2)
        "2026-02-05-turn-completion-summary",
        "2026-02-06-layout-alignment-summary",
        # reference (3)
        "2026-02-07-main-window-safety-audit",
        "2026-02-05-editor-demo-core-reference",
        "2026-02-04-displaymap-reference",
        # research (2)
        "2026-02-05-editor-demo-research",
        "2026-02-07-dispatch-protocol-alignment-audit",
    ]
)

# ---------------------------------------------------------------------------
# Lance directory suffixes (test isolation)
# ---------------------------------------------------------------------------

LANCE_SUFFIX_FAST: str = "-fast"
LANCE_SUFFIX_FULL: str = "-full"
LANCE_SUFFIX_UNIT: str = "-fast-unit"

# ---------------------------------------------------------------------------
# Test port constants
# ---------------------------------------------------------------------------

TEST_PORT_BASE: int = 10001
TEST_PORT_A2A_BASE: int = 10020
TEST_PORT_SUBAGENT: int = 10010

# ---------------------------------------------------------------------------
# Timeout constants (seconds)
# ---------------------------------------------------------------------------

TIMEOUT_QUICK: int = 15
TIMEOUT_INTEGRATION: int = 120
TIMEOUT_E2E: int = 180
TIMEOUT_CLAUDE_E2E: int = 60
TIMEOUT_GEMINI_E2E: int = 60
TIMEOUT_MCP_E2E: int = 180
TIMEOUT_FULL_CYCLE: int = 180
TIMEOUT_A2A_E2E: int = 300

# ---------------------------------------------------------------------------
# Delay constants (seconds) -- used in asyncio.sleep / time.sleep
# ---------------------------------------------------------------------------

DELAY_SHORT: float = 0.2
DELAY_MEDIUM: float = 0.3
DELAY_LONG: float = 1.0

# ---------------------------------------------------------------------------
# ACP test helper timeouts (seconds)
# ---------------------------------------------------------------------------

ACP_TIMEOUT_READ: float = 10.0
ACP_TIMEOUT_MESSAGE: float = 30.0
