"""Layer 2 — Integration tests for A2A HTTP server.

In-process HTTP via httpx.ASGITransport. No real TCP, no LLM.
Tests the full JSON-RPC request/response cycle through the Starlette app.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from a2a.types import AgentCard

from protocol.a2a.server import create_app
from protocol.a2a.tests.conftest import EchoExecutor, PrefixExecutor, _make_card


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


def _cancel_task_payload(task_id: str) -> dict:
    """Build a JSON-RPC 'tasks/cancel' request body."""
    return {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tasks/cancel",
        "params": {"id": task_id},
    }


def _get_task_payload(task_id: str) -> dict:
    """Build a JSON-RPC 'tasks/get' request body."""
    return {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tasks/get",
        "params": {"id": task_id},
    }


def _build_client(executor, name="test", port=10099) -> httpx.AsyncClient:
    """Build an httpx.AsyncClient backed by an in-process A2A ASGI app."""
    card = _make_card(name, port)
    app = create_app(executor, card)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=f"http://localhost:{port}",
    )


# ------------------------------------------------------------------
# Agent Card tests
# ------------------------------------------------------------------


@pytest.mark.integration
class TestAgentCardServed:
    @pytest.mark.asyncio
    async def test_agent_card_at_well_known(self):
        """GET /.well-known/agent-card.json returns valid card."""
        client = _build_client(EchoExecutor())
        async with client:
            resp = await client.get("/.well-known/agent-card.json")
            assert resp.status_code == 200
            data = resp.json()
            card = AgentCard.model_validate(data)
            assert card.name == "test"
            assert card.version == "0.1.0"
            assert len(card.skills) >= 1

    @pytest.mark.asyncio
    async def test_agent_card_backward_compat(self):
        """GET /.well-known/agent.json also works (deprecated path)."""
        client = _build_client(EchoExecutor())
        async with client:
            resp = await client.get("/.well-known/agent.json")
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "test"


# ------------------------------------------------------------------
# Message send tests
# ------------------------------------------------------------------


@pytest.mark.integration
class TestMessageSend:
    @pytest.mark.asyncio
    async def test_send_message_returns_completed_task(self):
        """POST / with message/send returns a completed Task."""
        client = _build_client(EchoExecutor())
        async with client:
            payload = _send_message_payload("Hello A2A")
            resp = await client.post("/", json=payload)
            assert resp.status_code == 200

            body = resp.json()
            assert body.get("jsonrpc") == "2.0"
            assert body.get("id") == 1
            result = body.get("result")
            assert result is not None
            assert result.get("status", {}).get("state") == "completed"

    @pytest.mark.asyncio
    async def test_echo_round_trip_integrity(self):
        """Input text survives full A2A encode->send->process->respond->decode."""
        test_text = "The quick brown fox jumps over the lazy dog."
        client = _build_client(EchoExecutor())
        async with client:
            payload = _send_message_payload(test_text)
            resp = await client.post("/", json=payload)
            body = resp.json()

            result = body["result"]
            # Check the completion message contains our echoed text
            message = result.get("status", {}).get("message", {})
            parts = message.get("parts", [])
            assert len(parts) >= 1
            response_text = parts[0].get("text", "")
            assert response_text == f"Echo: {test_text}"

    @pytest.mark.asyncio
    async def test_prefix_executor_through_http(self):
        """PrefixExecutor works correctly through the HTTP layer."""
        client = _build_client(PrefixExecutor("[Claude] "))
        async with client:
            payload = _send_message_payload("analyze code")
            resp = await client.post("/", json=payload)
            body = resp.json()

            result = body["result"]
            message = result.get("status", {}).get("message", {})
            parts = message.get("parts", [])
            assert parts[0]["text"] == "[Claude] analyze code"


# ------------------------------------------------------------------
# Bidirectional / multi-agent tests
# ------------------------------------------------------------------


@pytest.mark.integration
class TestBidirectional:
    @pytest.mark.asyncio
    async def test_two_agents_independent(self):
        """Two separate A2A agents both complete their tasks."""
        client_a = _build_client(
            PrefixExecutor("[AgentA] "), name="agent-a", port=10001
        )
        client_b = _build_client(
            PrefixExecutor("[AgentB] "), name="agent-b", port=10002
        )

        async with client_a, client_b:
            # Send to agent A
            payload_b = _send_message_payload("hello from B")
            resp_a = await client_a.post("/", json=payload_b)
            body_a = resp_a.json()
            assert body_a["result"]["status"]["state"] == "completed"
            msg_a = body_a["result"]["status"]["message"]["parts"][0]["text"]
            assert msg_a == "[AgentA] hello from B"

            # Send to agent B
            payload_a = _send_message_payload("hello from A")
            resp_b = await client_b.post("/", json=payload_a)
            body_b = resp_b.json()
            assert body_b["result"]["status"]["state"] == "completed"
            msg_b = body_b["result"]["status"]["message"]["parts"][0]["text"]
            assert msg_b == "[AgentB] hello from A"


# ------------------------------------------------------------------
# Task state / lifecycle tests
# ------------------------------------------------------------------


@pytest.mark.integration
class TestTaskLifecycle:
    @pytest.mark.asyncio
    async def test_task_has_status_history(self):
        """Completed task includes status with state=completed."""
        client = _build_client(EchoExecutor())
        async with client:
            payload = _send_message_payload("test state")
            resp = await client.post("/", json=payload)
            body = resp.json()

            result = body["result"]
            # Task should be in completed state
            assert result["status"]["state"] == "completed"
            # Task should have an id
            assert "id" in result
            # Task should have a contextId
            assert "contextId" in result

    @pytest.mark.asyncio
    async def test_get_task_after_completion(self):
        """tasks/get retrieves a previously completed task."""
        client = _build_client(EchoExecutor())
        async with client:
            # First, create a task via message/send
            send_resp = await client.post(
                "/", json=_send_message_payload("for retrieval")
            )
            send_body = send_resp.json()
            task_id = send_body["result"]["id"]

            # Then retrieve it via tasks/get
            get_resp = await client.post("/", json=_get_task_payload(task_id))
            get_body = get_resp.json()

            assert get_body.get("result") is not None
            assert get_body["result"]["id"] == task_id
            assert get_body["result"]["status"]["state"] == "completed"

    @pytest.mark.asyncio
    async def test_get_nonexistent_task_returns_error(self):
        """tasks/get for unknown task returns JSON-RPC error."""
        client = _build_client(EchoExecutor())
        async with client:
            get_resp = await client.post(
                "/", json=_get_task_payload("nonexistent-task-id")
            )
            get_body = get_resp.json()

            # Should be a JSON-RPC error response
            assert "error" in get_body
            assert get_body["error"]["code"] is not None

    @pytest.mark.asyncio
    async def test_cancel_completed_task_returns_error(self):
        """tasks/cancel on completed task returns not-cancelable error."""
        client = _build_client(EchoExecutor())
        async with client:
            # Create and complete a task
            send_resp = await client.post("/", json=_send_message_payload("to cancel"))
            task_id = send_resp.json()["result"]["id"]

            # Try to cancel the already-completed task
            cancel_resp = await client.post("/", json=_cancel_task_payload(task_id))
            cancel_body = cancel_resp.json()

            # Should be an error since task is already completed
            assert "error" in cancel_body


# ------------------------------------------------------------------
# Error handling tests
# ------------------------------------------------------------------


@pytest.mark.integration
class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_invalid_json_returns_parse_error(self):
        """Malformed JSON body returns JSON parse error."""
        client = _build_client(EchoExecutor())
        async with client:
            resp = await client.post(
                "/",
                content=b"not valid json{{{",
                headers={"content-type": "application/json"},
            )
            body = resp.json()
            assert "error" in body

    @pytest.mark.asyncio
    async def test_unknown_method_returns_error(self):
        """Unknown JSON-RPC method returns method-not-found error."""
        client = _build_client(EchoExecutor())
        async with client:
            payload = {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "nonexistent/method",
                "params": {},
            }
            resp = await client.post("/", json=payload)
            body = resp.json()
            assert "error" in body
