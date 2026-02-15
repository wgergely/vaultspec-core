"""Cross-provider parity tests.

Verify that ClaudeProvider and GeminiProvider produce
structurally consistent ProcessSpec outputs and deliver
system prompts through the correct provider-specific
mechanisms.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

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
def _clear_gemini_version_cache():
    """Reset module-level version cache around each test."""
    from protocol.providers import gemini as gmod

    gmod._cached_version = None
    yield
    gmod._cached_version = None


def _gemini_spec(
    provider: GeminiProvider,
    tmp_path: Path,
    *,
    persona: str = "You are a helper.",
    task: str = "Do the thing.",
    mode: str = "read-write",
) -> ProcessSpec:
    """Build a GeminiProvider ProcessSpec with mocked deps."""
    with (
        mock.patch(
            "protocol.providers.gemini.shutil.which",
            return_value="/usr/bin/gemini",
        ),
        mock.patch(
            "protocol.providers.gemini.GeminiProvider.check_version",
            return_value=(0, 27, 0),
        ),
    ):
        return provider.prepare_process(
            agent_name="parity-agent",
            agent_meta={"tier": "LOW"},
            agent_persona=persona,
            task_context=task,
            root_dir=tmp_path,
            model_override=GeminiModels.LOW,
            mode=mode,
        )


def _claude_spec(
    provider: ClaudeProvider,
    tmp_path: Path,
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
        root_dir=tmp_path,
        model_override=ClaudeModels.MEDIUM,
        mode=mode,
    )


# Tests -------------------------------------------------------------


class TestBothProvidersProduceValidProcessSpec:
    """Both providers return ProcessSpec with required fields."""

    def test_claude_spec_valid(self, claude, tmp_path):
        spec = _claude_spec(claude, tmp_path)
        assert isinstance(spec, ProcessSpec)
        assert spec.executable
        assert isinstance(spec.args, list)
        assert isinstance(spec.env, dict)

    def test_gemini_spec_valid(self, gemini, tmp_path):
        spec = _gemini_spec(gemini, tmp_path)
        assert isinstance(spec, ProcessSpec)
        assert spec.executable
        assert isinstance(spec.args, list)
        assert isinstance(spec.env, dict)


class TestBothProvidersDeliverSystemPrompt:
    """Claude uses VS_SYSTEM_PROMPT env; Gemini uses GEMINI_SYSTEM_MD."""

    def test_claude_sets_vs_system_prompt(self, claude, tmp_path):
        spec = _claude_spec(claude, tmp_path, persona="You are Jean-Claude.")
        assert "VS_SYSTEM_PROMPT" in spec.env
        assert "Jean-Claude" in spec.env["VS_SYSTEM_PROMPT"]

    def test_gemini_sets_gemini_system_md(self, gemini, tmp_path):
        spec = _gemini_spec(gemini, tmp_path, persona="You are Jean-Claude.")
        assert "GEMINI_SYSTEM_MD" in spec.env
        sys_file = Path(spec.env["GEMINI_SYSTEM_MD"])
        assert sys_file.exists()
        content = sys_file.read_text(encoding="utf-8")
        assert "Jean-Claude" in content
        sys_file.unlink(missing_ok=True)


class TestBothProvidersSetInitialPromptTaskOnly:
    """initial_prompt_override equals task_context only."""

    def test_claude_initial_prompt_is_task(self, claude, tmp_path):
        spec = _claude_spec(claude, tmp_path, task="Bake croissants.")
        assert spec.initial_prompt_override == "Bake croissants."

    def test_gemini_initial_prompt_is_task(self, gemini, tmp_path):
        spec = _gemini_spec(gemini, tmp_path, task="Bake croissants.")
        assert spec.initial_prompt_override == "Bake croissants."


class TestBothProvidersAcceptModeParameter:
    """prepare_process accepts mode='read-only' without error."""

    def test_claude_accepts_readonly(self, claude, tmp_path):
        spec = _claude_spec(claude, tmp_path, mode="read-only")
        assert isinstance(spec, ProcessSpec)

    def test_gemini_accepts_readonly(self, gemini, tmp_path):
        spec = _gemini_spec(gemini, tmp_path, mode="read-only")
        assert isinstance(spec, ProcessSpec)


class TestReadonlySandboxBothProviders:
    """Gemini args include --sandbox; Claude does not change args."""

    def test_gemini_readonly_has_sandbox(self, gemini, tmp_path):
        spec = _gemini_spec(gemini, tmp_path, mode="read-only")
        assert "--sandbox" in spec.args

    def test_gemini_readwrite_no_sandbox(self, gemini, tmp_path):
        spec = _gemini_spec(gemini, tmp_path, mode="read-write")
        assert "--sandbox" not in spec.args

    def test_claude_readonly_no_sandbox_in_args(self, claude, tmp_path):
        spec = _claude_spec(claude, tmp_path, mode="read-only")
        assert "--sandbox" not in spec.args
