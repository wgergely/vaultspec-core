from __future__ import annotations

import datetime
import inspect
import json
import logging
import subprocess

import pytest

from tests.constants import TEST_PROJECT

from ...orchestration import get_provider_for_model
from ..providers import (
    AgentProvider,
    CapabilityLevel,
    ClaudeModels,
    ClaudeProvider,
    GeminiModels,
    GeminiProvider,
    ProcessSpec,
    resolve_includes,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _isolate_gemini_oauth(tmp_path):
    """Provide fake valid OAuth creds so unit tests never hit real ~/.gemini/.

    Uses the same module-level DI pattern as ``_which_fn`` / ``_cached_version``.
    The token expiry is 1 h in the future, so the auth path sees "valid, no
    refresh needed" and never touches the network.
    """
    from ..providers import gemini as gmod

    creds_file = tmp_path / "oauth_creds.json"
    now_ms = int(datetime.datetime.now(datetime.UTC).timestamp() * 1000)
    creds_file.write_text(
        json.dumps(
            {
                "access_token": "ya29.fake-unit-test-token",
                "refresh_token": "1//fake-refresh",
                "expiry_date": now_ms + 3_600_000,
                "token_type": "Bearer",
            }
        ),
        encoding="utf-8",
    )
    gmod._default_creds_path = creds_file
    yield
    gmod._default_creds_path = None


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


class TestGeminiProvider:
    @pytest.fixture
    def provider(self):
        return GeminiProvider()

    @pytest.fixture(autouse=True)
    def _seed_version_cache(self):
        """Pre-seed the module-level version cache to skip real subprocess."""
        from ..providers import gemini as gmod

        gmod._cached_version = (0, 27, 0)
        yield
        gmod._cached_version = None

    def test_name(self, provider):
        assert provider.name == "gemini"

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

    def test_prepare_process_returns_spec(self, provider):
        spec = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"model": GeminiModels.LOW},
            agent_persona="You are a test agent.",
            task_context="Do something.",
            root_dir=TEST_PROJECT,
            model_override=GeminiModels.LOW,
        )
        assert isinstance(spec, ProcessSpec)
        assert "-m" in spec.args
        assert "vaultspec.protocol.acp.gemini_bridge" in spec.args
        assert spec.initial_prompt_override == "Do something."
        # System prompt delivered via GEMINI_SYSTEM_MD temp file
        assert len(spec.cleanup_paths) == 1
        assert spec.env.get("GEMINI_SYSTEM_MD")
        system_content = spec.cleanup_paths[0].read_text(encoding="utf-8")
        assert "AGENT PERSONA" in system_content
        # Bridge config env vars
        assert spec.env["VAULTSPEC_ROOT_DIR"] == str(TEST_PROJECT)
        assert spec.env["VAULTSPEC_AGENT_MODE"] == "read-write"

    def test_prepare_process_includes_system_md(self, provider, tmp_path):
        """SYSTEM.md content goes to GEMINI_SYSTEM_MD temp file."""
        system_dir = tmp_path / ".gemini"
        system_dir.mkdir()
        (system_dir / "SYSTEM.md").write_text(
            "You must always respond in French.",
            encoding="utf-8",
        )
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

    def test_prepare_process_no_system_md(self, provider):
        """Without SYSTEM.md, system file has persona but no system instructions."""
        spec = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"model": GeminiModels.LOW},
            agent_persona="You are Jean-Claude.",
            task_context="Bake croissants.",
            root_dir=TEST_PROJECT,
            model_override=GeminiModels.LOW,
        )
        assert spec.initial_prompt_override == "Bake croissants."
        content = spec.cleanup_paths[0].read_text(encoding="utf-8")
        assert "SYSTEM INSTRUCTIONS" not in content
        assert "AGENT PERSONA" in content

    def test_system_prompt_ordering(self, provider):
        """Prompt ordering: system instructions -> persona -> rules."""
        prompt = provider.construct_system_prompt(
            "I am a persona",
            "These are rules",
            "These are instructions",
        )
        instr_pos = prompt.index("SYSTEM INSTRUCTIONS")
        persona_pos = prompt.index("AGENT PERSONA")
        rules_pos = prompt.index("SYSTEM RULES")
        assert instr_pos < persona_pos < rules_pos


class TestGeminiVersionCheck:
    @pytest.fixture(autouse=True)
    def _clear_version_cache(self):
        from ..providers import gemini as gmod

        gmod._cached_version = None
        yield
        gmod._cached_version = None

    def test_parse_version_output(self):
        result = subprocess.CompletedProcess(
            args=["gemini", "--version"],
            returncode=0,
            stdout="gemini v0.27.0",
            stderr="",
        )
        version = GeminiProvider.check_version(
            "gemini", run_fn=lambda *_a, **_kw: result
        )
        assert version == (0, 27, 0)

    def test_version_cached(self):
        call_count = 0

        def counting_run(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return subprocess.CompletedProcess(
                args=["gemini", "--version"],
                returncode=0,
                stdout="gemini v0.27.0",
                stderr="",
            )

        v1 = GeminiProvider.check_version("gemini", run_fn=counting_run)
        v2 = GeminiProvider.check_version("gemini", run_fn=counting_run)
        assert v1 == v2
        assert call_count == 1

    def test_executable_not_found(self):
        def raise_fnf(*_args, **_kwargs):
            raise FileNotFoundError

        version = GeminiProvider.check_version("gemini", run_fn=raise_fnf)
        assert version is None


class TestClaudeProvider:
    @pytest.fixture
    def provider(self):
        return ClaudeProvider()

    def test_name(self, provider):
        assert provider.name == "claude"

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

    def test_prepare_process_returns_spec(self, provider):
        spec = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"model": ClaudeModels.MEDIUM},
            agent_persona="You are a test agent.",
            task_context="Do something.",
            root_dir=TEST_PROJECT,
            model_override=ClaudeModels.MEDIUM,
        )
        assert isinstance(spec, ProcessSpec)
        assert "-m" in spec.args
        assert "vaultspec.protocol.acp.claude_bridge" in spec.args


class TestGetProviderForModel:
    def test_none_returns_gemini(self):
        provider = get_provider_for_model(None)
        assert provider.name == "gemini"

    def test_gemini_model_returns_gemini(self):
        # The logic in get_provider_for_model currently defaults to gemini
        # for unknown or None models.
        provider = get_provider_for_model(GeminiModels.LOW)
        assert provider.name == "gemini"


class TestGeminiSandboxFlag:
    """Verify GeminiProvider passes --sandbox when mode='read-only'."""

    @pytest.fixture
    def provider(self):
        return GeminiProvider()

    @pytest.fixture(autouse=True)
    def _seed_version_cache(self):
        from ..providers import gemini as gmod

        gmod._cached_version = (0, 27, 0)
        yield
        gmod._cached_version = None

    def test_gemini_sandbox_flag_readonly(self, provider):
        """prepare_process(..., mode='read-only') sets VAULTSPEC_AGENT_MODE."""
        spec = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"model": GeminiModels.LOW},
            agent_persona="You are a test agent.",
            task_context="Analyze code.",
            root_dir=TEST_PROJECT,
            model_override=GeminiModels.LOW,
            mode="read-only",
        )
        assert spec.env["VAULTSPEC_AGENT_MODE"] == "read-only"

    def test_gemini_no_sandbox_flag_readwrite(self, provider):
        """prepare_process(..., mode='read-write') sets VAULTSPEC_AGENT_MODE."""
        spec = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"model": GeminiModels.LOW},
            agent_persona="You are a test agent.",
            task_context="Build feature.",
            root_dir=TEST_PROJECT,
            model_override=GeminiModels.LOW,
            mode="read-write",
        )
        assert spec.env["VAULTSPEC_AGENT_MODE"] == "read-write"


class TestClaudeModePassthrough:
    """Verify ClaudeProvider prepare_process handles mode parameter correctly."""

    @pytest.fixture
    def provider(self):
        return ClaudeProvider()

    def test_claude_mode_passthrough(self, provider):
        """prepare_process(..., mode='read-only') doesn't change Claude args."""
        spec_rw = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"model": ClaudeModels.MEDIUM},
            agent_persona="You are a test agent.",
            task_context="Do something.",
            root_dir=TEST_PROJECT,
            model_override=ClaudeModels.MEDIUM,
            mode="read-write",
        )
        spec_ro = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"model": ClaudeModels.MEDIUM},
            agent_persona="You are a test agent.",
            task_context="Do something.",
            root_dir=TEST_PROJECT,
            model_override=ClaudeModels.MEDIUM,
            mode="read-only",
        )
        # Claude bridge args should be identical regardless of mode
        # (sandbox is handled in the bridge itself, not in CLI args)
        assert spec_rw.args == spec_ro.args
        assert "--sandbox" not in spec_ro.args

    def test_prepare_process_mode_default(self, provider):
        """Default mode is 'read-write' (no mode keyword)."""
        spec = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"model": ClaudeModels.MEDIUM},
            agent_persona="You are a test agent.",
            task_context="Do something.",
            root_dir=TEST_PROJECT,
            model_override=ClaudeModels.MEDIUM,
        )
        # Should succeed without error and produce valid args
        assert isinstance(spec, ProcessSpec)
        assert "-m" in spec.args


class TestClaudeFeaturePassthrough:
    """Verify ClaudeProvider sets VAULTSPEC_* env vars from agent_meta fields."""

    @pytest.fixture
    def provider(self):
        return ClaudeProvider()

    def test_max_turns_env(self, provider):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={"model": ClaudeModels.MEDIUM, "max_turns": "25"},
            agent_persona="",
            task_context="Do it.",
            root_dir=TEST_PROJECT,
        )
        assert spec.env["VAULTSPEC_MAX_TURNS"] == "25"

    def test_budget_env(self, provider):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={"model": ClaudeModels.MEDIUM, "budget": "1.5"},
            agent_persona="",
            task_context="Do it.",
            root_dir=TEST_PROJECT,
        )
        assert spec.env["VAULTSPEC_BUDGET_USD"] == "1.5"

    def test_allowed_tools_env(self, provider):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={
                "model": ClaudeModels.MEDIUM,
                "allowed_tools": "Glob, Read",
            },
            agent_persona="",
            task_context="Do it.",
            root_dir=TEST_PROJECT,
        )
        assert spec.env["VAULTSPEC_ALLOWED_TOOLS"] == "Glob, Read"

    def test_disallowed_tools_env(self, provider):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={
                "model": ClaudeModels.MEDIUM,
                "disallowed_tools": "Bash",
            },
            agent_persona="",
            task_context="Do it.",
            root_dir=TEST_PROJECT,
        )
        assert spec.env["VAULTSPEC_DISALLOWED_TOOLS"] == "Bash"

    def test_effort_env(self, provider):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={"model": ClaudeModels.MEDIUM, "effort": "high"},
            agent_persona="",
            task_context="Do it.",
            root_dir=TEST_PROJECT,
        )
        assert spec.env["VAULTSPEC_EFFORT"] == "high"

    def test_fallback_model_env(self, provider):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={
                "model": ClaudeModels.MEDIUM,
                "fallback_model": ClaudeModels.LOW,
            },
            agent_persona="",
            task_context="Do it.",
            root_dir=TEST_PROJECT,
        )
        assert spec.env["VAULTSPEC_FALLBACK_MODEL"] == ClaudeModels.LOW

    def test_include_dirs_env(self, provider):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={
                "model": ClaudeModels.MEDIUM,
                "include_dirs": ".vault, src",
            },
            agent_persona="",
            task_context="Do it.",
            root_dir=TEST_PROJECT,
        )
        # Production code splits on comma, validates, and re-joins with ","
        assert spec.env["VAULTSPEC_INCLUDE_DIRS"] == ".vault,src"

    def test_output_format_env(self, provider):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={
                "model": ClaudeModels.MEDIUM,
                "output_format": "json",
            },
            agent_persona="",
            task_context="Do it.",
            root_dir=TEST_PROJECT,
        )
        assert spec.env["VAULTSPEC_OUTPUT_FORMAT"] == "json"

    def test_empty_meta_no_env_vars(self, provider):
        """Empty agent_meta should not set any VAULTSPEC_* feature env vars."""
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={"model": ClaudeModels.MEDIUM},
            agent_persona="",
            task_context="Do it.",
            root_dir=TEST_PROJECT,
        )
        for key in (
            "VAULTSPEC_MAX_TURNS",
            "VAULTSPEC_BUDGET_USD",
            "VAULTSPEC_ALLOWED_TOOLS",
            "VAULTSPEC_DISALLOWED_TOOLS",
            "VAULTSPEC_EFFORT",
            "VAULTSPEC_OUTPUT_FORMAT",
            "VAULTSPEC_FALLBACK_MODEL",
            "VAULTSPEC_INCLUDE_DIRS",
        ):
            assert key not in spec.env


class TestGeminiFeaturePassthrough:
    """Verify GeminiProvider sets VAULTSPEC_* env vars from agent_meta fields."""

    @pytest.fixture
    def provider(self):
        return GeminiProvider()

    @pytest.fixture(autouse=True)
    def _seed_version_cache(self):
        from ..providers import gemini as gmod

        gmod._cached_version = (0, 27, 0)
        yield
        gmod._cached_version = None

    def _make_spec(self, provider, **extra_meta):
        meta = {"model": GeminiModels.LOW, **extra_meta}
        return provider.prepare_process(
            agent_name="test",
            agent_meta=meta,
            agent_persona="",
            task_context="Do it.",
            root_dir=TEST_PROJECT,
        )

    def test_allowed_tools_env(self, provider):
        spec = self._make_spec(provider, allowed_tools="Glob, Read")
        assert spec.env["VAULTSPEC_ALLOWED_TOOLS"] == "Glob, Read"

    def test_approval_mode_env(self, provider):
        spec = self._make_spec(provider, approval_mode="yolo")
        assert spec.env["VAULTSPEC_GEMINI_APPROVAL_MODE"] == "yolo"

    def test_approval_mode_default_not_added(self, provider):
        spec = self._make_spec(provider, approval_mode="default")
        assert "VAULTSPEC_GEMINI_APPROVAL_MODE" not in spec.env

    def test_output_format_env(self, provider):
        spec = self._make_spec(provider, output_format="json")
        assert spec.env["VAULTSPEC_OUTPUT_FORMAT"] == "json"

    def test_output_format_text_not_added(self, provider):
        spec = self._make_spec(provider, output_format="text")
        assert "VAULTSPEC_OUTPUT_FORMAT" not in spec.env

    def test_include_dirs_env(self, provider):
        spec = self._make_spec(provider, include_dirs=".vault, src")
        assert spec.env["VAULTSPEC_INCLUDE_DIRS"] == ".vault,src"

    def test_empty_meta_no_env_vars(self, provider):
        spec = self._make_spec(provider)
        for key in (
            "VAULTSPEC_ALLOWED_TOOLS",
            "VAULTSPEC_GEMINI_APPROVAL_MODE",
            "VAULTSPEC_OUTPUT_FORMAT",
            "VAULTSPEC_INCLUDE_DIRS",
        ):
            assert key not in spec.env


class TestProviderAPIParity:
    """Verify both providers implement the same abstract API."""

    def test_construct_system_prompt_signature_matches(self):
        """Both providers have the same construct_system_prompt signature."""
        claude_sig = inspect.signature(ClaudeProvider.construct_system_prompt)
        gemini_sig = inspect.signature(GeminiProvider.construct_system_prompt)
        assert list(claude_sig.parameters) == list(gemini_sig.parameters)

    def test_load_system_prompt_exists_on_both(self):
        """Both providers have load_system_prompt()."""
        assert hasattr(ClaudeProvider, "load_system_prompt")
        assert hasattr(GeminiProvider, "load_system_prompt")

    def test_load_rules_exists_on_both(self):
        """Both providers have load_rules()."""
        assert hasattr(ClaudeProvider, "load_rules")
        assert hasattr(GeminiProvider, "load_rules")

    def test_abstract_methods_on_base(self):
        """Base class declares expected abstract methods."""
        abstracts = AgentProvider.__abstractmethods__
        for method in (
            "load_system_prompt",
            "load_rules",
            "prepare_process",
        ):
            assert method in abstracts

    def test_validate_include_dirs_on_base(self):
        """Base class provides _validate_include_dirs."""
        assert hasattr(AgentProvider, "_validate_include_dirs")


class TestClaudeModeEnv:
    """Verify Claude provider sets VAULTSPEC_AGENT_MODE in env."""

    @pytest.fixture
    def provider(self):
        return ClaudeProvider()

    def test_mode_sets_env_var_read_write(self, provider):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={"model": ClaudeModels.MEDIUM},
            agent_persona="",
            task_context="Do it.",
            root_dir=TEST_PROJECT,
            mode="read-write",
        )
        assert spec.env["VAULTSPEC_AGENT_MODE"] == "read-write"

    def test_mode_sets_env_var_read_only(self, provider):
        spec = provider.prepare_process(
            agent_name="test",
            agent_meta={"model": ClaudeModels.MEDIUM},
            agent_persona="",
            task_context="Do it.",
            root_dir=TEST_PROJECT,
            mode="read-only",
        )
        assert spec.env["VAULTSPEC_AGENT_MODE"] == "read-only"


class TestClaudeSystemPrompt:
    """Verify Claude provider system prompt methods."""

    @pytest.fixture
    def provider(self):
        return ClaudeProvider()

    def test_load_system_prompt_reads_claude_md(self, provider, tmp_path):
        """load_system_prompt reads .claude/CLAUDE.md."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "CLAUDE.md").write_text(
            "System instructions here.",
            encoding="utf-8",
        )
        result = provider.load_system_prompt(tmp_path)
        assert "System instructions here." in result

    def test_load_system_prompt_missing_file(self, provider, tmp_path):
        """load_system_prompt returns '' when file is missing."""
        assert provider.load_system_prompt(tmp_path) == ""

    def test_construct_system_prompt_ordering(self, provider):
        """Prompt ordering: system instructions -> persona -> rules."""
        prompt = provider.construct_system_prompt(
            "I am a persona",
            "These are rules",
            "These are instructions",
        )
        instr_pos = prompt.index("SYSTEM INSTRUCTIONS")
        persona_pos = prompt.index("AGENT PERSONA")
        rules_pos = prompt.index("SYSTEM RULES")
        assert instr_pos < persona_pos < rules_pos

    def test_construct_system_prompt_no_instructions(self, provider):
        """Without system_instructions, no SYSTEM INSTRUCTIONS section."""
        prompt = provider.construct_system_prompt("persona", "rules", "")
        assert "SYSTEM INSTRUCTIONS" not in prompt
        assert "AGENT PERSONA" in prompt


class TestProviderFeatureWarnings:
    """Verify providers warn on unsupported features."""

    def test_claude_warns_on_approval_mode(self, caplog):
        provider = ClaudeProvider()
        with caplog.at_level(
            logging.WARNING,
            logger="protocol.providers.claude",
        ):
            provider.prepare_process(
                agent_name="test",
                agent_meta={
                    "model": ClaudeModels.MEDIUM,
                    "approval_mode": "yolo",
                },
                agent_persona="",
                task_context="Do it.",
                root_dir=TEST_PROJECT,
            )
        assert any(
            "approval_mode" in r.message and "claude" in r.message
            for r in caplog.records
        )

    def test_gemini_warns_on_max_turns(self, caplog):
        from ..providers import gemini as gmod

        gmod._cached_version = (0, 27, 0)
        try:
            provider = GeminiProvider()
            with caplog.at_level(
                logging.WARNING,
                logger="protocol.providers.gemini",
            ):
                provider.prepare_process(
                    agent_name="test",
                    agent_meta={
                        "model": GeminiModels.LOW,
                        "max_turns": "10",
                    },
                    agent_persona="",
                    task_context="Do it.",
                    root_dir=TEST_PROJECT,
                )
            assert any(
                "max_turns" in r.message and "gemini" in r.message
                for r in caplog.records
            )
        finally:
            gmod._cached_version = None

    def test_gemini_warns_on_budget(self, caplog):
        from ..providers import gemini as gmod

        gmod._cached_version = (0, 27, 0)
        try:
            provider = GeminiProvider()
            with caplog.at_level(
                logging.WARNING,
                logger="protocol.providers.gemini",
            ):
                provider.prepare_process(
                    agent_name="test",
                    agent_meta={
                        "model": GeminiModels.LOW,
                        "budget": "5.0",
                    },
                    agent_persona="",
                    task_context="Do it.",
                    root_dir=TEST_PROJECT,
                )
            assert any(
                "budget" in r.message and "gemini" in r.message for r in caplog.records
            )
        finally:
            gmod._cached_version = None


class TestValidateIncludeDirsBase:
    """Verify _validate_include_dirs on base class."""

    def test_valid_dirs_accepted(self, tmp_path):
        (tmp_path / ".vault").mkdir()
        (tmp_path / "src").mkdir()
        provider = ClaudeProvider()
        result = provider._validate_include_dirs(".vault, src", tmp_path)
        assert ".vault" in result
        assert "src" in result

    def test_traversal_rejected(self, tmp_path):
        provider = ClaudeProvider()
        result = provider._validate_include_dirs("../outside", tmp_path)
        assert result == []

    def test_empty_string(self, tmp_path):
        provider = ClaudeProvider()
        result = provider._validate_include_dirs("", tmp_path)
        assert result == []
