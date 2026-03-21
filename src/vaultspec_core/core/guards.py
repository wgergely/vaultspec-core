"""Dev-repo protection guard for vaultspec-core.

Detects when the effective ``TARGET_DIR`` is the vaultspec-core source
repository and refuses destructive writes (install, uninstall, sync) that
would corrupt the canonical ``.vaultspec/`` content.

Detection is definitive: a ``pyproject.toml`` at the target root whose
``[project].name`` equals ``"vaultspec-core"`` can never appear in any
normal installed project.

The guard can be bypassed with the ``VAULTSPEC_ALLOW_DEV_WRITES``
environment variable for intentional development operations.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from .exceptions import VaultSpecError

logger = logging.getLogger(__name__)

_PROJECT_NAME = "vaultspec-core"
_ENV_OVERRIDE = "VAULTSPEC_ALLOW_DEV_WRITES"


class DevRepoProtectionError(VaultSpecError):
    """Raised when an operation would modify the dev repo's managed content."""


def is_dev_repo(root: Path) -> bool:
    """Return ``True`` if *root* is the vaultspec-core source repository.

    Checks for a ``pyproject.toml`` whose ``[project].name`` field matches
    ``"vaultspec-core"``.  Uses ``tomllib`` (stdlib ≥3.11) for parsing.

    Args:
        root: Directory to inspect.
    """
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return False

    import tomllib

    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return data.get("project", {}).get("name") == _PROJECT_NAME
    except Exception:
        return False


@lru_cache(maxsize=4)
def _cached_is_dev_repo(root_str: str) -> bool:
    """Memoized wrapper  - avoids re-parsing pyproject.toml on every call."""
    return is_dev_repo(Path(root_str))


def guard_dev_repo(target: Path) -> None:
    """Raise :class:`DevRepoProtectionError` if *target* is the dev repo.

    Does nothing when the ``VAULTSPEC_ALLOW_DEV_WRITES`` env var is set to
    a truthy value (``1``, ``true``, ``yes``).

    Args:
        target: The effective ``TARGET_DIR`` for the current operation.

    Raises:
        DevRepoProtectionError: If the target is detected as the source repo
            and the override env var is not set.
    """
    override = os.environ.get(_ENV_OVERRIDE, "").strip().lower()
    if override in ("1", "true", "yes"):
        return

    resolved = target.resolve()
    if _cached_is_dev_repo(str(resolved)):
        raise DevRepoProtectionError(
            f"Refusing to modify '{resolved}'  - this is the vaultspec-core "
            f"source repository.\n"
            f"  Use --target to specify a project directory.",
            hint=f"Set {_ENV_OVERRIDE}=1 to override this protection.",
        )
