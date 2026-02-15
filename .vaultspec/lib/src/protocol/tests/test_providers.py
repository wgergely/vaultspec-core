from __future__ import annotations

from unittest import mock

import pytest

from orchestration.subagent import get_provider_for_model
from protocol.providers.base import (
    CapabilityLevel,
    ClaudeModels,
    GeminiModels,
    ProcessSpec,
    resolve_includes,
)
from protocol.providers.claude import ClaudeProvider
from protocol.providers.gemini import GeminiProvider

pytestmark = [pytest.mark.unit]

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
        assert "--system" not in spec.args
        assert spec.initial_prompt_override == "Do something."
        # System prompt delivered via GEMINI_SYSTEM_MD temp file
        assert len(spec.cleanup_paths) == 1
        assert spec.env.get("GEMINI_SYSTEM_MD")
        system_content = spec.cleanup_paths[0].read_text(encoding="utf-8")
        assert "AGENT PERSONA" in system_content

    def test_prepare_process_includes_system_md(self, provider, tmp_path):
        """SYSTEM.md content goes to GEMINI_SYSTEM_MD temp file."""
        system_dir = tmp_path / ".gemini"
        system_dir.mkdir()
        (system_dir / "SYSTEM.md").write_text(
            "You must always respond in French.",
            encoding="utf-8",
        )
        with mock.patch(
            "protocol.providers.gemini.GeminiProvider.check_version",
            return_value=(0, 27, 0),
        ):
            spec = provider.prepare_process(
                agent_name="test-agent",
                agent_meta={"model": GeminiModels.LOW},
                agent_persona="You are Jean-Claude.",
                task_context="Bake croissants.",
                root_dir=tmp_path,
                model_override=GeminiModels.LOW,
            )
        # Task is passed directly, not mixed with system prompt
        assert spec.initial_prompt_override == "Bake croissants."
        # System prompt written to temp file referenced by env var
        assert len(spec.cleanup_paths) == 1
        sys_file = spec.cleanup_paths[0]
        assert spec.env["GEMINI_SYSTEM_MD"] == str(sys_file)
        content = sys_file.read_text(encoding="utf-8")
        assert "SYSTEM INSTRUCTIONS" in content
        assert "respond in French" in content
        assert "AGENT PERSONA" in content
        assert "Jean-Claude" in content
        assert content.index("SYSTEM INSTRUCTIONS") < content.index("AGENT PERSONA")

    def test_prepare_process_no_system_md(self, provider, tmp_path):
        """Without SYSTEM.md, system file has persona but no system instructions."""
        with mock.patch(
            "protocol.providers.gemini.GeminiProvider.check_version",
            return_value=(0, 27, 0),
        ):
            spec = provider.prepare_process(
                agent_name="test-agent",
                agent_meta={"model": GeminiModels.LOW},
                agent_persona="You are Jean-Claude.",
                task_context="Bake croissants.",
                root_dir=tmp_path,
                model_override=GeminiModels.LOW,
            )
        assert spec.initial_prompt_override == "Bake croissants."
        content = spec.cleanup_paths[0].read_text(encoding="utf-8")
        assert "SYSTEM INSTRUCTIONS" not in content
        assert "AGENT PERSONA" in content

    def test_system_prompt_ordering(self, provider):
        """Prompt ordering: system instructions → persona → rules."""
        prompt = provider.construct_system_prompt(
            "I am a persona",
            "These are rules",
            "These are instructions",
        )
        instr_pos = prompt.index("SYSTEM INSTRUCTIONS")
        persona_pos = prompt.index("AGENT PERSONA")
        rules_pos = prompt.index("SYSTEM RULES")
        assert instr_pos < persona_pos < rules_pos


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
        assert "-m" in spec.args
        assert "protocol.acp.claude_bridge" in spec.args


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


# ---------------------------------------------------------------------------
# TestGeminiSandboxFlag — Phase 1: --sandbox flag in read-only mode
# ---------------------------------------------------------------------------


class TestGeminiSandboxFlag:
    """Verify GeminiProvider passes --sandbox when mode='read-only'."""

    @pytest.fixture
    def provider(self):
        return GeminiProvider()

    @pytest.fixture(autouse=True)
    def _clear_version_cache(self):
        from protocol.providers import gemini as gmod

        gmod._cached_version = None
        yield
        gmod._cached_version = None

    def test_gemini_sandbox_flag_readonly(self, provider, tmp_path):
        """prepare_process(..., mode='read-only') includes --sandbox in args."""
        with mock.patch(
            "protocol.providers.gemini.GeminiProvider.check_version",
            return_value=(0, 27, 0),
        ):
            spec = provider.prepare_process(
                agent_name="test-agent",
                agent_meta={"model": GeminiModels.LOW},
                agent_persona="You are a test agent.",
                task_context="Analyze code.",
                root_dir=tmp_path,
                model_override=GeminiModels.LOW,
                mode="read-only",
            )
        assert "--sandbox" in spec.args

    def test_gemini_no_sandbox_flag_readwrite(self, provider, tmp_path):
        """prepare_process(..., mode='read-write') does NOT include --sandbox."""
        with mock.patch(
            "protocol.providers.gemini.GeminiProvider.check_version",
            return_value=(0, 27, 0),
        ):
            spec = provider.prepare_process(
                agent_name="test-agent",
                agent_meta={"model": GeminiModels.LOW},
                agent_persona="You are a test agent.",
                task_context="Build feature.",
                root_dir=tmp_path,
                model_override=GeminiModels.LOW,
                mode="read-write",
            )
        assert "--sandbox" not in spec.args


# ---------------------------------------------------------------------------
# TestClaudeModePassthrough — Phase 1: mode doesn't change Claude args
# ---------------------------------------------------------------------------


class TestClaudeModePassthrough:
    """Verify ClaudeProvider prepare_process handles mode parameter correctly."""

    @pytest.fixture
    def provider(self):
        return ClaudeProvider()

    def test_claude_mode_passthrough(self, provider, tmp_path):
        """prepare_process(..., mode='read-only') doesn't change Claude args."""
        spec_rw = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"model": ClaudeModels.MEDIUM},
            agent_persona="You are a test agent.",
            task_context="Do something.",
            root_dir=tmp_path,
            model_override=ClaudeModels.MEDIUM,
            mode="read-write",
        )
        spec_ro = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"model": ClaudeModels.MEDIUM},
            agent_persona="You are a test agent.",
            task_context="Do something.",
            root_dir=tmp_path,
            model_override=ClaudeModels.MEDIUM,
            mode="read-only",
        )
        # Claude bridge args should be identical regardless of mode
        # (sandbox is handled in the bridge itself, not in CLI args)
        assert spec_rw.args == spec_ro.args
        assert "--sandbox" not in spec_ro.args

    def test_prepare_process_mode_default(self, provider, tmp_path):
        """Default mode is 'read-write' (no mode keyword)."""
        spec = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"model": ClaudeModels.MEDIUM},
            agent_persona="You are a test agent.",
            task_context="Do something.",
            root_dir=tmp_path,
            model_override=ClaudeModels.MEDIUM,
        )
        # Should succeed without error and produce valid args
        assert isinstance(spec, ProcessSpec)
        assert "-m" in spec.args


# ---------------------------------------------------------------------------
# TestClaudeFeaturePassthrough — Phase 5: env vars from agent_meta
# ---------------------------------------------------------------------------


class TestClaudeFeaturePassthrough:
    """Verify ClaudeProvider sets VS_* env vars from agent_meta fields."""

    @pytest.fixture
    def provider(self):
        return ClaudeProvider()

    def test_max_turns_env(self, provider, tmp_path):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={"model": ClaudeModels.MEDIUM, "max_turns": "25"},
            agent_persona="",
            task_context="Do it.",
            root_dir=tmp_path,
        )
        assert spec.env["VS_MAX_TURNS"] == "25"

    def test_budget_env(self, provider, tmp_path):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={"model": ClaudeModels.MEDIUM, "budget": "1.5"},
            agent_persona="",
            task_context="Do it.",
            root_dir=tmp_path,
        )
        assert spec.env["VS_BUDGET_USD"] == "1.5"

    def test_allowed_tools_env(self, provider, tmp_path):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={
                "model": ClaudeModels.MEDIUM,
                "allowed_tools": "Glob, Read",
            },
            agent_persona="",
            task_context="Do it.",
            root_dir=tmp_path,
        )
        assert spec.env["VS_ALLOWED_TOOLS"] == "Glob, Read"

    def test_disallowed_tools_env(self, provider, tmp_path):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={
                "model": ClaudeModels.MEDIUM,
                "disallowed_tools": "Bash",
            },
            agent_persona="",
            task_context="Do it.",
            root_dir=tmp_path,
        )
        assert spec.env["VS_DISALLOWED_TOOLS"] == "Bash"

    def test_effort_env(self, provider, tmp_path):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={"model": ClaudeModels.MEDIUM, "effort": "high"},
            agent_persona="",
            task_context="Do it.",
            root_dir=tmp_path,
        )
        assert spec.env["VS_EFFORT"] == "high"

    def test_fallback_model_env(self, provider, tmp_path):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={
                "model": ClaudeModels.MEDIUM,
                "fallback_model": "claude-haiku-4-5",
            },
            agent_persona="",
            task_context="Do it.",
            root_dir=tmp_path,
        )
        assert spec.env["VS_FALLBACK_MODEL"] == "claude-haiku-4-5"

    def test_include_dirs_env(self, provider, tmp_path):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={
                "model": ClaudeModels.MEDIUM,
                "include_dirs": ".vault, src",
            },
            agent_persona="",
            task_context="Do it.",
            root_dir=tmp_path,
        )
        assert spec.env["VS_INCLUDE_DIRS"] == ".vault, src"

    def test_output_format_env(self, provider, tmp_path):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={
                "model": ClaudeModels.MEDIUM,
                "output_format": "json",
            },
            agent_persona="",
            task_context="Do it.",
            root_dir=tmp_path,
        )
        assert spec.env["VS_OUTPUT_FORMAT"] == "json"

    def test_empty_meta_no_env_vars(self, provider, tmp_path):
        """Empty agent_meta should not set any VS_* feature env vars."""
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={"model": ClaudeModels.MEDIUM},
            agent_persona="",
            task_context="Do it.",
            root_dir=tmp_path,
        )
        for key in (
            "VS_MAX_TURNS",
            "VS_BUDGET_USD",
            "VS_ALLOWED_TOOLS",
            "VS_DISALLOWED_TOOLS",
            "VS_EFFORT",
            "VS_OUTPUT_FORMAT",
            "VS_FALLBACK_MODEL",
            "VS_INCLUDE_DIRS",
        ):
            assert key not in spec.env


# ---------------------------------------------------------------------------
# TestGeminiFeaturePassthrough — Phase 5: CLI flags from agent_meta
# ---------------------------------------------------------------------------


class TestGeminiFeaturePassthrough:
    """Verify GeminiProvider adds CLI flags from agent_meta fields."""

    @pytest.fixture
    def provider(self):
        return GeminiProvider()

    @pytest.fixture(autouse=True)
    def _clear_version_cache(self):
        from protocol.providers import gemini as gmod

        gmod._cached_version = None
        yield
        gmod._cached_version = None

    def _make_spec(self, provider, tmp_path, **extra_meta):
        meta = {"model": GeminiModels.LOW, **extra_meta}
        with mock.patch(
            "protocol.providers.gemini.GeminiProvider.check_version",
            return_value=(0, 27, 0),
        ):
            return provider.prepare_process(
                agent_name="test",
                agent_meta=meta,
                agent_persona="",
                task_context="Do it.",
                root_dir=tmp_path,
            )

    def test_allowed_tools_flags(self, provider, tmp_path):
        spec = self._make_spec(provider, tmp_path, allowed_tools="Glob, Read")
        assert "--allowed-tools" in spec.args
        idx = spec.args.index("--allowed-tools")
        assert spec.args[idx + 1] == "Glob"
        # Second occurrence
        remaining = spec.args[idx + 2 :]
        assert "--allowed-tools" in remaining
        idx2 = remaining.index("--allowed-tools")
        assert remaining[idx2 + 1] == "Read"

    def test_approval_mode_flag(self, provider, tmp_path):
        spec = self._make_spec(provider, tmp_path, approval_mode="yolo")
        assert "--approval-mode" in spec.args
        idx = spec.args.index("--approval-mode")
        assert spec.args[idx + 1] == "yolo"

    def test_approval_mode_default_not_added(self, provider, tmp_path):
        spec = self._make_spec(provider, tmp_path, approval_mode="default")
        assert "--approval-mode" not in spec.args

    def test_output_format_flag(self, provider, tmp_path):
        spec = self._make_spec(provider, tmp_path, output_format="json")
        assert "--output-format" in spec.args
        idx = spec.args.index("--output-format")
        assert spec.args[idx + 1] == "json"

    def test_output_format_text_not_added(self, provider, tmp_path):
        spec = self._make_spec(provider, tmp_path, output_format="text")
        assert "--output-format" not in spec.args

    def test_include_directories_flags(self, provider, tmp_path):
        spec = self._make_spec(provider, tmp_path, include_dirs=".vault, src")
        assert "--include-directories" in spec.args
        idx = spec.args.index("--include-directories")
        assert spec.args[idx + 1] == ".vault"

    def test_empty_meta_no_extra_flags(self, provider, tmp_path):
        spec = self._make_spec(provider, tmp_path)
        for flag in (
            "--allowed-tools",
            "--approval-mode",
            "--output-format",
            "--include-directories",
        ):
            assert flag not in spec.args
