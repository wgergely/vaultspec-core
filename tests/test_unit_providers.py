from __future__ import annotations

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import json  # noqa: E402
from unittest import mock  # noqa: E402

import pytest  # noqa: E402

from agent_providers.base import (  # noqa: E402
    CapabilityLevel,
    ProcessSpec,
    resolve_includes,
    load_mcp_servers,
)
from agent_providers.gemini import GeminiProvider  # noqa: E402
from agent_providers.claude import ClaudeProvider  # noqa: E402
from acp_dispatch import get_provider_for_model  # noqa: E402


# ---------------------------------------------------------------------------
# TestSharedResolveIncludes (base.py free function)
# ---------------------------------------------------------------------------


class TestSharedResolveIncludes:
    def test_basic(self, tmp_path):
        (tmp_path / "included.md").write_text("Included content", encoding="utf-8")
        result = resolve_includes("Before\n@included.md\nAfter", tmp_path, tmp_path)
        assert "Included content" in result
        assert "Before" in result
        assert "After" in result

    def test_missing_file(self, tmp_path):
        result = resolve_includes("@nonexistent.md", tmp_path, tmp_path)
        assert "ERROR: Missing include" in result

    def test_url_passthrough(self, tmp_path):
        result = resolve_includes("@https://example.com/file.md", tmp_path, tmp_path)
        assert "@https://example.com/file.md" in result


# ---------------------------------------------------------------------------
# TestLoadMcpServers (base.py free function)
# ---------------------------------------------------------------------------


class TestLoadMcpServers:
    def test_no_settings_file(self, tmp_path):
        assert load_mcp_servers(tmp_path) == []

    def test_valid_settings(self, tmp_path):
        settings = {
            "mcpServers": {
                "rust": {"command": "rust-mcp-server", "args": [], "trust": True},
                "dispatch": {"command": "python", "args": ["mcp.py"]},
            }
        }
        (tmp_path / ".gemini").mkdir()
        (tmp_path / ".gemini" / "settings.json").write_text(
            json.dumps(settings), encoding="utf-8"
        )
        servers = load_mcp_servers(tmp_path)
        assert len(servers) == 2
        names = {s["name"] for s in servers}
        assert names == {"rust", "dispatch"}
        rust = next(s for s in servers if s["name"] == "rust")
        assert rust["command"] == "rust-mcp-server"
        assert rust["args"] == []

    def test_malformed_json(self, tmp_path):
        (tmp_path / ".gemini").mkdir()
        (tmp_path / ".gemini" / "settings.json").write_text(
            "not json", encoding="utf-8"
        )
        assert load_mcp_servers(tmp_path) == []

    def test_no_mcp_block(self, tmp_path):
        (tmp_path / ".gemini").mkdir()
        (tmp_path / ".gemini" / "settings.json").write_text(
            json.dumps({"tools": {}}), encoding="utf-8"
        )
        assert load_mcp_servers(tmp_path) == []

    def test_malformed_entry_skipped(self, tmp_path):
        settings = {
            "mcpServers": {
                "good": {"command": "cmd"},
                "bad": "not a dict",
                "missing_cmd": {"args": []},
            }
        }
        (tmp_path / ".gemini").mkdir()
        (tmp_path / ".gemini" / "settings.json").write_text(
            json.dumps(settings), encoding="utf-8"
        )
        servers = load_mcp_servers(tmp_path)
        assert len(servers) == 1
        assert servers[0]["name"] == "good"

    def test_env_passed_through(self, tmp_path):
        settings = {
            "mcpServers": {
                "srv": {"command": "cmd", "args": ["-v"], "env": {"FOO": "bar"}},
            }
        }
        (tmp_path / ".gemini").mkdir()
        (tmp_path / ".gemini" / "settings.json").write_text(
            json.dumps(settings), encoding="utf-8"
        )
        servers = load_mcp_servers(tmp_path)
        assert servers[0]["env"] == {"FOO": "bar"}


# ---------------------------------------------------------------------------
# TestGeminiProvider
# ---------------------------------------------------------------------------


class TestGeminiProvider:
    @pytest.fixture
    def provider(self):
        return GeminiProvider()

    @pytest.fixture(autouse=True)
    def _clear_version_cache(self):
        """Reset the module-level version cache before each test."""
        import agent_providers.gemini as gmod

        gmod._cached_version = None
        yield
        gmod._cached_version = None

    def test_name(self, provider):
        assert provider.name == "gemini"

    def test_supported_models(self, provider):
        models = provider.supported_models
        assert "gemini-3-pro-preview" in models
        assert "gemini-3-flash-preview" in models
        assert "gemini-2.5-pro" in models
        assert "gemini-2.5-flash" in models

    def test_capability_3_pro_is_high(self, provider):
        assert (
            provider.get_model_capability("gemini-3-pro-preview")
            == CapabilityLevel.HIGH
        )

    def test_capability_3_flash_is_medium(self, provider):
        assert (
            provider.get_model_capability("gemini-3-flash-preview")
            == CapabilityLevel.MEDIUM
        )

    def test_capability_2_5_pro_is_medium(self, provider):
        """M6 fix: gemini-2.5-pro is MEDIUM, not LOW."""
        assert provider.get_model_capability("gemini-2.5-pro") == CapabilityLevel.MEDIUM

    def test_capability_2_5_flash_is_low(self, provider):
        assert provider.get_model_capability("gemini-2.5-flash") == CapabilityLevel.LOW

    def test_best_model_high(self, provider):
        assert (
            provider.get_best_model_for_capability(CapabilityLevel.HIGH)
            == "gemini-3-pro-preview"
        )

    def test_best_model_medium(self, provider):
        assert (
            provider.get_best_model_for_capability(CapabilityLevel.MEDIUM)
            == "gemini-3-flash-preview"
        )

    def test_best_model_low(self, provider):
        """M6 fix: LOW now maps to gemini-2.5-flash (not gemini-2.5-pro)."""
        assert (
            provider.get_best_model_for_capability(CapabilityLevel.LOW)
            == "gemini-2.5-flash"
        )

    def test_no_circular_fallback(self, provider):
        """M6 fix: LOW -> flash (LOW), MEDIUM -> 3-flash (MEDIUM). No circular mapping."""
        low_model = provider.get_best_model_for_capability(CapabilityLevel.LOW)
        assert provider.get_model_capability(low_model) == CapabilityLevel.LOW
        med_model = provider.get_best_model_for_capability(CapabilityLevel.MEDIUM)
        assert provider.get_model_capability(med_model) == CapabilityLevel.MEDIUM

    def test_resolve_includes_delegates_to_shared(self, provider, tmp_path):
        (tmp_path / "included.md").write_text("Included content", encoding="utf-8")
        content = "Before\n@included.md\nAfter"
        resolved = provider.resolve_includes(content, tmp_path, tmp_path)
        assert "Included content" in resolved

    def test_prepare_process_returns_spec(self, provider, tmp_path):
        with mock.patch(
            "agent_providers.gemini.GeminiProvider.check_version",
            return_value=(0, 27, 0),
        ):
            spec = provider.prepare_process(
                agent_name="test-agent",
                agent_meta={"model": "gemini-2.5-flash"},
                agent_persona="You are a test agent.",
                task_context="Do something.",
                root_dir=tmp_path,
                model_override="gemini-2.5-flash",
            )
        assert isinstance(spec, ProcessSpec)
        assert "--experimental-acp" in spec.args
        assert "GEMINI_SYSTEM_MD" in spec.env
        assert len(spec.cleanup_paths) == 1

        # Cleanup temp file
        for p in spec.cleanup_paths:
            if p.exists():
                p.unlink()

    def test_prepare_process_sets_initial_prompt(self, provider, tmp_path):
        """M1 fix: dual delivery -- initial_prompt_override is set."""
        with mock.patch(
            "agent_providers.gemini.GeminiProvider.check_version",
            return_value=(0, 27, 0),
        ):
            spec = provider.prepare_process(
                agent_name="test-agent",
                agent_meta={},
                agent_persona="Test persona",
                task_context="Test task",
                root_dir=tmp_path,
            )
        assert spec.initial_prompt_override is not None
        assert "Test task" in spec.initial_prompt_override
        assert "Test persona" in spec.initial_prompt_override

        for p in spec.cleanup_paths:
            if p.exists():
                p.unlink()

    def test_prepare_process_loads_mcp_servers(self, provider, tmp_path):
        """H3 fix: MCP servers from .gemini/settings.json are loaded."""
        settings = {
            "mcpServers": {
                "rust": {"command": "rust-mcp-server", "args": []},
            }
        }
        (tmp_path / ".gemini").mkdir()
        (tmp_path / ".gemini" / "settings.json").write_text(
            json.dumps(settings), encoding="utf-8"
        )

        with mock.patch(
            "agent_providers.gemini.GeminiProvider.check_version",
            return_value=(0, 27, 0),
        ):
            spec = provider.prepare_process(
                agent_name="test-agent",
                agent_meta={},
                agent_persona="Test persona",
                task_context="Test task",
                root_dir=tmp_path,
            )
        assert len(spec.mcp_servers) == 1
        assert spec.mcp_servers[0]["name"] == "rust"

        for p in spec.cleanup_paths:
            if p.exists():
                p.unlink()

    def test_system_prompt_persona_first(self, provider):
        """M5 fix: prompt ordering is persona-first, rules-second."""
        prompt = provider.construct_system_prompt("I am a persona", "These are rules")
        persona_pos = prompt.index("AGENT PERSONA")
        rules_pos = prompt.index("SYSTEM RULES")
        assert persona_pos < rules_pos


# ---------------------------------------------------------------------------
# TestGeminiVersionCheck
# ---------------------------------------------------------------------------


class TestGeminiVersionCheck:
    @pytest.fixture(autouse=True)
    def _clear_version_cache(self):
        import agent_providers.gemini as gmod

        gmod._cached_version = None
        yield
        gmod._cached_version = None

    def test_parse_version_output(self):
        result = mock.MagicMock()
        result.stdout = "Gemini CLI v0.27.0"
        result.stderr = ""
        with mock.patch("agent_providers.gemini.subprocess.run", return_value=result):
            version = GeminiProvider.check_version("gemini")
        assert version == (0, 27, 0)

    def test_parse_bare_version(self):
        result = mock.MagicMock()
        result.stdout = "0.28.1"
        result.stderr = ""
        with mock.patch("agent_providers.gemini.subprocess.run", return_value=result):
            version = GeminiProvider.check_version("gemini")
        assert version == (0, 28, 1)

    def test_version_cached(self):
        result = mock.MagicMock()
        result.stdout = "v0.27.0"
        result.stderr = ""
        with mock.patch(
            "agent_providers.gemini.subprocess.run", return_value=result
        ) as mock_run:
            v1 = GeminiProvider.check_version("gemini")
            v2 = GeminiProvider.check_version("gemini")
        assert v1 == v2
        mock_run.assert_called_once()

    def test_version_below_recommended_warns(self):
        result = mock.MagicMock()
        result.stdout = "v0.20.0"
        result.stderr = ""
        with mock.patch("agent_providers.gemini.subprocess.run", return_value=result):
            with mock.patch("agent_providers.gemini.logger.warning") as mock_warn:
                version = GeminiProvider.check_version("gemini")
        assert version == (0, 20, 0)
        mock_warn.assert_called()

    def test_version_below_windows_min_raises(self):
        result = mock.MagicMock()
        result.stdout = "v0.8.0"
        result.stderr = ""
        with mock.patch("agent_providers.gemini.subprocess.run", return_value=result):
            with mock.patch("agent_providers.gemini.sys") as mock_sys:
                mock_sys.platform = "win32"
                with pytest.raises(RuntimeError, match="below minimum"):
                    GeminiProvider.check_version("gemini")

    def test_executable_not_found(self):
        with mock.patch(
            "agent_providers.gemini.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            version = GeminiProvider.check_version("gemini")
        assert version is None

    def test_timeout(self):
        import subprocess as sp

        with mock.patch(
            "agent_providers.gemini.subprocess.run",
            side_effect=sp.TimeoutExpired(cmd="gemini --version", timeout=10),
        ):
            version = GeminiProvider.check_version("gemini")
        assert version is None

    def test_unparseable_output(self):
        result = mock.MagicMock()
        result.stdout = "unknown output"
        result.stderr = ""
        with mock.patch("agent_providers.gemini.subprocess.run", return_value=result):
            version = GeminiProvider.check_version("gemini")
        assert version is None


# ---------------------------------------------------------------------------
# TestClaudeProvider
# ---------------------------------------------------------------------------


class TestClaudeProvider:
    @pytest.fixture
    def provider(self):
        return ClaudeProvider()

    def test_name(self, provider):
        assert provider.name == "claude"

    def test_supported_models(self, provider):
        models = provider.supported_models
        assert "claude-opus-4-6" in models
        assert "claude-sonnet-4-5" in models
        assert "claude-haiku-4-5" in models

    def test_capability_opus_is_high(self, provider):
        assert provider.get_model_capability("claude-opus-4-6") == CapabilityLevel.HIGH

    def test_capability_sonnet_is_medium(self, provider):
        assert (
            provider.get_model_capability("claude-sonnet-4-5") == CapabilityLevel.MEDIUM
        )

    def test_capability_haiku_is_low(self, provider):
        assert provider.get_model_capability("claude-haiku-4-5") == CapabilityLevel.LOW

    def test_capability_unknown_defaults_medium(self, provider):
        assert (
            provider.get_model_capability("claude-unknown-42") == CapabilityLevel.MEDIUM
        )

    def test_best_model_high(self, provider):
        assert (
            provider.get_best_model_for_capability(CapabilityLevel.HIGH)
            == "claude-opus-4-6"
        )

    def test_best_model_medium(self, provider):
        assert (
            provider.get_best_model_for_capability(CapabilityLevel.MEDIUM)
            == "claude-sonnet-4-5"
        )

    def test_best_model_low(self, provider):
        assert (
            provider.get_best_model_for_capability(CapabilityLevel.LOW)
            == "claude-haiku-4-5"
        )

    def test_resolve_includes_delegates_to_shared(self, provider, tmp_path):
        (tmp_path / "included.md").write_text("Included content", encoding="utf-8")
        resolved = provider.resolve_includes("@included.md", tmp_path, tmp_path)
        assert "Included content" in resolved

    def test_prepare_process_uses_npx(self, provider, tmp_path):
        spec = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"model": "claude-haiku-4-5"},
            agent_persona="You are a test agent.",
            task_context="Do something.",
            root_dir=tmp_path,
            model_override="claude-haiku-4-5",
        )
        assert isinstance(spec, ProcessSpec)
        assert "@zed-industries/claude-code-acp" in spec.args

    def test_prepare_process_sets_session_meta(self, provider, tmp_path):
        spec = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={},
            agent_persona="Test persona",
            task_context="Test task",
            root_dir=tmp_path,
        )
        assert "systemPrompt" in spec.session_meta

    def test_prepare_process_sets_initial_prompt(self, provider, tmp_path):
        spec = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={},
            agent_persona="Test persona",
            task_context="Test task",
            root_dir=tmp_path,
        )
        assert spec.initial_prompt_override is not None
        assert "Test task" in spec.initial_prompt_override
        assert "Test persona" in spec.initial_prompt_override

    def test_system_prompt_persona_first(self, provider):
        """M5 fix: Claude prompt ordering is persona-first, rules-second."""
        prompt = provider.construct_system_prompt("I am a persona", "These are rules")
        persona_pos = prompt.index("AGENT PERSONA")
        rules_pos = prompt.index("SYSTEM RULES")
        assert persona_pos < rules_pos


# ---------------------------------------------------------------------------
# TestPromptOrderingConsistency
# ---------------------------------------------------------------------------


class TestPromptOrderingConsistency:
    """M5 fix: Both providers should use the same prompt ordering."""

    def test_same_ordering(self):
        gemini = GeminiProvider()
        claude = ClaudeProvider()
        g_prompt = gemini.construct_system_prompt("persona", "rules")
        c_prompt = claude.construct_system_prompt("persona", "rules")
        assert g_prompt == c_prompt


# ---------------------------------------------------------------------------
# TestProcessSpecMcpServers
# ---------------------------------------------------------------------------


class TestProcessSpecMcpServers:
    def test_default_empty(self):
        spec = ProcessSpec(executable="test", args=[], env={}, cleanup_paths=[])
        assert spec.mcp_servers == []

    def test_populated(self):
        servers = [
            {"name": "rust", "command": "rust-mcp-server", "args": [], "env": {}}
        ]
        spec = ProcessSpec(
            executable="test",
            args=[],
            env={},
            cleanup_paths=[],
            mcp_servers=servers,
        )
        assert len(spec.mcp_servers) == 1
        assert spec.mcp_servers[0]["name"] == "rust"


# ---------------------------------------------------------------------------
# TestGetProviderForModel
# ---------------------------------------------------------------------------


class TestGetProviderForModel:
    def test_none_returns_gemini(self):
        provider = get_provider_for_model(None)
        assert provider.name == "gemini"

    def test_gemini_model_returns_gemini(self):
        provider = get_provider_for_model("gemini-3-pro-preview")
        assert provider.name == "gemini"

    def test_gemini_flash_returns_gemini(self):
        provider = get_provider_for_model("gemini-2.5-flash")
        assert provider.name == "gemini"

    def test_claude_model_returns_claude(self):
        provider = get_provider_for_model("claude-opus-4-6")
        assert provider.name == "claude"

    def test_claude_haiku_returns_claude(self):
        provider = get_provider_for_model("claude-haiku-4-5")
        assert provider.name == "claude"

    def test_unknown_returns_gemini_fallback(self):
        provider = get_provider_for_model("unknown-model-xyz")
        assert provider.name == "gemini"
