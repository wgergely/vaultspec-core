"""Mixed Gemini/Claude A2A Protocol Tests: Cross-Wiring."""

import pytest

from tests.constants import TEST_PORT_A2A_BASE
from vaultspec.orchestration.team import (
    TeamCoordinator,
    TeamStatus,
    extract_artifact_text,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.gemini,
    pytest.mark.claude,
    pytest.mark.team,
]


@pytest.mark.asyncio
async def test_mixed_team_echo(workspace, agent_spawner, echo_agent_def):
    """Verify a team with both Gemini and Claude can collaborate on echo tasks."""

    # 1. Setup Agent Definitions
    (workspace / ".vaultspec" / "rules" / "agents" / "gemini-echo.md").write_text(
        echo_agent_def, encoding="utf-8"
    )
    (workspace / ".vaultspec" / "rules" / "agents" / "claude-echo.md").write_text(
        echo_agent_def, encoding="utf-8"
    )

    # 2. Spawn Agents (Mixed Providers)
    url_gemini = await agent_spawner(
        "gemini-echo", TEST_PORT_A2A_BASE + 4, "gemini", workspace
    )
    url_claude = await agent_spawner(
        "claude-echo", TEST_PORT_A2A_BASE + 5, "claude", workspace
    )

    # 3. Form Team
    coordinator = TeamCoordinator()
    async with coordinator:
        session = await coordinator.form_team(
            name="mixed-echo-team",
            agent_urls=[url_gemini, url_claude],
        )
        assert session.status == TeamStatus.ACTIVE
        assert len(session.members) == 2

        # 4. Dispatch Echo Task (Broadcast)
        results = await coordinator.dispatch_parallel(
            {
                "gemini-echo": "Hello from Gemini",
                "claude-echo": "Hello from Claude",
            }
        )

        # 5. Verify Results
        assert "gemini-echo" in results
        assert "claude-echo" in results

        text_gemini = extract_artifact_text(results["gemini-echo"])
        text_claude = extract_artifact_text(results["claude-echo"])

        assert "Echo: Hello from Gemini" in text_gemini
        assert "Echo: Hello from Claude" in text_claude

        # 6. Dissolve
        await coordinator.dissolve_team()
        assert coordinator.session.status == TeamStatus.DISSOLVED


@pytest.mark.asyncio
async def test_mixed_team_relay(workspace, agent_spawner, echo_agent_def):
    """Verify one provider can relay its output to another provider."""

    # 1. Setup Agent Definitions
    (workspace / ".vaultspec" / "rules" / "agents" / "gemini-echo.md").write_text(
        echo_agent_def, encoding="utf-8"
    )
    (workspace / ".vaultspec" / "rules" / "agents" / "claude-echo.md").write_text(
        echo_agent_def, encoding="utf-8"
    )

    # 2. Spawn Agents
    url_gemini = await agent_spawner(
        "gemini-echo", TEST_PORT_A2A_BASE + 6, "gemini", workspace
    )
    url_claude = await agent_spawner(
        "claude-echo", TEST_PORT_A2A_BASE + 7, "claude", workspace
    )

    # 3. Form Team
    coordinator = TeamCoordinator()
    async with coordinator:
        await coordinator.form_team(
            name="mixed-relay-team",
            agent_urls=[url_gemini, url_claude],
        )

        # 4. Dispatch to Source (Gemini)
        results = await coordinator.dispatch_parallel({"gemini-echo": "Initial Msg"})
        src_task = results["gemini-echo"]

        # 5. Relay Output to Destination (Claude)
        # relay_output takes the TaskResult from source and sends it as input to
        # destination
        relay_task = await coordinator.relay_output(
            src_task, "claude-echo", "Processing relay: "
        )

        # 6. Verify Relay Result
        # Claude should receive "Processing relay: Echo: Initial Msg"
        final_text = extract_artifact_text(relay_task)
        assert "Initial Msg" in final_text
        assert "Processing relay" in final_text
        assert "Echo" in final_text

        await coordinator.dissolve_team()


@pytest.mark.asyncio
async def test_mixed_team_broadcast(workspace, agent_spawner, echo_agent_def):
    """Verify broadcasting the SAME message to a Gemini and Claude agent.

    ADR Decision 3, Section B: "Form team (1 Gemini, 1 Claude). Broadcast
    'Hello'. Verify both return 'Echo: Hello'."
    """

    (workspace / ".vaultspec" / "rules" / "agents" / "gemini-echo.md").write_text(
        echo_agent_def, encoding="utf-8"
    )
    (workspace / ".vaultspec" / "rules" / "agents" / "claude-echo.md").write_text(
        echo_agent_def, encoding="utf-8"
    )

    url_gemini = await agent_spawner(
        "gemini-echo", TEST_PORT_A2A_BASE + 8, "gemini", workspace
    )
    url_claude = await agent_spawner(
        "claude-echo", TEST_PORT_A2A_BASE + 9, "claude", workspace
    )

    coordinator = TeamCoordinator()
    async with coordinator:
        session = await coordinator.form_team(
            name="mixed-broadcast-team",
            agent_urls=[url_gemini, url_claude],
        )
        assert session.status == TeamStatus.ACTIVE
        assert len(session.members) == 2

        # Broadcast the SAME message to both agents
        broadcast_msg = "Hello"
        results = await coordinator.dispatch_parallel(
            {
                "gemini-echo": broadcast_msg,
                "claude-echo": broadcast_msg,
            }
        )

        assert "gemini-echo" in results
        assert "claude-echo" in results

        text_gemini = extract_artifact_text(results["gemini-echo"])
        text_claude = extract_artifact_text(results["claude-echo"])

        assert "Echo" in text_gemini
        assert broadcast_msg in text_gemini
        assert "Echo" in text_claude
        assert broadcast_msg in text_claude

        await coordinator.dissolve_team()
        assert coordinator.session.status == TeamStatus.DISSOLVED
