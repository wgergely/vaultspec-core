"""A2A HTTP server for vaultspec agents.

Wraps an AgentExecutor with DefaultRequestHandler + InMemoryTaskStore
and builds a Starlette ASGI application via A2AStarletteApplication.

Usage::

    from protocol.a2a.server import create_app
    from protocol.a2a.agent_card import agent_card_from_definition

    card = agent_card_from_definition("vaultspec-researcher", meta, port=10010)
    app = create_app(executor, card)
    # app is a Starlette instance, run with uvicorn or test with httpx
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

if TYPE_CHECKING:
    from a2a.server.agent_execution import AgentExecutor
    from a2a.types import AgentCard
    from starlette.applications import Starlette

logger = logging.getLogger(__name__)


def create_app(executor: AgentExecutor, agent_card: AgentCard) -> Starlette:
    """Build an A2A Starlette application from an executor and agent card.

    Args:
        executor: The AgentExecutor that processes incoming A2A messages.
        agent_card: The AgentCard describing this agent's capabilities.

    Returns:
        A configured Starlette ASGI application with routes for:
        - ``/.well-known/agent-card.json`` (GET) — agent card
        - ``/`` (POST) — JSON-RPC endpoint for message/send, tasks/*, etc.
    """
    logger.info("Creating A2A Starlette app for agent: %s", agent_card.name)

    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    logger.debug("Created request handler with in-memory task store")

    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler,
    )
    app = a2a_app.build()
    logger.info("A2A Starlette app built successfully")
    return app
