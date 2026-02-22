"""Comprehensive unit tests for core.config module."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from vaultspec.config.config import (
    CONFIG_REGISTRY,
    VaultSpecConfig,
    _OptionalFloat,
    _OptionalInt,
    get_config,
    parse_csv_list,
    parse_float_or_none,
    parse_int_or_none,
    reset_config,
)


@pytest.fixture(autouse=True)
def clean_config():
    """Reset config singleton between every test."""
    reset_config()
    yield
    reset_config()


# ---- Helper parsers --------------------------------------------------------


@pytest.mark.unit
class TestParseCsvList:
    def test_basic_split(self):
        assert parse_csv_list("a,b,c") == ["a", "b", "c"]

    def test_strips_whitespace(self):
        assert parse_csv_list(" a , b , c ") == ["a", "b", "c"]

    def test_empty_string(self):
        assert parse_csv_list("") == []

    def test_skips_empty_items(self):
        assert parse_csv_list("a,,b, ,c") == ["a", "b", "c"]

    def test_single_item(self):
        assert parse_csv_list("only") == ["only"]


@pytest.mark.unit
class TestParseIntOrNone:
    def test_valid_int(self):
        assert parse_int_or_none("42") == 42

    def test_negative_int(self):
        assert parse_int_or_none("-10") == -10

    def test_invalid_returns_none(self):
        assert parse_int_or_none("abc") is None

    def test_empty_returns_none(self):
        assert parse_int_or_none("") is None

    def test_float_string_returns_none(self):
        assert parse_int_or_none("3.14") is None


@pytest.mark.unit
class TestParseFloatOrNone:
    def test_valid_float(self):
        assert parse_float_or_none("3.14") == 3.14

    def test_integer_string(self):
        assert parse_float_or_none("42") == 42.0

    def test_negative(self):
        assert parse_float_or_none("-1.5") == -1.5

    def test_invalid_returns_none(self):
        assert parse_float_or_none("abc") is None

    def test_empty_returns_none(self):
        assert parse_float_or_none("") is None


# ---- Default values --------------------------------------------------------


@pytest.mark.unit
class TestDefaults:
    """Ensure every default on VaultSpecConfig matches the documented values."""

    def test_agent_mode(self):
        cfg = VaultSpecConfig()
        assert cfg.agent_mode == "read-write"

    def test_system_prompt(self):
        cfg = VaultSpecConfig()
        assert cfg.system_prompt is None

    def test_max_turns(self):
        cfg = VaultSpecConfig()
        assert cfg.max_turns is None

    def test_budget_usd(self):
        cfg = VaultSpecConfig()
        assert cfg.budget_usd is None

    def test_allowed_tools(self):
        cfg = VaultSpecConfig()
        assert cfg.allowed_tools == []

    def test_disallowed_tools(self):
        cfg = VaultSpecConfig()
        assert cfg.disallowed_tools == []

    def test_effort(self):
        cfg = VaultSpecConfig()
        assert cfg.effort is None

    def test_output_format(self):
        cfg = VaultSpecConfig()
        assert cfg.output_format is None

    def test_fallback_model(self):
        cfg = VaultSpecConfig()
        assert cfg.fallback_model is None

    def test_include_dirs(self):
        cfg = VaultSpecConfig()
        assert cfg.include_dirs == []

    def test_mcp_root_dir(self):
        cfg = VaultSpecConfig()
        assert cfg.mcp_root_dir is None

    def test_mcp_port(self):
        cfg = VaultSpecConfig()
        assert cfg.mcp_port == 10010

    def test_mcp_host(self):
        cfg = VaultSpecConfig()
        assert cfg.mcp_host == "0.0.0.0"

    def test_mcp_ttl_seconds(self):
        cfg = VaultSpecConfig()
        assert cfg.mcp_ttl_seconds == 3600.0

    def test_a2a_default_port(self):
        cfg = VaultSpecConfig()
        assert cfg.a2a_default_port == 10010

    def test_a2a_host(self):
        cfg = VaultSpecConfig()
        assert cfg.a2a_host == "localhost"

    def test_docs_dir(self):
        cfg = VaultSpecConfig()
        assert cfg.docs_dir == ".vault"

    def test_framework_dir(self):
        cfg = VaultSpecConfig()
        assert cfg.framework_dir == ".vaultspec"

    def test_lance_dir(self):
        cfg = VaultSpecConfig()
        assert cfg.lance_dir == ".lance"

    def test_index_metadata_file(self):
        cfg = VaultSpecConfig()
        assert cfg.index_metadata_file == "index_meta.json"

    def test_claude_dir(self):
        cfg = VaultSpecConfig()
        assert cfg.claude_dir == ".claude"

    def test_gemini_dir(self):
        cfg = VaultSpecConfig()
        assert cfg.gemini_dir == ".gemini"

    def test_agent_dir(self):
        cfg = VaultSpecConfig()
        assert cfg.agent_dir == ".agent"

    def test_task_engine_ttl_seconds(self):
        cfg = VaultSpecConfig()
        assert cfg.task_engine_ttl_seconds == 3600.0

    def test_graph_ttl_seconds(self):
        cfg = VaultSpecConfig()
        assert cfg.graph_ttl_seconds == 300.0

    def test_embedding_batch_size(self):
        cfg = VaultSpecConfig()
        assert cfg.embedding_batch_size == 64

    def test_max_embed_chars(self):
        cfg = VaultSpecConfig()
        assert cfg.max_embed_chars == 8000

    def test_io_buffer_size(self):
        cfg = VaultSpecConfig()
        assert cfg.io_buffer_size == 8192

    def test_terminal_output_limit(self):
        cfg = VaultSpecConfig()
        assert cfg.terminal_output_limit == 1_000_000


# ---- Environment variable loading ------------------------------------------


@pytest.mark.unit
class TestEnvVarLoading:
    """Test VAULTSPEC_* env var loading via from_environment."""

    def test_string_var(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_AGENT_MODE", "read-only")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.agent_mode == "read-only"

    def test_int_var(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_PORT", "9999")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_port == 9999

    def test_float_var(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_TTL_SECONDS", "7200.5")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_ttl_seconds == 7200.5

    def test_csv_list_var(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_ALLOWED_TOOLS", "tool1, tool2 , tool3")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.allowed_tools == ["tool1", "tool2", "tool3"]

    def test_path_var(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_ROOT_DIR", "/tmp/test-root")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.root_dir == Path("/tmp/test-root")

    def test_optional_string_set(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_SYSTEM_PROMPT", "Be helpful.")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.system_prompt == "Be helpful."

    def test_optional_string_unset(self):
        cfg = VaultSpecConfig.from_environment()
        assert cfg.system_prompt is None

    def test_optional_path_set(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_ROOT_DIR", "/srv/mcp")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_root_dir == Path("/srv/mcp")

    def test_optional_path_unset(self):
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_root_dir is None

    def test_multiple_vars_at_once(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_PORT", "5000")
        monkeypatch.setenv("VAULTSPEC_MCP_HOST", "127.0.0.1")
        monkeypatch.setenv("VAULTSPEC_DOCS_DIR", "docs")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_port == 5000
        assert cfg.mcp_host == "127.0.0.1"
        assert cfg.docs_dir == "docs"


# ---- Override dict ---------------------------------------------------------


@pytest.mark.unit
class TestOverrides:
    """Test from_environment(overrides={...}) takes highest precedence."""

    def test_override_takes_precedence_over_env(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_PORT", "9999")
        cfg = VaultSpecConfig.from_environment(overrides={"mcp_port": 8888})
        assert cfg.mcp_port == 8888

    def test_override_with_no_env(self):
        cfg = VaultSpecConfig.from_environment(overrides={"mcp_host": "192.168.1.1"})
        assert cfg.mcp_host == "192.168.1.1"

    def test_override_multiple_fields(self):
        cfg = VaultSpecConfig.from_environment(
            overrides={
                "mcp_port": 7777,
                "docs_dir": "custom-docs",
                "embedding_batch_size": 32,
            }
        )
        assert cfg.mcp_port == 7777
        assert cfg.docs_dir == "custom-docs"
        assert cfg.embedding_batch_size == 32

    def test_override_does_not_bypass_type(self):
        """Overrides are passed directly to the dataclass constructor, no parsing."""
        cfg = VaultSpecConfig.from_environment(overrides={"max_turns": 100})
        assert cfg.max_turns == 100
        assert isinstance(cfg.max_turns, int)


# ---- Type parsing ----------------------------------------------------------


@pytest.mark.unit
class TestTypeParsing:
    """Test parsing of env var strings into correct Python types."""

    def test_int_parsing(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_EMBEDDING_BATCH_SIZE", "128")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.embedding_batch_size == 128
        assert isinstance(cfg.embedding_batch_size, int)

    def test_float_parsing(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_GRAPH_TTL_SECONDS", "600.5")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.graph_ttl_seconds == 600.5
        assert isinstance(cfg.graph_ttl_seconds, float)

    def test_optional_int_none_by_default(self):
        cfg = VaultSpecConfig.from_environment()
        assert cfg.max_turns is None

    def test_optional_int_from_env(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MAX_TURNS", "50")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.max_turns == 50
        assert isinstance(cfg.max_turns, int)

    def test_optional_float_none_by_default(self):
        cfg = VaultSpecConfig.from_environment()
        assert cfg.budget_usd is None

    def test_optional_float_from_env(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_BUDGET_USD", "25.50")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.budget_usd == 25.50
        assert isinstance(cfg.budget_usd, float)

    def test_csv_empty_string(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_ALLOWED_TOOLS", "")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.allowed_tools == []

    def test_csv_whitespace_handling(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_ALLOWED_TOOLS", " tool1 , , tool2 , ")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.allowed_tools == ["tool1", "tool2"]

    def test_csv_single_item(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_DISALLOWED_TOOLS", "dangerous_tool")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.disallowed_tools == ["dangerous_tool"]

    def test_path_parsing(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_ROOT_DIR", "/some/path")
        cfg = VaultSpecConfig.from_environment()
        assert isinstance(cfg.root_dir, Path)
        assert cfg.root_dir == Path("/some/path")


# ---- Validation: invalid values fall back to defaults ----------------------


@pytest.mark.unit
class TestValidation:
    """Test that invalid env var values fall back to defaults instead of crashing."""

    def test_invalid_int_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("VAULTSPEC_MCP_PORT", "not_a_number")
        with caplog.at_level(logging.ERROR, logger="core.config"):
            cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_port == 10010  # default

    def test_invalid_float_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("VAULTSPEC_MCP_TTL_SECONDS", "not_a_float")
        with caplog.at_level(logging.ERROR, logger="core.config"):
            cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_ttl_seconds == 3600.0  # default

    def test_invalid_optional_int_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("VAULTSPEC_MAX_TURNS", "abc")
        with caplog.at_level(logging.ERROR, logger="core.config"):
            cfg = VaultSpecConfig.from_environment()
        assert cfg.max_turns is None  # default

    def test_invalid_optional_float_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("VAULTSPEC_BUDGET_USD", "xyz")
        with caplog.at_level(logging.ERROR, logger="core.config"):
            cfg = VaultSpecConfig.from_environment()
        assert cfg.budget_usd is None  # default

    def test_port_below_min_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("VAULTSPEC_MCP_PORT", "0")
        with caplog.at_level(logging.ERROR, logger="core.config"):
            cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_port == 10010  # min is 1, so 0 is rejected

    def test_port_above_max_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("VAULTSPEC_MCP_PORT", "70000")
        with caplog.at_level(logging.ERROR, logger="core.config"):
            cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_port == 10010  # max is 65535

    def test_port_at_min_boundary(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_PORT", "1")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_port == 1

    def test_port_at_max_boundary(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_PORT", "65535")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_port == 65535

    def test_embedding_batch_below_min_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("VAULTSPEC_EMBEDDING_BATCH_SIZE", "0")
        with caplog.at_level(logging.ERROR, logger="core.config"):
            cfg = VaultSpecConfig.from_environment()
        assert cfg.embedding_batch_size == 64  # min is 1

    def test_max_embed_chars_below_min_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("VAULTSPEC_MAX_EMBED_CHARS", "50")
        with caplog.at_level(logging.ERROR, logger="core.config"):
            cfg = VaultSpecConfig.from_environment()
        assert cfg.max_embed_chars == 8000  # min is 100

    def test_negative_ttl_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("VAULTSPEC_MCP_TTL_SECONDS", "-1")
        with caplog.at_level(logging.ERROR, logger="core.config"):
            cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_ttl_seconds == 3600.0  # min is 0

    def test_zero_ttl_accepted(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_TTL_SECONDS", "0")
        cfg = VaultSpecConfig.from_environment()
        assert cfg.mcp_ttl_seconds == 0.0  # min_value=0, so 0 is valid

    def test_max_turns_below_min_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("VAULTSPEC_MAX_TURNS", "0")
        with caplog.at_level(logging.ERROR, logger="core.config"):
            cfg = VaultSpecConfig.from_environment()
        assert cfg.max_turns is None  # min is 1, 0 is rejected

    def test_budget_negative_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("VAULTSPEC_BUDGET_USD", "-5.0")
        with caplog.at_level(logging.ERROR, logger="core.config"):
            cfg = VaultSpecConfig.from_environment()
        assert cfg.budget_usd is None  # min is 0

    def test_invalid_agent_mode_option_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("VAULTSPEC_AGENT_MODE", "admin")
        with caplog.at_level(logging.ERROR, logger="core.config"):
            cfg = VaultSpecConfig.from_environment()
        assert cfg.agent_mode == "read-write"  # default; "admin" not in options

    def test_valid_agent_mode_options(self, monkeypatch):
        for mode in ("read-write", "read-only"):
            monkeypatch.setenv("VAULTSPEC_AGENT_MODE", mode)
            cfg = VaultSpecConfig.from_environment()
            assert cfg.agent_mode == mode


# ---- Singleton management --------------------------------------------------


@pytest.mark.unit
class TestSingleton:
    """Test get_config / reset_config singleton behavior."""

    def test_get_config_returns_same_instance(self):
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

    def test_get_config_with_override_returns_fresh(self):
        cfg1 = get_config()
        cfg2 = get_config(overrides={"mcp_port": 9999})
        assert cfg1 is not cfg2
        assert cfg2.mcp_port == 9999

    def test_get_config_override_does_not_replace_singleton(self):
        cfg1 = get_config()
        get_config(overrides={"mcp_port": 9999})
        cfg3 = get_config()
        assert cfg3 is cfg1
        assert cfg3.mcp_port == 10010

    def test_reset_config_clears_singleton(self):
        cfg1 = get_config()
        reset_config()
        cfg2 = get_config()
        assert cfg1 is not cfg2

    def test_reset_config_twice_is_safe(self):
        reset_config()
        reset_config()
        cfg = get_config()
        assert cfg is not None

    def test_get_config_reads_env_on_first_call(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_HOST", "10.0.0.1")
        cfg = get_config()
        assert cfg.mcp_host == "10.0.0.1"

    def test_get_config_caches_and_ignores_later_env_changes(self, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_MCP_HOST", "10.0.0.1")
        cfg1 = get_config()
        monkeypatch.setenv("VAULTSPEC_MCP_HOST", "10.0.0.2")
        cfg2 = get_config()
        assert cfg2 is cfg1
        assert cfg2.mcp_host == "10.0.0.1"  # cached, not re-read


# ---- Registry completeness ------------------------------------------------


@pytest.mark.unit
class TestRegistryCompleteness:
    """Ensure CONFIG_REGISTRY covers every dataclass field and vice versa."""

    def test_registry_covers_all_config_attributes(self):
        cfg = VaultSpecConfig()
        registry_attrs = {cv.attr_name for cv in CONFIG_REGISTRY}
        config_attrs = set(cfg.__dataclass_fields__.keys())
        assert registry_attrs == config_attrs, (
            f"Mismatch between registry and dataclass fields:\n"
            f"  In registry but not dataclass: {registry_attrs - config_attrs}\n"
            f"  In dataclass but not registry: {config_attrs - registry_attrs}"
        )

    def test_all_env_names_start_with_vaultspec(self):
        for cv in CONFIG_REGISTRY:
            assert cv.env_name.startswith("VAULTSPEC_"), (
                f"Registry entry {cv.attr_name!r} has env_name={cv.env_name!r} "
                f"which does not start with VAULTSPEC_"
            )

    def test_no_duplicate_env_names(self):
        env_names = [cv.env_name for cv in CONFIG_REGISTRY]
        assert len(env_names) == len(set(env_names)), "Duplicate env_name found"

    def test_no_duplicate_attr_names(self):
        attr_names = [cv.attr_name for cv in CONFIG_REGISTRY]
        assert len(attr_names) == len(set(attr_names)), "Duplicate attr_name found"

    def test_type_sentinels_used_correctly(self):
        """Verify sentinel types match Optional[int]/Optional[float]."""
        for cv in CONFIG_REGISTRY:
            if cv.var_type is _OptionalInt:
                # Field default should be None
                assert cv.default is None, (
                    f"{cv.attr_name} uses _OptionalInt but default is {cv.default}"
                )
            if cv.var_type is _OptionalFloat:
                assert cv.default is None, (
                    f"{cv.attr_name} uses _OptionalFloat but default is {cv.default}"
                )
