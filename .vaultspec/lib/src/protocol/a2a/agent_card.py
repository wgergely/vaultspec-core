"""Generate A2A Agent Cards from vaultspec agent definition files."""

import logging

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

logger = logging.getLogger(__name__)


def agent_card_from_definition(
    agent_name: str,
    agent_meta: dict,
    host: str | None = None,
    port: int | None = None,
) -> AgentCard:
    """Convert a vaultspec agent definition to an A2A Agent Card."""
    from core.config import get_config

    logger.info("Creating A2A agent card for agent: %s", agent_name)

    cfg = get_config()
    host = host or cfg.a2a_host
    port = port or cfg.a2a_default_port
    logger.debug("Agent card URL: http://%s:%d/", host, port)

    card = AgentCard(
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
    logger.info("Agent card created with 1 skill")
    return card
