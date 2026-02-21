"""Integration test for Claude provider subagent.

Requires (for CLI tests):
- Claude CLI installed and on PATH
- Claude CLI authenticated (handles its own auth)
- Network access to Anthropic API

Unit-level provider tests (load_rules, process_spec) run without the CLI.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from tests.constants import TEST_PROJECT
from vaultspec.orchestration.subagent import run_subagent
from vaultspec.protocol.acp import SubagentResult
from vaultspec.protocol.providers import ClaudeProvider

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_has_claude_cli = shutil.which("claude") is not None


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
    (root / ".vaultspec" / "rules" / "agents").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "rules").mkdir(parents=True, exist_ok=True)
    yield root
    _cleanup_test_project(root)


@pytest.mark.unit
def test_claude_loads_rules(test_project_root):
    """Verify ClaudeProvider.load_rules() reads .claude/rules/ files."""
    (test_project_root / ".claude" / "rules" / "test-rule.md").write_text(
        "# Test Rule\nYou must always say 'VAULTSPEC_VERIFIED'.\n",
        encoding="utf-8",
    )

    provider = ClaudeProvider()
    rules = provider.load_rules(test_project_root)
    assert "VAULTSPEC_VERIFIED" in rules
    assert "Test Rule" in rules


@pytest.mark.unit
def test_claude_process_spec_complete(test_project_root):
    """Verify Claude ProcessSpec delivers system prompt via env var."""
    (test_project_root / ".claude" / "rules" / "identity.md").write_text(
        "Your name is Jean-Claude.\n",
        encoding="utf-8",
    )

    provider = ClaudeProvider()
    spec = provider.prepare_process(
        agent_name="tester",
        agent_meta={"tier": "LOW"},
        agent_persona="You are a helpful assistant.",
        task_context="Tell me your name.",
        root_dir=test_project_root,
    )

    # initial_prompt_override is task-only (no system prefix)
    assert spec.initial_prompt_override == "Tell me your name."
    # System prompt delivered via VAULTSPEC_SYSTEM_PROMPT env var
    assert "VAULTSPEC_SYSTEM_PROMPT" in spec.env
    sys_prompt = spec.env["VAULTSPEC_SYSTEM_PROMPT"]
    assert "Jean-Claude" in sys_prompt
    assert "helpful assistant" in sys_prompt


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.skipif(not _has_claude_cli, reason="Claude CLI not installed")
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_claude_dispatch_lifecycle(test_project_root):
    """Verify run_subagent with real Claude CLI returns a valid result."""
    (test_project_root / ".vaultspec" / "rules" / "agents" / "tester.md").write_text(
        "---\ntier: MEDIUM\n---\n\n# Persona\n"
        "You are Jean-Claude, a helpful assistant.\n"
        "Your name is Jean-Claude. Always introduce yourself by name.\n"
        "Keep your responses extremely short.\n",
        encoding="utf-8",
    )

    provider = ClaudeProvider()

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
@pytest.mark.claude
@pytest.mark.skipif(not _has_claude_cli, reason="Claude CLI not installed")
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_claude_rule_fingerprint(test_project_root):
    """Verify Claude picks up rules from .claude/rules/ directory."""
    # Create agent (minimal, no persona fingerprint)
    (test_project_root / ".vaultspec" / "rules" / "agents" / "tester.md").write_text(
        "---\ntier: LOW\n---\n\n# Persona\n"
        "You are a helpful assistant.\n"
        "Keep your responses extremely short.\n",
        encoding="utf-8",
    )

    # Deploy identity rule to .claude/rules/
    (test_project_root / ".claude" / "rules" / "identity.md").write_text(
        "# Identity Rule\n\n"
        "Your name is Jean-Claude. Always state your name when asked.\n",
        encoding="utf-8",
    )

    provider = ClaudeProvider()
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
    # The rule should make Claude identify as Jean-Claude
    assert "Jean-Claude" in result.response_text
