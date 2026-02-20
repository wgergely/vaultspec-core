"""Cross-provider parity tests.

Verify that ClaudeProvider and GeminiProvider produce
structurally consistent ProcessSpec outputs and deliver
system prompts through the correct provider-specific
mechanisms.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.constants import TEST_PROJECT

from protocol.providers.base import (
    ClaudeModels,
    GeminiModels,
    ProcessSpec,
)
from protocol.providers.claude import ClaudeProvider
from protocol.providers.gemini import GeminiProvider

pytestmark = [pytest.mark.unit]

# Common fixtures ---------------------------------------------------


@pytest.fixture
def claude():
    return ClaudeProvider()


@pytest.fixture
def gemini():
    return GeminiProvider()


@pytest.fixture(autouse=True)
def _seed_gemini_version_cache():
    """Pre-seed the Gemini version cache so check_version() is a no-op."""
    from protocol.providers import gemini as gmod

    orig_cached = gmod._cached_version
    gmod._cached_version = (0, 27, 0)
    yield
    gmod._cached_version = orig_cached


def _gemini_spec(
    provider: GeminiProvider,
    *,
    persona: str = "You are a helper.",
    task: str = "Do the thing.",
    mode: str = "read-write",
) -> ProcessSpec:
    """Build a GeminiProvider ProcessSpec (no mocks needed -- cache pre-seeded)."""
    return provider.prepare_process(
        agent_name="parity-agent",
        agent_meta={"tier": "LOW"},
        agent_persona=persona,
        task_context=task,
        root_dir=TEST_PROJECT,
        model_override=GeminiModels.LOW,
        mode=mode,
    )


def _claude_spec(
    provider: ClaudeProvider,
    *,
    persona: str = "You are a helper.",
    task: str = "Do the thing.",
    mode: str = "read-write",
) -> ProcessSpec:
    """Build a ClaudeProvider ProcessSpec."""
    return provider.prepare_process(
        agent_name="parity-agent",
        agent_meta={"tier": "MEDIUM"},
        agent_persona=persona,
        task_context=task,
        root_dir=TEST_PROJECT,
        model_override=ClaudeModels.MEDIUM,
        mode=mode,
    )


# Tests -------------------------------------------------------------


class TestBothProvidersProduceValidProcessSpec:
    """Both providers return ProcessSpec with required fields."""

    def test_claude_spec_valid(self, claude):
        spec = _claude_spec(claude)
        assert isinstance(spec, ProcessSpec)
        assert spec.executable
        assert isinstance(spec.args, list)
        assert isinstance(spec.env, dict)

    def test_gemini_spec_valid(self, gemini):
        spec = _gemini_spec(gemini)
        assert isinstance(spec, ProcessSpec)
        assert spec.executable
        assert isinstance(spec.args, list)
        assert isinstance(spec.env, dict)


class TestBothProvidersDeliverSystemPrompt:
    """Claude uses VAULTSPEC_SYSTEM_PROMPT env; Gemini uses GEMINI_SYSTEM_MD."""

    def test_claude_sets_vaultspec_system_prompt(self, claude):
        spec = _claude_spec(claude, persona="You are Jean-Claude.")
        assert "VAULTSPEC_SYSTEM_PROMPT" in spec.env
        assert "Jean-Claude" in spec.env["VAULTSPEC_SYSTEM_PROMPT"]

    def test_gemini_sets_gemini_system_md(self, gemini):
        spec = _gemini_spec(gemini, persona="You are Jean-Claude.")
        assert "GEMINI_SYSTEM_MD" in spec.env
        sys_file = Path(spec.env["GEMINI_SYSTEM_MD"])
        assert sys_file.exists()
        content = sys_file.read_text(encoding="utf-8")
        assert "Jean-Claude" in content
        sys_file.unlink(missing_ok=True)


class TestBothProvidersSetInitialPromptTaskOnly:
    """initial_prompt_override equals task_context only."""

    def test_claude_initial_prompt_is_task(self, claude):
        spec = _claude_spec(claude, task="Bake croissants.")
        assert spec.initial_prompt_override == "Bake croissants."

    def test_gemini_initial_prompt_is_task(self, gemini):
        spec = _gemini_spec(gemini, task="Bake croissants.")
        assert spec.initial_prompt_override == "Bake croissants."


class TestBothProvidersAcceptModeParameter:
    """prepare_process accepts mode='read-only' without error."""

    def test_claude_accepts_readonly(self, claude):
        spec = _claude_spec(claude, mode="read-only")
        assert isinstance(spec, ProcessSpec)

    def test_gemini_accepts_readonly(self, gemini):
        spec = _gemini_spec(gemini, mode="read-only")
        assert isinstance(spec, ProcessSpec)


class TestReadonlySandboxBothProviders:
    """Gemini args include --sandbox; Claude does not change args."""

    def test_gemini_readonly_has_sandbox(self, gemini):
        spec = _gemini_spec(gemini, mode="read-only")
        assert "--sandbox" in spec.args

    def test_gemini_readwrite_no_sandbox(self, gemini):
        spec = _gemini_spec(gemini, mode="read-write")
        assert "--sandbox" not in spec.args

    def test_claude_readonly_no_sandbox_in_args(self, claude):
        spec = _claude_spec(claude, mode="read-only")
        assert "--sandbox" not in spec.args
