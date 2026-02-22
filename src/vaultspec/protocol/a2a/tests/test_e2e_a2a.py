"""A2A protocol tests.

E2E tests require real LLM backends (authenticated via their CLIs):
- Claude CLI (``claude``) on PATH for Claude tests
- Gemini CLI (``gemini``) on PATH for Gemini tests

Protocol infrastructure tests exercise the real A2A server stack (JSON-RPC,
task lifecycle, message routing, Starlette app wiring) using simple
AgentExecutor implementations (EchoExecutor, PrefixExecutor).

Markers:
- @pytest.mark.integration + @pytest.mark.claude/@pytest.mark.gemini — real LLM E2E
- @pytest.mark.integration — protocol infrastructure (real server, no LLM)
"""

from __future__ import annotations

import logging
import shutil
import time
import uuid

import httpx
import pytest
from a2a.types import AgentCard

from tests.constants import PROJECT_ROOT as _TEST_ROOT

from ...providers import ClaudeModels, GeminiModels
from .. import agent_card_from_definition, create_app
from .conftest import (
    EchoExecutor,
    PrefixExecutor,
    _make_card,
)

logger = logging.getLogger(__name__)

requires_anthropic = pytest.mark.skipif(
    not shutil.which("claude"),
    reason="Claude CLI not on PATH",
)

requires_gemini = pytest.mark.skipif(
    not shutil.which("gemini"),
    reason="Gemini CLI not on PATH",
)


def _send_message_payload(text: str, message_id: str | None = None) -> dict:
    """Build a JSON-RPC 'message/send' request body."""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": message_id or str(uuid.uuid4()),
                "parts": [{"kind": "text", "text": text}],
            }
        },
    }


def _build_client(executor, name: str = "test", port: int = 10099) -> httpx.AsyncClient:
    """Build an httpx.AsyncClient backed by an in-process A2A ASGI app."""
    card = _make_card(name, port)
    app = create_app(executor, card)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=f"http://localhost:{port}",
    )


# ===================================================================
# Integration tests (no real LLM)
# ===================================================================


@pytest.mark.integration
class TestA2AServeWiring:
    """Verify create_app produces a working Starlette app with test executor."""

    @pytest.mark.asyncio
    async def test_create_app_with_echo_executor(self):
        """create_app returns a Starlette app that serves agent card."""
        executor = EchoExecutor()
        card = agent_card_from_definition(
            "test-echo",
            {"name": "Echo", "description": "Test echo agent"},
            port=10050,
        )
        app = create_app(executor, card)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost:10050",
        ) as client:
            # Agent card is served
            card_resp = await client.get("/.well-known/agent-card.json")
            assert card_resp.status_code == 200
            card_data = card_resp.json()
            assert card_data["name"] == "test-echo"

            # Message send works
            resp = await client.post("/", json=_send_message_payload("wiring test"))
            assert resp.status_code == 200
            body = resp.json()
            assert body["result"]["status"]["state"] == "completed"

    @pytest.mark.asyncio
    async def test_create_app_with_prefix_executor(self):
        """create_app works with stateful executors (PrefixExecutor)."""
        executor = PrefixExecutor("[Test] ")
        card = _make_card("prefix-test", 10051)
        app = create_app(executor, card)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost:10051",
        ) as client:
            resp = await client.post("/", json=_send_message_payload("hello"))
            body = resp.json()
            msg = body["result"]["status"]["message"]
            assert msg["parts"][0]["text"] == "[Test] hello"


@pytest.mark.integration
class TestAgentCardFromCLIArgs:
    """Verify agent_card_from_definition with CLI-like parameters."""

    def test_card_with_host_and_port(self):
        """Card URL reflects custom host and port."""
        card = agent_card_from_definition(
            "vaultspec-researcher",
            {
                "name": "Researcher",
                "description": "Research agent",
                "tags": ["research"],
            },
            host="0.0.0.0",
            port=10020,
        )
        assert card.url == "http://0.0.0.0:10020/"
        assert card.name == "vaultspec-researcher"
        assert card.skills[0].tags == ["research"]

    def test_card_defaults_for_minimal_meta(self):
        """Card uses sensible defaults when agent meta is empty."""
        card = agent_card_from_definition("agent-x", {})
        assert card.name == "agent-x"
        assert card.description == "Vaultspec agent: agent-x"
        assert card.url == "http://localhost:10010/"  # default port

    def test_card_serializes_for_http_response(self):
        """Card can be serialized to dict (as the server does for HTTP response)."""
        card = agent_card_from_definition(
            "writer",
            {"name": "Writer", "description": "Writing agent"},
            port=10030,
        )
        data = card.model_dump()
        assert data["name"] == "writer"
        assert data["url"] == "http://localhost:10030/"
        restored = AgentCard.model_validate(data)
        assert restored.name == card.name


# ===================================================================
# In-process bidirectional integration tests (no real LLM)
# ===================================================================


@pytest.mark.integration
class TestInProcessBidirectional:
    """Bidirectional A2A communication with in-process test executors.

    Validates the full A2A stack (JSON-RPC, task lifecycle, message
    routing) without requiring real LLM backends.
    """

    @pytest.mark.asyncio
    async def test_claude_gemini_bidirectional(self):
        """Two A2A servers exchange messages in both directions.

        In-process Claude ([Claude] prefix) and Gemini ([Gemini] prefix)
        each send a message to the other and both complete successfully.
        """
        claude_client = _build_client(
            PrefixExecutor("[Claude] "), name="test-claude", port=10090
        )
        gemini_client = _build_client(
            PrefixExecutor("[Gemini] "), name="test-gemini", port=10091
        )

        async with claude_client, gemini_client:
            # Claude processes a message
            claude_resp = await claude_client.post(
                "/", json=_send_message_payload("research quantum computing")
            )
            claude_body = claude_resp.json()
            assert claude_body["result"]["status"]["state"] == "completed"
            claude_text = claude_body["result"]["status"]["message"]["parts"][0]["text"]
            assert claude_text == "[Claude] research quantum computing"

            # Gemini processes a message
            gemini_resp = await gemini_client.post(
                "/", json=_send_message_payload("analyze the results")
            )
            gemini_body = gemini_resp.json()
            assert gemini_body["result"]["status"]["state"] == "completed"
            gemini_text = gemini_body["result"]["status"]["message"]["parts"][0]["text"]
            assert gemini_text == "[Gemini] analyze the results"

            # Now simulate cross-delegation: send Gemini's output to Claude
            cross_resp = await claude_client.post(
                "/", json=_send_message_payload(gemini_text)
            )
            cross_body = cross_resp.json()
            assert cross_body["result"]["status"]["state"] == "completed"
            cross_text = cross_body["result"]["status"]["message"]["parts"][0]["text"]
            assert cross_text == "[Claude] [Gemini] analyze the results"

    @pytest.mark.asyncio
    async def test_claude_to_gemini_delegation(self):
        """Claude executor receives task, forwards to Gemini via A2A.

        Simulates the delegation pattern:
        1. Client sends task to Claude A2A server
        2. Claude completes with a result
        3. That result is forwarded to Gemini A2A server
        4. Gemini completes with final result
        5. Verify the full chain produces expected output
        """
        claude_client = _build_client(
            PrefixExecutor("[Claude] "), name="delegate-claude", port=10092
        )
        gemini_client = _build_client(
            PrefixExecutor("[Gemini] "), name="delegate-gemini", port=10093
        )

        async with claude_client, gemini_client:
            # Step 1: Client sends task to Claude
            original_task = "summarize the architecture document"
            claude_resp = await claude_client.post(
                "/", json=_send_message_payload(original_task)
            )
            claude_body = claude_resp.json()
            assert claude_body["result"]["status"]["state"] == "completed"
            claude_output = claude_body["result"]["status"]["message"]["parts"][0][
                "text"
            ]

            # Step 2: Forward Claude's output to Gemini (delegation)
            gemini_resp = await gemini_client.post(
                "/", json=_send_message_payload(claude_output)
            )
            gemini_body = gemini_resp.json()
            assert gemini_body["result"]["status"]["state"] == "completed"
            final_output = gemini_body["result"]["status"]["message"]["parts"][0][
                "text"
            ]

            # Verify the chain: original text was processed by both agents
            expected = "[Gemini] [Claude] summarize the architecture document"
            assert final_output == expected

            # Verify both tasks have independent IDs
            claude_task_id = claude_body["result"]["id"]
            gemini_task_id = gemini_body["result"]["id"]
            assert claude_task_id != gemini_task_id


# ===================================================================
# E2E tests (real LLM required)
# ===================================================================


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.timeout(180)
@requires_anthropic
class TestClaudeE2E:
    @pytest.mark.asyncio
    async def test_claude_a2a_responds(self):
        """Real Claude processes an A2A message and returns a completed task."""
        from ..executors import ClaudeA2AExecutor

        executor = ClaudeA2AExecutor(
            model=ClaudeModels.MEDIUM,
            root_dir=str(_TEST_ROOT),
            mode="read-only",
        )
        client = _build_client(executor, name="claude-e2e", port=10060)

        async with client:
            payload = _send_message_payload("Reply with exactly: HELLO_A2A_CLAUDE")
            logger.info("Sending request to Claude E2E (%s)...", ClaudeModels.MEDIUM)
            start = time.monotonic()
            resp = await client.post("/", json=payload)
            elapsed = time.monotonic() - start

            assert resp.status_code == 200
            body = resp.json()
            result = body.get("result")
            assert result is not None, f"No result in response: {body}"
            state = result["status"]["state"]
            assert state == "completed"

            # Verify the response contains expected text
            message = result["status"].get("message", {})
            parts = message.get("parts", [])
            assert len(parts) >= 1
            response_text = parts[0].get("text", "")
            assert "HELLO_A2A_CLAUDE" in response_text

            logger.info(
                "Response from Claude E2E: state=%s, %.2fs, model=%s",
                state,
                elapsed,
                ClaudeModels.MEDIUM,
            )


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.timeout(180)
@requires_gemini
class TestGeminiE2E:
    @pytest.mark.asyncio
    async def test_gemini_a2a_responds(self):
        """Real Gemini processes an A2A message and returns a completed task."""
        from ..executors import GeminiA2AExecutor

        executor = GeminiA2AExecutor(
            root_dir=_TEST_ROOT,
            model=GeminiModels.LOW,
            agent_name="vaultspec-researcher",
        )
        client = _build_client(executor, name="gemini-e2e", port=10061)

        async with client:
            payload = _send_message_payload("Reply with exactly: HELLO_A2A_GEMINI")
            logger.info("Sending request to Gemini E2E (%s)...", GeminiModels.LOW)
            start = time.monotonic()
            resp = await client.post("/", json=payload)
            elapsed = time.monotonic() - start

            assert resp.status_code == 200
            body = resp.json()
            result = body.get("result")
            assert result is not None, f"No result in response: {body}"
            state = result["status"]["state"]
            fail_msg = (
                result["status"]
                .get("message", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            assert state == "completed", f"Expected completed, got {state}: {fail_msg}"

            message = result["status"].get("message", {})
            parts = message.get("parts", [])
            assert len(parts) >= 1
            response_text = parts[0].get("text", "")
            assert "HELLO_A2A_GEMINI" in response_text

            logger.info(
                "Response from Gemini E2E: state=%s, %.2fs, model=%s",
                state,
                elapsed,
                GeminiModels.LOW,
            )


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.gemini
@pytest.mark.timeout(300)
@requires_anthropic
@requires_gemini
class TestGoldStandardBidirectional:
    """Gold standard tests: cross-agent A2A communication.

    These tests validate real bidirectional communication where one agent
    delegates work to another via A2A protocol.
    """

    @pytest.mark.asyncio
    async def test_claude_asks_gemini(self):
        """GOLD STANDARD: Claude sends task to Gemini via A2A, gets result back.

        Flow:
        1. Gemini A2A server running in-process (ASGITransport)
        2. Claude A2A server running in-process
        3. Send message to Claude asking it to delegate to Gemini
        4. Verify round-trip completes with Gemini's response

        Note: This test validates the A2A infrastructure by having both
        executors process messages. True cross-delegation (Claude calling
        Gemini's A2A endpoint) requires MCP tool injection, which is
        Phase 6 scope. Here we validate both agents can independently
        complete A2A tasks and that results can be chained.
        """
        from ..executors import (
            ClaudeA2AExecutor,
            GeminiA2AExecutor,
        )

        # Set up Gemini A2A server
        gemini_executor = GeminiA2AExecutor(
            root_dir=_TEST_ROOT,
            model=GeminiModels.LOW,
            agent_name="vaultspec-researcher",
        )
        gemini_card = agent_card_from_definition(
            "gemini-agent",
            {"name": "Gemini", "description": "Gemini research agent"},
            port=10070,
        )
        gemini_app = create_app(gemini_executor, gemini_card)
        gemini_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=gemini_app),
            base_url="http://localhost:10070",
        )

        # Set up Claude A2A server
        claude_executor = ClaudeA2AExecutor(
            model=ClaudeModels.MEDIUM,
            root_dir=str(_TEST_ROOT),
            mode="read-only",
        )
        claude_card = agent_card_from_definition(
            "claude-agent",
            {"name": "Claude", "description": "Claude analysis agent"},
            port=10071,
        )
        claude_app = create_app(claude_executor, claude_card)
        claude_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=claude_app),
            base_url="http://localhost:10071",
        )

        async with gemini_client, claude_client:
            # Step 1: Send task to Gemini
            logger.info("Sending request to Gemini (%s)...", GeminiModels.LOW)
            start = time.monotonic()
            gemini_resp = await gemini_client.post(
                "/",
                json=_send_message_payload(
                    "Reply with exactly one word: GEMINI_CONFIRMED"
                ),
            )
            gemini_elapsed = time.monotonic() - start
            gemini_body = gemini_resp.json()
            gemini_state = gemini_body["result"]["status"]["state"]
            assert gemini_state == "completed"
            gemini_text = (
                gemini_body["result"]["status"]
                .get("message", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            logger.info(
                "Response from Gemini: state=%s, %.2fs", gemini_state, gemini_elapsed
            )

            # Step 2: Send Gemini's output to Claude for processing
            logger.info("Sending request to Claude (%s)...", ClaudeModels.MEDIUM)
            start2 = time.monotonic()
            claude_resp = await claude_client.post(
                "/",
                json=_send_message_payload(
                    f"The following text was produced by Gemini: '{gemini_text}'. "
                    "Reply with exactly: CLAUDE_RECEIVED_GEMINI"
                ),
            )
            claude_elapsed = time.monotonic() - start2
            claude_body = claude_resp.json()
            claude_state = claude_body["result"]["status"]["state"]
            assert claude_state == "completed"
            claude_text = (
                claude_body["result"]["status"]
                .get("message", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            logger.info(
                "Response from Claude: state=%s, %.2fs", claude_state, claude_elapsed
            )

            total_elapsed = gemini_elapsed + claude_elapsed

            assert "GEMINI_CONFIRMED" in gemini_text
            assert "CLAUDE_RECEIVED_GEMINI" in claude_text

            logger.info(
                "Claude-asks-Gemini total: %.2fs (gemini=%.2fs, claude=%.2fs)",
                total_elapsed,
                gemini_elapsed,
                claude_elapsed,
            )

    @pytest.mark.asyncio
    async def test_gemini_asks_claude(self):
        """GOLD STANDARD: Gemini sends task to Claude via A2A, gets result back.

        Mirror of test_claude_asks_gemini with reversed flow:
        1. Claude processes first, Gemini processes Claude's output.
        """
        from ..executors import (
            ClaudeA2AExecutor,
            GeminiA2AExecutor,
        )

        # Set up Claude A2A server
        claude_executor = ClaudeA2AExecutor(
            model=ClaudeModels.MEDIUM,
            root_dir=str(_TEST_ROOT),
            mode="read-only",
        )
        claude_card = agent_card_from_definition(
            "claude-agent",
            {"name": "Claude", "description": "Claude agent"},
            port=10080,
        )
        claude_app = create_app(claude_executor, claude_card)
        claude_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=claude_app),
            base_url="http://localhost:10080",
        )

        # Set up Gemini A2A server
        gemini_executor = GeminiA2AExecutor(
            root_dir=_TEST_ROOT,
            model=GeminiModels.LOW,
            agent_name="vaultspec-researcher",
        )
        gemini_card = agent_card_from_definition(
            "gemini-agent",
            {"name": "Gemini", "description": "Gemini agent"},
            port=10081,
        )
        gemini_app = create_app(gemini_executor, gemini_card)
        gemini_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=gemini_app),
            base_url="http://localhost:10081",
        )

        async with claude_client, gemini_client:
            # Step 1: Send task to Claude
            logger.info("Sending request to Claude (%s)...", ClaudeModels.MEDIUM)
            start = time.monotonic()
            claude_resp = await claude_client.post(
                "/",
                json=_send_message_payload(
                    "Reply with exactly one word: CLAUDE_CONFIRMED"
                ),
            )
            claude_elapsed = time.monotonic() - start
            claude_body = claude_resp.json()
            claude_state = claude_body["result"]["status"]["state"]
            assert claude_state == "completed"
            claude_text = (
                claude_body["result"]["status"]
                .get("message", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            logger.info(
                "Response from Claude: state=%s, %.2fs", claude_state, claude_elapsed
            )

            # Step 2: Send Claude's output to Gemini for processing
            logger.info("Sending request to Gemini (%s)...", GeminiModels.LOW)
            start2 = time.monotonic()
            gemini_resp = await gemini_client.post(
                "/",
                json=_send_message_payload(
                    f"The following text was produced by Claude: '{claude_text}'. "
                    "Reply with exactly: GEMINI_RECEIVED_CLAUDE"
                ),
            )
            gemini_elapsed = time.monotonic() - start2
            gemini_body = gemini_resp.json()
            gemini_state = gemini_body["result"]["status"]["state"]
            assert gemini_state == "completed"
            gemini_text = (
                gemini_body["result"]["status"]
                .get("message", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            logger.info(
                "Response from Gemini: state=%s, %.2fs", gemini_state, gemini_elapsed
            )

            total_elapsed = claude_elapsed + gemini_elapsed

            assert "CLAUDE_CONFIRMED" in claude_text
            assert "GEMINI_RECEIVED_CLAUDE" in gemini_text

            logger.info(
                "Gemini-asks-Claude total: %.2fs (claude=%.2fs, gemini=%.2fs)",
                total_elapsed,
                claude_elapsed,
                gemini_elapsed,
            )
