"""Cross-Provider Subagent Dispatch Protocol Tests.

Verifies that one provider can dispatch a task to a subagent running on a
different provider via the ``dispatch_agent`` MCP tool.  The Lead Agent
persona is explicitly instructed to return only the raw tool result — no
wrapping, explanation, or markdown — so the assertion can be resilient
without being fragile.
"""

import pytest

from vaultspec.orchestration.subagent import run_subagent
from vaultspec.protocol.acp import SubagentResult
from vaultspec.protocol.providers import ClaudeProvider, GeminiProvider

pytestmark = [pytest.mark.integration, pytest.mark.gemini, pytest.mark.claude]

# Shared Lead Agent persona template.  The explicit "return ONLY the raw
# tool result" instruction minimises non-determinism from LLM reformulation.
_LEAD_AGENT_TEMPLATE = (
    "---\n"
    "tier: MEDIUM\n"
    "---\n"
    "# Persona\n"
    "You are a Lead Agent.  Your ONLY job is:\n"
    "1. Call the 'dispatch_agent' tool with agent='{echo_agent}' and "
    "task='Echo: {payload}'.\n"
    "2. Return ONLY the raw tool result text.  Do NOT explain, wrap, "
    "summarise, or add any other text.\n"
)


def _lead_agent_def(echo_agent: str, payload: str) -> str:
    return _LEAD_AGENT_TEMPLATE.format(echo_agent=echo_agent, payload=payload)


@pytest.mark.asyncio
async def test_gemini_spawns_claude(workspace, echo_agent_def, mcp_server_config):
    """Verify Gemini can dispatch a task to a Claude subagent via tool call."""

    payload = "Hello from Gemini"
    agents_dir = workspace / ".vaultspec" / "rules" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "gemini-lead.md").write_text(
        _lead_agent_def("claude-echo", payload),
        encoding="utf-8",
    )
    (agents_dir / "claude-echo.md").write_text(echo_agent_def, encoding="utf-8")

    provider = GeminiProvider()
    result = await run_subagent(
        agent_name="gemini-lead",
        root_dir=workspace,
        initial_task="Go.",
        provider_instance=provider,
        interactive=False,
        mcp_servers=mcp_server_config,
    )

    assert isinstance(result, SubagentResult)
    # Resilient assertions: check key substrings independently so that
    # minor LLM reformulation (e.g. quoting, newline wrapping) does not
    # cause a false-negative.
    assert "Echo" in result.response_text
    assert payload in result.response_text


@pytest.mark.asyncio
async def test_claude_spawns_gemini(workspace, echo_agent_def, mcp_server_config):
    """Verify Claude can dispatch a task to a Gemini subagent via tool call."""

    payload = "Hello from Claude"
    agents_dir = workspace / ".vaultspec" / "rules" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "claude-lead.md").write_text(
        _lead_agent_def("gemini-echo", payload),
        encoding="utf-8",
    )
    (agents_dir / "gemini-echo.md").write_text(echo_agent_def, encoding="utf-8")

    provider = ClaudeProvider()
    result = await run_subagent(
        agent_name="claude-lead",
        root_dir=workspace,
        initial_task="Go.",
        provider_instance=provider,
        interactive=False,
        mcp_servers=mcp_server_config,
    )

    assert isinstance(result, SubagentResult)
    assert "Echo" in result.response_text
    assert payload in result.response_text
