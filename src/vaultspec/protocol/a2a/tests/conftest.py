"""Fixtures for A2A protocol tests."""

from __future__ import annotations

import httpx
import pytest
from a2a.server.agent_execution import RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Message,
    MessageSendParams,
    Part,
    Role,
    TextPart,
)

from .helpers import EchoExecutor, PrefixExecutor


@pytest.fixture
def echo_executor():
    return EchoExecutor()


@pytest.fixture
def claude_test_executor():
    return PrefixExecutor("[Claude] ")


@pytest.fixture
def gemini_test_executor():
    return PrefixExecutor("[Gemini] ")


def _make_card(name: str, port: int) -> AgentCard:
    return AgentCard(
        name=name,
        url=f"http://localhost:{port}/",
        version="0.1.0",
        description=f"Test {name} agent",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id="test",
                name="Test",
                description="Test skill",
                tags=["test"],
            )
        ],
    )


def make_request_context(
    text: str,
    task_id: str = "test-task-1",
    context_id: str = "test-ctx-1",
) -> RequestContext:
    """Build a RequestContext with the given user text for unit testing."""
    msg = Message(
        role=Role.user,
        message_id="test-msg-1",
        parts=[Part(root=TextPart(text=text))],
    )
    params = MessageSendParams(message=msg)
    return RequestContext(
        request=params,
        task_id=task_id,
        context_id=context_id,
    )


@pytest.fixture
def a2a_server_factory():
    """Factory: (executor, name, port) -> (app, card, httpx_client)"""

    async def _factory(executor, name="test", port=10099):
        card = _make_card(name, port)
        handler = DefaultRequestHandler(
            agent_executor=executor,
            task_store=InMemoryTaskStore(),
        )
        a2a_app = A2AStarletteApplication(
            agent_card=card,
            http_handler=handler,
        )
        app = a2a_app.build()
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=f"http://localhost:{port}",
        )
        return app, card, client

    return _factory
