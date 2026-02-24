"""Gemini ACP Protocol Tests: Isolation (Single Provider)."""

import pytest

from vaultspec.orchestration.subagent import run_subagent
from vaultspec.protocol.acp import SubagentResult
from vaultspec.protocol.providers import GeminiProvider

pytestmark = [pytest.mark.integration, pytest.mark.gemini]


@pytest.fixture
def state_agent_def() -> str:
    """Returns the definition for a robust State Agent."""
    return (
        "---\n"
        "tier: LOW\n"
        "mode: read-write\n"
        "---\n\n"
        "# Persona\n"
        "You are a State Agent. Your only goal is to store and retrieve values.\n"
        "Rules:\n"
        "1. If the user says 'Set <key>=<value>', store it and reply 'OK'.\n"
        "2. If the user says 'Get <key>', reply with the stored value only.\n"
        "3. Do not add any explanation, thoughts, or markdown.\n"
        "4. If no value is stored, reply 'EMPTY'.\n"
    )


@pytest.mark.asyncio
async def test_gemini_echo_single_turn(workspace, echo_agent_def):
    """Verify Gemini ACP handles single-turn deterministic echo."""
    agent_file = workspace / ".vaultspec" / "rules" / "agents" / "echo-gemini.md"
    agent_file.write_text(echo_agent_def, encoding="utf-8")

    provider = GeminiProvider()
    result = await run_subagent(
        agent_name="echo-gemini",
        root_dir=workspace,
        initial_task="Hello World",
        provider_instance=provider,
        interactive=False,
    )

    assert isinstance(result, SubagentResult)
    assert "Echo: Hello World" in result.response_text


@pytest.mark.asyncio
async def test_gemini_state_multi_turn(workspace, state_agent_def):
    """Verify Gemini ACP handles multi-turn state retention."""
    agent_file = workspace / ".vaultspec" / "rules" / "agents" / "state-gemini.md"
    agent_file.write_text(state_agent_def, encoding="utf-8")

    provider = GeminiProvider()

    # Turn 1: Set State
    result1 = await run_subagent(
        agent_name="state-gemini",
        root_dir=workspace,
        initial_task="Set secret=12345",
        provider_instance=provider,
        interactive=False,  # Must be False for non-interactive tests
    )

    assert "OK" in result1.response_text

    # Turn 2: Get State (Resume Session)
    session_id = result1.session_id
    assert session_id is not None

    result2 = await run_subagent(
        agent_name="state-gemini",
        root_dir=workspace,
        initial_task="Get secret",
        provider_instance=provider,
        interactive=False,
        resume_session_id=session_id,
    )

    assert "12345" in result2.response_text
    assert result2.session_id == result1.session_id
