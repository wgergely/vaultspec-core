from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import pathlib
from tests._windows_temp_compat import install_windows_temp_compat
from tests.constants import (
    PROJECT_ROOT,
)
from vaultspec_core.config import VaultSpecConfig, get_config, reset_config

install_windows_temp_compat()


def _cleanup_test_project(root: pathlib.Path) -> None:
    """Remove transient artifacts, preserving .vault/ and README."""
    for item in root.iterdir():
        if item.name in (".vault", "README.md", ".gitignore"):
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


@pytest.fixture(scope="session", autouse=True)
def _vault_snapshot_reset():
    """Reset test-project/.vault/ to git HEAD after the full test session."""
    yield
    subprocess.run(
        ["git", "checkout", "--", "test-project/.vault/"],
        cwd=PROJECT_ROOT,
        check=False,
    )


@pytest.fixture
def vaultspec_config():
    """Provide a fresh VaultSpecConfig from current environment.

    Resets the singleton before and after to ensure test isolation.
    """
    reset_config()
    cfg = get_config()
    yield cfg
    reset_config()


@pytest.fixture
def config_override():
    """Factory fixture: call with overrides dict to get a custom config.

    Example::

        def test_custom_port(config_override):
            cfg = config_override({"mcp_port": 9999})
            assert cfg.mcp_port == 9999
    """
    created: list[VaultSpecConfig] = []

    def _make(overrides: dict) -> VaultSpecConfig:
        cfg = VaultSpecConfig.from_environment(overrides=overrides)
        created.append(cfg)
        return cfg

    yield _make
    reset_config()


@pytest.fixture
def clean_config():
    """Reset the config singleton before and after the test."""
    reset_config()
    yield
    reset_config()
