"""Tests for vault structure validation - directory allow-list."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from vaultspec_core.config import reset_config
from vaultspec_core.vaultcore.models import VaultConstants


@pytest.fixture(autouse=True)
def _isolate_config():
    reset_config()
    yield
    reset_config()


def _make_vault(tmp_path: Path, subdirs: list[str]) -> Path:
    """Create a .vault/ with the given subdirectory names."""
    vault = tmp_path / ".vault"
    vault.mkdir()
    for d in subdirs:
        (vault / d).mkdir()
    return tmp_path


class TestAuxiliaryDirectories:
    """Ensure data/ and logs/ are accepted by validate_vault_structure."""

    def test_data_directory_allowed(self, tmp_path: Path):
        root = _make_vault(tmp_path, ["adr", "data"])
        errors = VaultConstants.validate_vault_structure(root)
        assert errors == []

    def test_logs_directory_allowed(self, tmp_path: Path):
        root = _make_vault(tmp_path, ["plan", "logs"])
        errors = VaultConstants.validate_vault_structure(root)
        assert errors == []

    def test_unknown_directory_rejected(self, tmp_path: Path):
        root = _make_vault(tmp_path, ["adr", "unknown_dir"])
        errors = VaultConstants.validate_vault_structure(root)
        assert len(errors) == 1
        assert "unknown_dir" in errors[0]

    def test_hidden_directory_allowed(self, tmp_path: Path):
        root = _make_vault(tmp_path, ["adr", ".obsidian"])
        errors = VaultConstants.validate_vault_structure(root)
        assert errors == []

    def test_all_supported_directories_pass(self, tmp_path: Path):
        all_dirs = list(VaultConstants.SUPPORTED_DIRECTORIES) + list(
            VaultConstants.AUXILIARY_DIRECTORIES
        )
        root = _make_vault(tmp_path, all_dirs)
        errors = VaultConstants.validate_vault_structure(root)
        assert errors == []
