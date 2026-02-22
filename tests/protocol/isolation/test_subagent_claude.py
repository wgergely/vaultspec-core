"""Claude ACP Protocol Tests: Isolation (Single Provider)."""

import pytest

from vaultspec.orchestration.subagent import run_subagent
from vaultspec.protocol.acp import SubagentResult
from vaultspec.protocol.providers import ClaudeProvider

pytestmark = [pytest.mark.integration, pytest.mark.claude]


@pytest.mark.asyncio
async def test_claude_echo_single_turn(workspace, echo_agent_def):
    """Verify Claude ACP handles single-turn deterministic echo."""
    agent_file = workspace / ".vaultspec" / "rules" / "agents" / "echo-claude.md"
    agent_file.write_text(echo_agent_def, encoding="utf-8")

    provider = ClaudeProvider()
    result = await run_subagent(
        agent_name="echo-claude",
        root_dir=workspace,
        initial_task="Hello World",
        provider_instance=provider,
        interactive=False,
    )

    assert isinstance(result, SubagentResult)
    assert "Echo: Hello World" in result.response_text


@pytest.mark.asyncio
async def test_claude_state_multi_turn(workspace, state_agent_def):
    """Verify Claude ACP handles multi-turn state retention."""
    agent_file = workspace / ".vaultspec" / "rules" / "agents" / "state-claude.md"
    agent_file.write_text(state_agent_def, encoding="utf-8")

    provider = ClaudeProvider()

    # Turn 1: Set State
    result1 = await run_subagent(
        agent_name="state-claude",
        root_dir=workspace,
        initial_task="Set secret=12345",
        provider_instance=provider,
        interactive=False,  # Single turn
    )

    assert "OK" in result1.response_text

    # Session ID should be present for resumption
    assert result1.session_id is not None

    # Turn 2: Get State (Resume Session)
    result2 = await run_subagent(
        agent_name="state-claude",
        root_dir=workspace,
        initial_task="Get secret",
        provider_instance=provider,
        interactive=False,
        resume_session_id=result1.session_id,
    )

    assert "12345" in result2.response_text
    assert result2.session_id == result1.session_id
