"""Layer 1 — Unit tests for A2A protocol module.

No network, no LLM. Tests state mapping, agent card generation, and
executor logic using in-memory event queues.
"""

import pytest
from a2a.server.events import EventQueue
from a2a.types import (
    AgentCard,
    Message,
    Part,
    TaskState,
    TaskStatusUpdateEvent,
    TextPart,
)

from protocol.a2a.agent_card import agent_card_from_definition
from protocol.a2a.state_map import A2A_TO_VAULTSPEC, VAULTSPEC_TO_A2A
from protocol.a2a.tests.conftest import (
    EchoExecutor,
    PrefixExecutor,
    make_request_context,
)


@pytest.mark.unit
class TestStateMapping:
    def test_vaultspec_to_a2a_all_states(self):
        """All 6 vaultspec states map to valid A2A TaskState values."""
        expected = {
            "pending": TaskState.submitted,
            "working": TaskState.working,
            "input_required": TaskState.input_required,
            "completed": TaskState.completed,
            "failed": TaskState.failed,
            "cancelled": TaskState.canceled,
        }
        assert expected == VAULTSPEC_TO_A2A

    def test_a2a_to_vaultspec_all_states(self):
        """All 9 A2A states map back to vaultspec states (including fallbacks)."""
        expected = {
            TaskState.submitted: "pending",
            TaskState.working: "working",
            TaskState.input_required: "input_required",
            TaskState.completed: "completed",
            TaskState.failed: "failed",
            TaskState.canceled: "cancelled",
            TaskState.rejected: "failed",
            TaskState.auth_required: "input_required",
            TaskState.unknown: "failed",
        }
        assert expected == A2A_TO_VAULTSPEC

    def test_roundtrip_core_states(self):
        """Core states survive a vaultspec->A2A->vaultspec roundtrip."""
        core = [
            "pending",
            "working",
            "input_required",
            "completed",
            "failed",
            "cancelled",
        ]
        for state in core:
            a2a_state = VAULTSPEC_TO_A2A[state]
            back = A2A_TO_VAULTSPEC[a2a_state]
            assert back == state, f"Roundtrip failed for {state}"


@pytest.mark.unit
class TestAgentCard:
    def test_agent_card_from_definition(self):
        """Agent Card has all required fields."""
        meta = {
            "name": "Researcher",
            "description": "A research agent",
            "tags": ["research", "analysis"],
        }
        card = agent_card_from_definition("researcher", meta, port=10020)

        assert isinstance(card, AgentCard)
        assert card.name == "researcher"
        assert card.description == "A research agent"
        assert card.url == "http://localhost:10020/"
        assert card.version == "0.1.0"
        assert card.default_input_modes == ["text"]
        assert card.default_output_modes == ["text"]
        assert card.capabilities.streaming is True
        assert card.capabilities.push_notifications is False
        assert card.capabilities.state_transition_history is True

    def test_agent_card_skills_from_meta(self):
        """Skills populated from agent metadata."""
        meta = {
            "name": "Writer",
            "description": "A writing agent",
            "tags": ["writing", "docs"],
        }
        card = agent_card_from_definition("writer", meta)

        assert len(card.skills) == 1
        skill = card.skills[0]
        assert skill.id == "writer"
        assert skill.name == "Writer"
        assert skill.description == "A writing agent"
        assert skill.tags == ["writing", "docs"]

    def test_agent_card_defaults(self):
        """Agent Card uses sensible defaults when meta is sparse."""
        card = agent_card_from_definition("minimal", {})

        assert card.name == "minimal"
        assert card.description == "Vaultspec agent: minimal"
        assert card.skills[0].name == "minimal"
        assert card.skills[0].description == ""
        assert card.skills[0].tags == []

    def test_agent_card_serialization_roundtrip(self):
        """Agent Card survives dict -> model -> dict roundtrip."""
        meta = {"name": "Test", "description": "Test agent", "tags": ["test"]}
        card = agent_card_from_definition("test-agent", meta)
        data = card.model_dump()
        restored = AgentCard.model_validate(data)
        assert restored.name == card.name
        assert restored.url == card.url
        assert restored.skills[0].id == card.skills[0].id


@pytest.mark.unit
class TestEchoExecutor:
    @pytest.mark.asyncio
    async def test_echo_executor_returns_text(self):
        """EchoExecutor completes with echoed input."""
        executor = EchoExecutor()
        queue = EventQueue()
        context = make_request_context("Hello A2A")

        await executor.execute(context, queue)

        # Drain events from the queue, calling task_done() so close() can join.
        events = []
        while not queue.queue.empty():
            events.append(queue.queue.get_nowait())
            queue.task_done()

        await queue.close()

        # Expect: working status, then completed status
        assert len(events) == 2
        assert isinstance(events[0], TaskStatusUpdateEvent)
        assert events[0].status.state == TaskState.working
        assert isinstance(events[1], TaskStatusUpdateEvent)
        assert events[1].status.state == TaskState.completed
        assert events[1].final is True

        # Verify message text
        msg = events[1].status.message
        assert msg is not None
        assert len(msg.parts) == 1
        assert msg.parts[0].root.text == "Echo: Hello A2A"


@pytest.mark.unit
class TestPrefixExecutor:
    @pytest.mark.asyncio
    async def test_prefix_executor_prepends(self):
        """PrefixExecutor prepends prefix to input."""
        executor = PrefixExecutor("[Claude] ")
        queue = EventQueue()
        context = make_request_context("analyze code")

        await executor.execute(context, queue)

        # Drain events from the queue, calling task_done() so close() can join.
        events = []
        while not queue.queue.empty():
            events.append(queue.queue.get_nowait())
            queue.task_done()

        await queue.close()

        assert len(events) == 2
        msg = events[1].status.message
        assert msg is not None
        assert msg.parts[0].root.text == "[Claude] analyze code"


@pytest.mark.unit
class TestMessageSerialization:
    def test_message_roundtrip(self):
        """Message -> dict -> Message roundtrip preserves structure."""
        from a2a.types import Role

        msg = Message(
            role=Role.agent,
            message_id="test-msg-001",
            task_id="test-task-001",
            context_id="test-ctx-001",
            parts=[Part(root=TextPart(text="Hello from A2A"))],
        )
        data = msg.model_dump()
        restored = Message.model_validate(data)

        assert restored.role == Role.agent
        assert restored.message_id == "test-msg-001"
        root = restored.parts[0].root
        assert isinstance(root, TextPart)
        assert root.text == "Hello from A2A"

    def test_part_discriminator(self):
        """Part uses TextPart discriminator correctly."""
        part = Part(root=TextPart(text="test"))
        data = part.model_dump()
        assert data["kind"] == "text"
        assert data["text"] == "test"

        restored = Part.model_validate(data)
        assert isinstance(restored.root, TextPart)
        assert restored.root.text == "test"
