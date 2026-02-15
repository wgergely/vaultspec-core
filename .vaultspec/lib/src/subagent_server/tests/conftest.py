"""Subagent server unit test fixtures."""

import sys
from pathlib import Path

# Ensure lib/src is importable
_LIB_SRC = Path(__file__).resolve().parent.parent.parent
if str(_LIB_SRC) not in sys.path:
    sys.path.insert(0, str(_LIB_SRC))

# Canonical test fixture root (git-tracked seed corpus)
_PROJECT_ROOT = _LIB_SRC.parents[2]
TEST_PROJECT = _PROJECT_ROOT / "test-project"
