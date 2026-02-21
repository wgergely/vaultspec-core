"""Unit tests for core.config module."""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultspec.core.config import (
    CONFIG_REGISTRY,
    ConfigVariable,
    VaultSpecConfig,
    get_config,
    parse_csv_list,
    parse_float_or_none,
    parse_int_or_none,
    reset_config,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _clean_env_and_singleton(monkeypatch):
    """Remove all VAULTSPEC_* env vars, and reset the singleton."""
    import os

    for key in list(os.environ):
        if key.startswith("VAULTSPEC_"):
            monkeypatch.delenv(key)
    reset_config()
    yield
    reset_config()


class TestDefaults:
    """All defaults must match current hardcoded values in production code."""

    def test_agent_defaults(self):
        cfg = VaultSpecConfig()
        assert isinstance(cfg.root_dir, Path)
        assert cfg.agent_mode == "read-write"
        assert cfg.system_prompt is None
        assert cfg.max_turns is None
        assert cfg.budget_usd is None
        assert cfg.allowed_tools == []
        assert cfg.disallowed_tools == []
        assert cfg.effort is None
        assert cfg.output_format is None
        assert cfg.fallback_model is None
        assert cfg.include_dirs == []

    def test_mcp_defaults(self):
        cfg = VaultSpecConfig()
        assert cfg.mcp_root_dir is None
        assert cfg.mcp_port == 10010
        assert cfg.mcp_host == "0.0.0.0"
        assert cfg.mcp_ttl_seconds == 3600.0

    def test_a2a_defaults(self):
        cfg = VaultSpecConfig()
        assert cfg.a2a_default_port == 10010
        assert cfg.a2a_host == "localhost"

    def test_storage_defaults(self):
        cfg = VaultSpecConfig()
        assert cfg.docs_dir == ".vault"
        assert cfg.framework_dir == ".vaultspec"
        assert cfg.lance_dir == ".lance"
        assert cfg.index_metadata_file == "index_meta.json"

    def test_tool_directory_defaults(self):
        cfg = VaultSpecConfig()
        assert cfg.claude_dir == ".claude"
        assert cfg.gemini_dir == ".gemini"
        assert cfg.agent_dir == ".agent"

    def test_orchestration_defaults(self):
        cfg = VaultSpecConfig()
        assert cfg.task_engine_ttl_seconds == 3600.0

    def test_rag_defaults(self):
        cfg = VaultSpecConfig()
        assert cfg.graph_ttl_seconds == 300.0
        assert cfg.embedding_batch_size == 64
        assert cfg.max_embed_chars == 8000

    def test_io_defaults(self):
        cfg = VaultSpecConfig()
        assert cfg.io_buffer_size == 8192
        assert cfg.terminal_output_limit == 1_000_000

    def test_storage_paths_are_str(self):
        cfg = VaultSpecConfig()
        for attr in (
            "docs_dir",
            "framework_dir",
            "lance_dir",
            "index_metadata_file",
            "claude_dir",
            "gemini_dir",
            "agent_dir",
        ):
            assert isinstance(getattr(cfg, attr), str), f"{attr} should be str"

    def test_root_dir_is_path(self):
        cfg = VaultSpecConfig()
        assert isinstance(cfg.root_dir, Path)


class TestEnvVarLoading:
    """VAULTSPEC_* env vars load correctly."""

    def test_string_env_var(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_AGENT_MODE", "read-only")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.agent_mode == "read-only"

    def test_int_env_var(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_PORT", "8080")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_port == 8080

    def test_float_env_var(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_TTL_SECONDS", "7200.5")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_ttl_seconds == 7200.5

    def test_csv_list_env_var(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_ALLOWED_TOOLS", "tool1, tool2, tool3")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.allowed_tools == ["tool1", "tool2", "tool3"]

    def test_path_env_var(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_ROOT_DIR", "/tmp/myproject")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.root_dir == Path("/tmp/myproject")

    def test_optional_int_env_var(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MAX_TURNS", "25")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.max_turns == 25

    def test_optional_float_env_var(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_BUDGET_USD", "99.99")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.budget_usd == 99.99


class TestOverrideDict:
    """Override dict takes precedence over env vars."""

    def test_override_over_env(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_AGENT_MODE", "read-only")
        cfg = VaultSpecConfig.from_environment(overrides={"agent_mode": "read-write"})
        assert cfg.agent_mode == "read-write"

    def test_override_with_none_env(self):
        cfg = VaultSpecConfig.from_environment(overrides={"max_turns": 42})
        assert cfg.max_turns == 42

    def test_override_path(self):
        p = Path("/custom/root")
        cfg = VaultSpecConfig.from_environment(overrides={"root_dir": p})
        assert cfg.root_dir == p

    def test_override_list(self):
        tools = ["a", "b"]
        cfg = VaultSpecConfig.from_environment(overrides={"allowed_tools": tools})
        assert cfg.allowed_tools == tools


class TestIntParsing:
    """Integer config values parse correctly."""

    def test_valid_int(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_EMBEDDING_BATCH_SIZE", "128")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.embedding_batch_size == 128

    def test_invalid_int_falls_back(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_PORT", "not-a-number")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_port == 10010

    def test_float_string_for_int_fails(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_IO_BUFFER_SIZE", "8192.5")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.io_buffer_size == 8192


class TestFloatParsing:
    """Float config values parse correctly."""

    def test_valid_float(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_GRAPH_TTL_SECONDS", "600.0")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.graph_ttl_seconds == 600.0

    def test_int_string_as_float(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_TTL_SECONDS", "7200")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_ttl_seconds == 7200.0

    def test_invalid_float_falls_back(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_TTL_SECONDS", "abc")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_ttl_seconds == 3600.0


class TestCsvListParsing:
    """Comma-separated lists parse correctly with whitespace handling."""

    def test_simple_csv(self):
        assert parse_csv_list("a,b,c") == ["a", "b", "c"]

    def test_csv_with_spaces(self):
        assert parse_csv_list("a, b , c") == ["a", "b", "c"]

    def test_empty_string(self):
        assert parse_csv_list("") == []

    def test_trailing_comma(self):
        assert parse_csv_list("a,b,") == ["a", "b"]

    def test_only_commas(self):
        assert parse_csv_list(",,,") == []

    def test_single_item(self):
        assert parse_csv_list("tool1") == ["tool1"]

    def test_csv_env_var_integration(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_DISALLOWED_TOOLS", "rm, git push, drop")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.disallowed_tools == ["rm", "git push", "drop"]


class TestPathParsing:
    """Path values parse correctly."""

    def test_absolute_path(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_ROOT_DIR", "/var/project")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_root_dir == Path("/var/project")

    def test_relative_path(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_ROOT_DIR", "relative/path")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.root_dir == Path("relative/path")


class TestOptionValidation:
    """Invalid enum/option values are rejected."""

    def test_invalid_agent_mode(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_AGENT_MODE", "delete-everything")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.agent_mode == "read-write"  # falls back to default

    def test_valid_agent_mode_read_only(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_AGENT_MODE", "read-only")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.agent_mode == "read-only"

    def test_valid_agent_mode_read_write(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_AGENT_MODE", "read-write")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.agent_mode == "read-write"


class TestRangeValidation:
    """Out-of-range values are rejected."""

    def test_port_below_min(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_PORT", "0")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_port == 10010

    def test_port_above_max(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_PORT", "99999")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_port == 10010

    def test_negative_ttl(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_TTL_SECONDS", "-1")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_ttl_seconds == 3600.0

    def test_batch_size_zero(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_EMBEDDING_BATCH_SIZE", "0")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.embedding_batch_size == 64

    def test_max_turns_zero(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MAX_TURNS", "0")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.max_turns is None  # below min_value=1

    def test_valid_max_turns(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MAX_TURNS", "1")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.max_turns == 1


class TestRequiredVars:
    """Missing required vars raise ValueError."""

    def test_required_var_missing_raises(self):
        # Temporarily make a var required for this test
        var = ConfigVariable(
            env_name="VAULTSPEC_REQUIRED_TEST",
            attr_name="mcp_root_dir",
            var_type=Path,
            default=None,
            description="Test required var",
            required=True,
        )
        original = CONFIG_REGISTRY[:]
        CONFIG_REGISTRY.clear()
        CONFIG_REGISTRY.append(var)
        try:
            with pytest.raises(ValueError, match="Required config variable"):
                VaultSpecConfig.from_environment()
        finally:
            CONFIG_REGISTRY.clear()
            CONFIG_REGISTRY.extend(original)

    def test_required_var_with_override_ok(self):
        var = ConfigVariable(
            env_name="VAULTSPEC_REQUIRED_TEST",
            attr_name="mcp_root_dir",
            var_type=Path,
            default=None,
            description="Test required var",
            required=True,
        )
        original = CONFIG_REGISTRY[:]
        CONFIG_REGISTRY.clear()
        CONFIG_REGISTRY.append(var)
        try:
            cfg = VaultSpecConfig.from_environment(
                overrides={"mcp_root_dir": Path("/tmp")}
            )
            assert cfg.mcp_root_dir == Path("/tmp")
        finally:
            CONFIG_REGISTRY.clear()
            CONFIG_REGISTRY.extend(original)


class TestSingleton:
    """get_config / reset_config singleton management."""

    def test_get_config_caching(self):
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

    def test_reset_config_clears(self):
        cfg1 = get_config()
        reset_config()
        cfg2 = get_config()
        assert cfg1 is not cfg2

    def test_override_bypasses_cache(self):
        cfg1 = get_config()
        cfg2 = get_config(overrides={"agent_mode": "read-only"})
        assert cfg1 is not cfg2
        assert cfg2.agent_mode == "read-only"

    def test_override_does_not_pollute_cache(self):
        cfg1 = get_config()
        get_config(overrides={"agent_mode": "read-only"})
        cfg3 = get_config()
        assert cfg3 is cfg1
        assert cfg3.agent_mode == "read-write"


class TestIsolation:
    """Config changes don't leak between tests."""

    def test_env_does_not_leak_a(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_AGENT_MODE", "read-only")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.agent_mode == "read-only"

    def test_env_does_not_leak_b(self):
        cfg = VaultSpecConfig.from_environment()
        assert cfg.agent_mode == "read-write"


class TestRegistry:
    """CONFIG_REGISTRY integrity checks."""

    def test_registry_count(self):
        assert len(CONFIG_REGISTRY) == 38

    def test_all_attr_names_unique(self):
        names = [v.attr_name for v in CONFIG_REGISTRY]
        assert len(names) == len(set(names))

    def test_all_env_names_unique(self):
        names = [v.env_name for v in CONFIG_REGISTRY]
        assert len(names) == len(set(names))

    def test_all_env_names_prefixed(self):
        for var in CONFIG_REGISTRY:
            assert var.env_name.startswith("VAULTSPEC_"), var.env_name

    def test_all_attrs_exist_on_dataclass(self):
        cfg = VaultSpecConfig()
        for var in CONFIG_REGISTRY:
            assert hasattr(cfg, var.attr_name), (
                f"VaultSpecConfig missing attr: {var.attr_name}"
            )


class TestHelperParsers:
    """Standalone parser function tests."""

    def test_parse_int_or_none_valid(self):
        assert parse_int_or_none("42") == 42

    def test_parse_int_or_none_invalid(self):
        assert parse_int_or_none("abc") is None

    def test_parse_int_or_none_float_string(self):
        assert parse_int_or_none("3.14") is None

    def test_parse_float_or_none_valid(self):
        assert parse_float_or_none("3.14") == pytest.approx(3.14)

    def test_parse_float_or_none_int_string(self):
        assert parse_float_or_none("42") == 42.0

    def test_parse_float_or_none_invalid(self):
        assert parse_float_or_none("xyz") is None
