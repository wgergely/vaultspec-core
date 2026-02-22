"""A2A Protocol Tests: Isolation (Single Provider Team) — Parameterized by provider."""

import pytest

from tests.constants import TEST_PORT_A2A_BASE
from vaultspec.orchestration.team import (
    TeamCoordinator,
    TeamStatus,
    extract_artifact_text,
)

pytestmark = [pytest.mark.integration, pytest.mark.team]

# Port offsets per provider: gemini uses BASE+0/+1, claude uses BASE+2/+3
_PROVIDER_PARAMS = [
    pytest.param(
        "gemini",
        TEST_PORT_A2A_BASE + 0,
        TEST_PORT_A2A_BASE + 1,
        marks=pytest.mark.gemini,
        id="gemini",
    ),
    pytest.param(
        "claude",
        TEST_PORT_A2A_BASE + 2,
        TEST_PORT_A2A_BASE + 3,
        marks=pytest.mark.claude,
        id="claude",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,port1,port2", _PROVIDER_PARAMS)
async def test_team_echo(
    workspace, agent_spawner, echo_agent_def, provider, port1, port2
):
    """Verify single-provider agents can form a team and echo messages."""

    # 1. Setup Agent Definitions
    agent1 = f"{provider}-1"
    agent2 = f"{provider}-2"
    agents_dir = workspace / ".vaultspec" / "rules" / "agents"
    (agents_dir / f"{agent1}.md").write_text(echo_agent_def, encoding="utf-8")
    (agents_dir / f"{agent2}.md").write_text(echo_agent_def, encoding="utf-8")

    # 2. Spawn Agents
    url1 = await agent_spawner(agent1, port1, provider, workspace)
    url2 = await agent_spawner(agent2, port2, provider, workspace)

    # 3. Form Team
    coordinator = TeamCoordinator()
    async with coordinator:
        session = await coordinator.form_team(
            name=f"{provider}-echo-team",
            agent_urls=[url1, url2],
        )
        assert session.status == TeamStatus.ACTIVE
        assert len(session.members) == 2

        # 4. Dispatch Echo Task (Parallel)
        results = await coordinator.dispatch_parallel(
            {
                agent1: "Ping",
                agent2: "Pong",
            }
        )

        # 5. Verify Results
        assert agent1 in results
        assert agent2 in results

        text1 = extract_artifact_text(results[agent1])
        text2 = extract_artifact_text(results[agent2])

        assert "Echo: Ping" in text1
        assert "Echo: Pong" in text2

        # 6. Dissolve
        await coordinator.dissolve_team()
        assert coordinator.session.status == TeamStatus.DISSOLVED
