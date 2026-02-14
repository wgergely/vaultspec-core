from __future__ import annotations

import json
from unittest import mock

import pytest

from orchestration.dispatch import get_provider_for_model
from protocol.providers.base import (
    CapabilityLevel,
    ClaudeModels,
    GeminiModels,
    ProcessSpec,
    load_mcp_servers,
    resolve_includes,
)
from protocol.providers.claude import ClaudeProvider
from protocol.providers.gemini import GeminiProvider

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
                "rust": {
                    "command": "rust-mcp-server",
                    "args": [],
                    "trust": True,
                },
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
                "srv": {
                    "command": "cmd",
                    "args": ["-v"],
                    "env": {"FOO": "bar"},
                },
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
        from protocol.providers import gemini as gmod

        gmod._cached_version = None
        yield
        gmod._cached_version = None

    def test_name(self, provider):
        assert provider.name == "gemini"

    def test_supported_models(self, provider):
        models = provider.supported_models
        assert GeminiModels.LOW in models
        assert GeminiModels.HIGH in models

    def test_capability_pro_is_high(self, provider):
        assert provider.get_model_capability(GeminiModels.HIGH) == CapabilityLevel.HIGH

    def test_capability_flash_is_low(self, provider):
        cap = provider.get_model_capability(GeminiModels.LOW)
        assert cap == CapabilityLevel.LOW

    def test_best_model_high(self, provider):
        assert (
            provider.get_best_model_for_capability(CapabilityLevel.HIGH)
            == GeminiModels.HIGH
        )

    def test_best_model_low(self, provider):
        assert (
            provider.get_best_model_for_capability(CapabilityLevel.LOW)
            == GeminiModels.LOW
        )

    def test_no_circular_fallback(self, provider):
        low_model = provider.get_best_model_for_capability(CapabilityLevel.LOW)
        assert provider.get_model_capability(low_model) == CapabilityLevel.LOW
        high_model = provider.get_best_model_for_capability(CapabilityLevel.HIGH)
        assert provider.get_model_capability(high_model) == CapabilityLevel.HIGH

    def test_prepare_process_returns_spec(self, provider, tmp_path):
        with mock.patch(
            "protocol.providers.gemini.GeminiProvider.check_version",
            return_value=(0, 27, 0),
        ):
            spec = provider.prepare_process(
                agent_name="test-agent",
                agent_meta={"model": GeminiModels.LOW},
                agent_persona="You are a test agent.",
                task_context="Do something.",
                root_dir=tmp_path,
                model_override=GeminiModels.LOW,
            )
        assert isinstance(spec, ProcessSpec)
        assert "--experimental-acp" in spec.args
        assert "--system" in spec.args
        assert len(spec.cleanup_paths) == 1

        # Cleanup temp file
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
        from protocol.providers import gemini as gmod

        gmod._cached_version = None
        yield
        gmod._cached_version = None

    def test_parse_version_output(self):
        result = mock.MagicMock()
        result.stdout = "gemini v0.27.0"
        result.stderr = ""
        target = "protocol.providers.gemini.subprocess.run"
        with mock.patch(target, return_value=result):
            version = GeminiProvider.check_version("gemini")
        assert version == (0, 27, 0)

    def test_version_cached(self):
        result = mock.MagicMock()
        result.stdout = "gemini v0.27.0"
        result.stderr = ""
        target = "protocol.providers.gemini.subprocess.run"
        with mock.patch(target, return_value=result) as mock_run:
            v1 = GeminiProvider.check_version("gemini")
            v2 = GeminiProvider.check_version("gemini")
        assert v1 == v2
        mock_run.assert_called_once()

    def test_executable_not_found(self):
        with mock.patch(
            "protocol.providers.gemini.subprocess.run",
            side_effect=FileNotFoundError,
        ):
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
        assert ClaudeModels.MEDIUM in models
        assert ClaudeModels.HIGH in models

    def test_capability_opus_is_high(self, provider):
        assert provider.get_model_capability(ClaudeModels.HIGH) == CapabilityLevel.HIGH

    def test_capability_sonnet_is_medium(self, provider):
        assert (
            provider.get_model_capability(ClaudeModels.MEDIUM) == CapabilityLevel.MEDIUM
        )

    def test_best_model_high(self, provider):
        assert (
            provider.get_best_model_for_capability(CapabilityLevel.HIGH)
            == ClaudeModels.HIGH
        )

    def test_best_model_medium(self, provider):
        assert (
            provider.get_best_model_for_capability(CapabilityLevel.MEDIUM)
            == ClaudeModels.MEDIUM
        )

    def test_best_model_low(self, provider):
        assert (
            provider.get_best_model_for_capability(CapabilityLevel.LOW)
            == ClaudeModels.LOW
        )

    def test_prepare_process_returns_spec(self, provider, tmp_path):
        spec = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"model": ClaudeModels.MEDIUM},
            agent_persona="You are a test agent.",
            task_context="Do something.",
            root_dir=tmp_path,
            model_override=ClaudeModels.MEDIUM,
        )
        assert isinstance(spec, ProcessSpec)
        assert "mcp" in spec.args
        assert "serve" in spec.args


# ---------------------------------------------------------------------------
# TestGetProviderForModel
# ---------------------------------------------------------------------------


class TestGetProviderForModel:
    def test_none_returns_gemini(self):
        provider = get_provider_for_model(None)
        assert provider.name == "gemini"

    def test_gemini_model_returns_gemini(self):
        # The logic in get_provider_for_model currently defaults to gemini
        # for unknown or None models.
        provider = get_provider_for_model(GeminiModels.LOW)
        assert provider.name == "gemini"
