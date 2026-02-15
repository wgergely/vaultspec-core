"""Generate A2A Agent Cards from vaultspec agent definition files."""

from a2a.types import AgentCapabilities, AgentCard, AgentSkill


def agent_card_from_definition(
    agent_name: str,
    agent_meta: dict,
    host: str = "localhost",
    port: int = 10010,
) -> AgentCard:
    """Convert a vaultspec agent definition to an A2A Agent Card."""
    return AgentCard(
        name=agent_name,
        description=agent_meta.get("description", f"Vaultspec agent: {agent_name}"),
        url=f"http://{host}:{port}/",
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(
            streaming=True,
            push_notifications=False,
            state_transition_history=True,
        ),
        skills=[
            AgentSkill(
                id=agent_name,
                name=agent_meta.get("name", agent_name),
                description=agent_meta.get("description", ""),
                tags=agent_meta.get("tags", []),
            ),
        ],
    )
