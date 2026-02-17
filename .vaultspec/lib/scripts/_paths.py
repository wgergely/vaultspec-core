"""Shared path bootstrap for .vaultspec/lib/scripts/ entry points.

Provides ROOT_DIR, LIB_SRC_DIR, and ensures LIB_SRC_DIR is on sys.path
so that library modules under .vaultspec/lib/src/ can be imported directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_LIB_DIR: Path = _SCRIPTS_DIR.parent  # .vaultspec/lib/
ROOT_DIR: Path = _LIB_DIR.parent.parent  # scripts -> lib -> .vaultspec -> root
LIB_SRC_DIR: Path = _LIB_DIR / "src"

if str(LIB_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_SRC_DIR))
