"""Shared path bootstrap for .vaultspec/lib/scripts/ entry points.

Provides ROOT_DIR, LIB_SRC_DIR, and ensures LIB_SRC_DIR is on sys.path
so that library modules under .vaultspec/lib/src/ can be imported directly.

Two-step bootstrap:
  1. Compute framework paths structurally (always correct for code location).
  2. Import core.workspace and resolve the full layout from overrides + git.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Step 1: Structural bootstrap (always correct for framework location).
# This is WHERE THE PYTHON CODE LIVES -- not where content lives.
_SCRIPTS_DIR = Path(__file__).resolve().parent
_LIB_DIR: Path = _SCRIPTS_DIR.parent  # .vaultspec/lib/
_FRAMEWORK_ROOT: Path = _LIB_DIR.parent  # .vaultspec/
LIB_SRC_DIR: Path = _LIB_DIR / "src"

if str(LIB_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_SRC_DIR))


# Step 2: Now safe to import from the library.
def _env_path(name: str) -> Path | None:
    """Read an env var as a Path, or None if unset/empty."""
    raw = os.environ.get(name)
    return Path(raw) if raw else None


from core.workspace import resolve_workspace  # noqa: E402

_layout = resolve_workspace(
    root_override=_env_path("VAULTSPEC_ROOT_DIR"),
    content_override=_env_path("VAULTSPEC_CONTENT_DIR"),
    framework_dir_name=os.environ.get("VAULTSPEC_FRAMEWORK_DIR", ".vaultspec"),
    framework_root=_FRAMEWORK_ROOT,
)

ROOT_DIR: Path = _layout.output_root
