"""Tests for the centralized configuration system."""

from __future__ import annotations

import os
from pathlib import Path

from vaultspec_core.config import (
    CONFIG_REGISTRY,
    VaultSpecConfig,
    get_config,
    parse_csv_list,
    parse_float_or_none,
    parse_int_or_none,
    reset_config,
)


class TestConfigParsing:
    """Test individual type parsing helper functions."""

    def test_parse_csv_list(self):
        assert parse_csv_list("a, b,  c") == ["a", "b", "c"]
        assert parse_csv_list("one") == ["one"]
        assert parse_csv_list("") == []
        assert parse_csv_list(" , , ") == []

    def test_parse_int_or_none(self):
        assert parse_int_or_none("123") == 123
        assert parse_int_or_none("0") == 0
        assert parse_int_or_none("-1") == -1
        assert parse_int_or_none("abc") is None
        assert parse_int_or_none("") is None
        assert parse_int_or_none(None) is None

    def test_parse_float_or_none(self):
        assert parse_float_or_none("1.23") == 1.23
        assert parse_float_or_none("0") == 0.0
        assert parse_float_or_none(".5") == 0.5
        assert parse_float_or_none("abc") is None
        assert parse_float_or_none("") is None
        assert parse_float_or_none(None) is None


class TestVaultSpecConfig:
    """Test the VaultSpecConfig dataclass and environment loading logic."""

    def test_default_values(self, clean_config):
        cfg = get_config()
        assert cfg.target_dir == Path.cwd()
        assert cfg.docs_dir == ".vault"
        assert cfg.framework_dir == ".vaultspec"
        assert cfg.antigravity_dir == ".agents"
        assert cfg.io_buffer_size == 8192
        assert cfg.terminal_output_limit == 1_000_000

    def test_from_environment(self):
        old_docs = os.environ.get("VAULTSPEC_DOCS_DIR")
        old_buf = os.environ.get("VAULTSPEC_IO_BUFFER_SIZE")
        os.environ["VAULTSPEC_DOCS_DIR"] = "custom_vault"
        os.environ["VAULTSPEC_IO_BUFFER_SIZE"] = "16384"
        try:
            cfg = VaultSpecConfig.from_environment()
            assert cfg.docs_dir == "custom_vault"
            assert cfg.io_buffer_size == 16384
        finally:
            if old_docs is None:
                os.environ.pop("VAULTSPEC_DOCS_DIR", None)
            else:
                os.environ["VAULTSPEC_DOCS_DIR"] = old_docs
            if old_buf is None:
                os.environ.pop("VAULTSPEC_IO_BUFFER_SIZE", None)
            else:
                os.environ["VAULTSPEC_IO_BUFFER_SIZE"] = old_buf

    def test_overrides_precedence(self):
        old = os.environ.get("VAULTSPEC_DOCS_DIR")
        os.environ["VAULTSPEC_DOCS_DIR"] = "env_vault"
        try:
            cfg = VaultSpecConfig.from_environment(
                overrides={"docs_dir": "manual_vault"}
            )
            assert cfg.docs_dir == "manual_vault"
        finally:
            if old is None:
                os.environ.pop("VAULTSPEC_DOCS_DIR", None)
            else:
                os.environ["VAULTSPEC_DOCS_DIR"] = old

    def test_singleton_management(self):
        reset_config()
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

        reset_config()
        cfg3 = get_config()
        assert cfg3 is not cfg1

    def test_validation_min_value(self, caplog):
        # io_buffer_size has min_value=1
        old = os.environ.get("VAULTSPEC_IO_BUFFER_SIZE")
        os.environ["VAULTSPEC_IO_BUFFER_SIZE"] = "0"
        try:
            cfg = VaultSpecConfig.from_environment()
            assert cfg.io_buffer_size == 8192  # falls back to default
            assert "below minimum" in caplog.text
        finally:
            if old is None:
                os.environ.pop("VAULTSPEC_IO_BUFFER_SIZE", None)
            else:
                os.environ["VAULTSPEC_IO_BUFFER_SIZE"] = old


def test_registry_coverage():
    """Ensure all fields in the dataclass are represented in the registry."""
    from dataclasses import fields

    registry_attrs = {var.attr_name for var in CONFIG_REGISTRY}
    config_attrs = {f.name for f in fields(VaultSpecConfig)}

    assert registry_attrs == config_attrs
