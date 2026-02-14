"""Integration test for Gemini provider subagent.

Requires (for CLI tests):
- Gemini CLI installed and on PATH
- Gemini CLI authenticated (handles its own auth)
- Network access to Google AI API

Unit-level provider tests (load_rules, system prompt) run without the CLI.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from orchestration.subagent import run_subagent
from protocol.acp.types import SubagentResult
from protocol.providers.gemini import GeminiProvider

_has_gemini_cli = shutil.which("gemini") is not None

TEST_PROJECT = Path(__file__).resolve().parent.parent.parent.parent / "test-project"


def _cleanup_test_project(root: Path) -> None:
    """Remove all transient artifacts, preserving .vault/ and README.md."""
    for item in root.iterdir():
        if item.name in (".vault", "README.md", ".gitignore"):
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


@pytest.fixture
def test_project_root() -> Iterator[Path]:
    """Set up test-project as workspace root for integration tests."""
    root = TEST_PROJECT
    (root / ".vaultspec" / "agents").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "rules").mkdir(parents=True, exist_ok=True)
    (root / ".gemini" / "rules").mkdir(parents=True, exist_ok=True)
    (root / ".gemini" / "settings.json").write_text("{}", encoding="utf-8")
    yield root
    _cleanup_test_project(root)


# ---------------------------------------------------------------------------
# Unit-level provider tests (no CLI required)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gemini_loads_rules(test_project_root):
    """Verify GeminiProvider.load_rules() reads .gemini/rules/ files."""
    (test_project_root / ".gemini" / "rules" / "test-rule.md").write_text(
        "# Test Rule\nYou must always say 'VAULTSPEC_VERIFIED'.\n",
        encoding="utf-8",
    )

    provider = GeminiProvider()
    rules = provider.load_rules(test_project_root)
    assert "VAULTSPEC_VERIFIED" in rules
    assert "Test Rule" in rules


@pytest.mark.unit
def test_gemini_system_prompt_includes_rules(test_project_root):
    """Verify Gemini system prompt combines persona + rules."""
    (test_project_root / ".gemini" / "rules" / "identity.md").write_text(
        "Your name is Jean-Claude.\n",
        encoding="utf-8",
    )

    provider = GeminiProvider()
    rules = provider.load_rules(test_project_root)
    prompt = provider.construct_system_prompt("You are a helper.", rules)

    assert "Jean-Claude" in prompt
    assert "helper" in prompt
    assert "AGENT PERSONA" in prompt
    assert "SYSTEM RULES" in prompt


@pytest.mark.unit
def test_gemini_process_spec_complete(test_project_root):
    """Verify Gemini ProcessSpec has system prompt with persona + rules."""
    (test_project_root / ".gemini" / "rules" / "identity.md").write_text(
        "Your name is Jean-Claude.\n",
        encoding="utf-8",
    )

    provider = GeminiProvider()
    spec = provider.prepare_process(
        agent_name="tester",
        agent_meta={"tier": "LOW"},
        agent_persona="You are a helpful assistant.",
        task_context="Tell me your name.",
        root_dir=test_project_root,
    )

    # Gemini writes the system prompt to a temp file; verify it's referenced in args
    assert "--system" in spec.args
    system_idx = spec.args.index("--system")
    system_file = Path(spec.args[system_idx + 1])
    assert system_file.exists()
    content = system_file.read_text(encoding="utf-8")
    assert "Jean-Claude" in content
    assert "helpful assistant" in content

    # Clean up the temp file
    system_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CLI integration tests (require Gemini CLI on PATH)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.skipif(not _has_gemini_cli, reason="Gemini CLI not installed")
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_gemini_dispatch_lifecycle(test_project_root):
    """Verify run_subagent with real Gemini CLI returns a valid result."""
    (test_project_root / ".vaultspec" / "agents" / "tester.md").write_text(
        "---\ntier: LOW\n---\n\n# Persona\n"
        "You are Jean-Claude, a helpful assistant.\n"
        "Your name is Jean-Claude. Always introduce yourself by name.\n"
        "Keep your responses extremely short.\n",
        encoding="utf-8",
    )

    provider = GeminiProvider()

    result = await run_subagent(
        agent_name="tester",
        root_dir=test_project_root,
        initial_task="What is your name? Reply with only your name.",
        provider_instance=provider,
        interactive=False,
        debug=True,
    )

    assert isinstance(result, SubagentResult)
    assert result.session_id is not None
    assert len(result.response_text) > 0
    assert "Jean-Claude" in result.response_text


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.skipif(not _has_gemini_cli, reason="Gemini CLI not installed")
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_gemini_rule_fingerprint(test_project_root):
    """Verify Gemini picks up rules from .gemini/rules/ via system prompt."""
    (test_project_root / ".vaultspec" / "agents" / "tester.md").write_text(
        "---\ntier: LOW\n---\n\n# Persona\n"
        "You are a helpful assistant.\n"
        "Keep your responses extremely short.\n",
        encoding="utf-8",
    )

    (test_project_root / ".gemini" / "rules" / "identity.md").write_text(
        "# Identity Rule\n\n"
        "Your name is Jean-Claude. Always state your name when asked.\n",
        encoding="utf-8",
    )

    provider = GeminiProvider()
    result = await run_subagent(
        agent_name="tester",
        root_dir=test_project_root,
        initial_task="What is your name? Reply with only your name.",
        provider_instance=provider,
        interactive=False,
        debug=True,
    )

    assert isinstance(result, SubagentResult)
    assert "Jean-Claude" in result.response_text
