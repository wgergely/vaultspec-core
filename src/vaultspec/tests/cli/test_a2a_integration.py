"""Integration tests for A2A executor pipeline.

Formalizes three scenarios proven working in live CLI tests:

1. Multi-agent dispatch: two executors, URL-keyed routing, independent completion.
2. Multi-turn session resume: same context_id across turns, SDK client persistence.
3. Mixed-provider team: Claude + Gemini executors, both complete independently.

No mocks, patches, or stubs. Real executor classes with DI test doubles injected
via the ``client_factory``/``options_factory`` (Claude) and ``run_subagent``
(Gemini) constructor parameters.

These tests operate at the in-process ASGI layer via httpx.ASGITransport, so no
real TCP sockets or LLM calls are required.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from a2a.types import TaskState, TaskStatusUpdateEvent
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from ...orchestration import (
    TeamCoordinator,
    extract_artifact_text,
)
from ...protocol.a2a import create_app
from ...protocol.a2a.executors import ClaudeA2AExecutor, GeminiA2AExecutor
from ...protocol.a2a.tests.conftest import (
    _make_card,
)
from ...protocol.acp import SubagentResult
from ...protocol.providers import ClaudeModels, GeminiModels


class _AwaitableNone:
    """Object that can be awaited (returns None)."""

    def __await__(self):
        return iter([])


class _InProcessSDKClient:
    """In-process Claude SDK client double for DI injection.

    Yields pre-built real SDK messages (AssistantMessage, ResultMessage,
    TextBlock) so the executor's isinstance checks work without any patching.

    Supports multiple message rounds for multi-turn testing: pass
    ``message_rounds`` (list of lists) to provide one sequence per turn.
    """

    def __init__(
        self,
        messages: list[Any] | None = None,
        connect_error: Exception | None = None,
        message_rounds: list[list[Any]] | None = None,
    ):
        self._message_rounds: list[list[Any]] = (
            message_rounds if message_rounds is not None else [messages or []]
        )
        self._round_idx = 0
        self.connect_error = connect_error
        self.connect_calls: list[tuple] = []
        self.query_calls: list[str] = []
        self.disconnect_calls: int = 0
        self.interrupt_calls: int = 0

    async def connect(self, *args: Any, **kwargs: Any) -> None:
        self.connect_calls.append((args, kwargs))
        if self.connect_error:
            raise self.connect_error

    async def query(self, prompt: str) -> None:
        self.query_calls.append(prompt)

    def disconnect(self) -> _AwaitableNone:
        self.disconnect_calls += 1
        return _AwaitableNone()

    async def interrupt(self) -> None:
        self.interrupt_calls += 1

    def receive_messages(self):
        return self.receive_response()

    def receive_response(self):
        idx = min(self._round_idx, len(self._message_rounds) - 1)
        self._round_idx += 1
        return _async_iter(self._message_rounds[idx])


async def _async_iter(items: list[Any]):
    """Yield items from a list as an async iterator."""
    for item in items:
        if isinstance(item, Exception):
            raise item
        yield item


def _make_result(
    *,
    result: str | None = None,
    is_error: bool = False,
    session_id: str = "test-session",
) -> ResultMessage:
    """Build a real ResultMessage with sensible defaults."""
    return ResultMessage(
        subtype="result",
        duration_ms=0,
        duration_api_ms=0,
        is_error=is_error,
        num_turns=1,
        session_id=session_id,
        result=result,
    )


def _drain_events(queue) -> list[Any]:
    """Drain all events from an EventQueue, calling task_done() for each."""
    events = []
    while not queue.queue.empty():
        events.append(queue.queue.get_nowait())
        queue.task_done()
    return events


def _build_app_transport(executor, name: str, port: int) -> httpx.ASGITransport:
    """Build an httpx.ASGITransport backed by an in-process A2A app."""
    card = _make_card(name, port)
    app = create_app(executor, card)
    return httpx.ASGITransport(app=app)


async def _build_coordinator_with_apps(
    executors: list[tuple[Any, str, int]],
    name: str = "test-team",
) -> tuple[TeamCoordinator, list[str]]:
    """Bootstrap a TeamCoordinator with in-process ASGI agent apps.

    Returns (coordinator, agent_urls). The coordinator's HTTP client is
    configured with per-host ASGITransport mounts so agent card discovery
    and message dispatch go through the real A2A server stack.
    """
    mounts: dict[str, httpx.ASGITransport] = {}
    agent_urls: list[str] = []
    for executor, agent_name, port in executors:
        base_url = f"http://localhost:{port}"
        agent_urls.append(base_url + "/")
        transport = _build_app_transport(executor, agent_name, port)
        mounts[f"http://localhost:{port}/"] = transport
        mounts[f"http://localhost:{port}"] = transport

    coordinator = TeamCoordinator()
    coordinator._http_client = httpx.AsyncClient(mounts=mounts)
    await coordinator.form_team(name, agent_urls)
    return coordinator, agent_urls


def _make_claude_executor(
    sdk_client: _InProcessSDKClient,
    root_dir: str = "/tmp",
) -> ClaudeA2AExecutor:
    """Build a ClaudeA2AExecutor with DI'd in-process SDK client."""
    return ClaudeA2AExecutor(
        model=ClaudeModels.MEDIUM,
        root_dir=root_dir,
        mode="read-only",
        client_factory=lambda _opts: sdk_client,
        options_factory=lambda **kwargs: kwargs,
        max_retries=0,
        retry_base_delay=0.0,
    )


class _RunSubagentRecorder:
    """Records calls and returns a preset SubagentResult for DI injection."""

    def __init__(self, result: SubagentResult | None = None):
        self.result = result or SubagentResult(
            session_id="test-session",
            response_text="Gemini response",
            written_files=[],
        )
        self.calls: list[dict] = []

    async def __call__(self, **kwargs: Any) -> SubagentResult:
        self.calls.append(kwargs)
        return self.result


@pytest.mark.integration
class TestA2AMultiAgentDispatch:
    """Two A2A agents in one team, URL-keyed routing, independent completion.

    Proves the scenario from live CLI test: two executor instances backed by
    the same in-process A2A stack, team coordinator routes tasks by URL, both
    complete with the correct response.
    """

    @pytest.mark.asyncio
    async def test_two_claude_agents_independent_dispatch(self):
        """Two ClaudeA2AExecutors, different tasks, both complete correctly."""
        client_a = _InProcessSDKClient(
            message_rounds=[
                [
                    AssistantMessage(
                        content=[TextBlock(text="Agent A answer")],
                        model=ClaudeModels.MEDIUM,
                    ),
                    _make_result(result=None, is_error=False, session_id="sess-a"),
                ]
            ]
        )
        client_b = _InProcessSDKClient(
            message_rounds=[
                [
                    AssistantMessage(
                        content=[TextBlock(text="Agent B answer")],
                        model=ClaudeModels.MEDIUM,
                    ),
                    _make_result(result=None, is_error=False, session_id="sess-b"),
                ]
            ]
        )

        executor_a = _make_claude_executor(client_a)
        executor_b = _make_claude_executor(client_b)

        coordinator, agent_urls = await _build_coordinator_with_apps(
            [
                (executor_a, "claude-a", 30100),
                (executor_b, "claude-b", 30101),
            ],
            name="multi-agent-team",
        )
        try:
            session = coordinator.session
            # Members are keyed by URL.
            assert len(session.members) == 2

            url_a = next(u for u in agent_urls if "30100" in u)
            url_b = next(u for u in agent_urls if "30101" in u)

            results = await coordinator.dispatch_parallel(
                {url_a: "task for A", url_b: "task for B"}
            )

            assert len(results) == 2

            task_a = results[url_a]
            task_b = results[url_b]

            assert task_a.status.state == TaskState.completed
            assert task_b.status.state == TaskState.completed

            # Both share the same team context_id.
            assert task_a.context_id == session.team_id
            assert task_b.context_id == session.team_id

            text_a = extract_artifact_text(task_a)
            text_b = extract_artifact_text(task_b)
            assert "Agent A answer" in text_a
            assert "Agent B answer" in text_b

            # Each agent received exactly one query with its own task text.
            assert client_a.query_calls == ["task for A"]
            assert client_b.query_calls == ["task for B"]

        finally:
            await coordinator.dissolve_team()

    @pytest.mark.asyncio
    async def test_url_routing_dispatches_to_correct_agent(self):
        """URL-keyed routing sends each task to the intended executor only."""
        client_a = _InProcessSDKClient(
            messages=[
                AssistantMessage(
                    content=[TextBlock(text="A handled this")],
                    model=ClaudeModels.MEDIUM,
                ),
                _make_result(is_error=False, session_id="sess-route-a"),
            ]
        )
        client_b = _InProcessSDKClient(
            messages=[
                AssistantMessage(
                    content=[TextBlock(text="B handled this")],
                    model=ClaudeModels.MEDIUM,
                ),
                _make_result(is_error=False, session_id="sess-route-b"),
            ]
        )

        coordinator, agent_urls = await _build_coordinator_with_apps(
            [
                (_make_claude_executor(client_a), "route-a", 30102),
                (_make_claude_executor(client_b), "route-b", 30103),
            ],
            name="route-team",
        )
        try:
            url_a = next(u for u in agent_urls if "30102" in u)
            url_b = next(u for u in agent_urls if "30103" in u)

            # Only dispatch to agent A.
            results = await coordinator.dispatch_parallel({url_a: "only A"})

            assert len(results) == 1
            task = results[url_a]
            assert task.status.state == TaskState.completed

            # Agent B received no calls.
            assert len(client_a.query_calls) == 1
            assert len(client_b.query_calls) == 0

        finally:
            await coordinator.dissolve_team()

    @pytest.mark.asyncio
    async def test_multi_agent_team_creation_and_member_count(self):
        """Team forms correctly with two Claude agent members."""
        client_a = _InProcessSDKClient(
            messages=[_make_result(result="ok-a", is_error=False, session_id="s-a")]
        )
        client_b = _InProcessSDKClient(
            messages=[_make_result(result="ok-b", is_error=False, session_id="s-b")]
        )

        coordinator, agent_urls = await _build_coordinator_with_apps(
            [
                (_make_claude_executor(client_a), "member-a", 30104),
                (_make_claude_executor(client_b), "member-b", 30105),
            ],
            name="member-count-team",
        )
        try:
            session = coordinator.session
            # Exactly two URL-keyed members.
            assert len(session.members) == 2
            member_urls = set(session.members.keys())
            for url in agent_urls:
                assert url in member_urls

        finally:
            await coordinator.dissolve_team()


@pytest.mark.integration
class TestA2AMultiTurnSessionResume:
    """Same context_id across two turns exercises SDK client persistence.

    Proves the Task #41 fix: after turn 1 completes, the executor stores
    the live SDK client under context_id in ``_active_clients``.  Turn 2
    on the same context_id reuses that client (no new connect() call).
    """

    @pytest.mark.asyncio
    async def test_client_persisted_after_first_turn(self):
        """After turn 1 completes, SDK client is stored under context_id."""
        from a2a.server.events import EventQueue

        from ...protocol.a2a.tests.conftest import make_request_context

        sdk_client = _InProcessSDKClient(
            message_rounds=[
                [
                    AssistantMessage(
                        content=[TextBlock(text="Turn 1 answer")],
                        model=ClaudeModels.MEDIUM,
                    ),
                    _make_result(result=None, is_error=False, session_id="sess-turn1"),
                ],
                [
                    AssistantMessage(
                        content=[TextBlock(text="Turn 2 answer")],
                        model=ClaudeModels.MEDIUM,
                    ),
                    _make_result(result=None, is_error=False, session_id="sess-turn2"),
                ],
            ]
        )

        executor = _make_claude_executor(sdk_client)

        # Turn 1: fresh context.
        queue1 = EventQueue()
        ctx1 = make_request_context(
            "What is the capital of France?",
            task_id="task-turn1",
            context_id="ctx-multi-turn",
        )
        await executor.execute(ctx1, queue1)
        _drain_events(queue1)
        await queue1.close()

        # After completion, client is stored under context_id.
        assert "ctx-multi-turn" in executor._active_clients
        stored_client = executor._active_clients["ctx-multi-turn"]
        assert stored_client is sdk_client

        # Exactly one connect() call for turn 1.
        assert len(sdk_client.connect_calls) == 1

    @pytest.mark.asyncio
    async def test_second_turn_reuses_client_without_reconnect(self):
        """Turn 2 on the same context_id reuses the stored client — no new connect()."""
        from a2a.server.events import EventQueue

        from ...protocol.a2a.tests.conftest import make_request_context

        sdk_client = _InProcessSDKClient(
            message_rounds=[
                [
                    AssistantMessage(
                        content=[
                            TextBlock(text="First: Paris is the capital of France.")
                        ],
                        model=ClaudeModels.MEDIUM,
                    ),
                    _make_result(
                        result=None, is_error=False, session_id="sess-multi-A"
                    ),
                ],
                [
                    AssistantMessage(
                        content=[
                            TextBlock(text="Second: You asked about France before.")
                        ],
                        model=ClaudeModels.MEDIUM,
                    ),
                    _make_result(
                        result=None, is_error=False, session_id="sess-multi-B"
                    ),
                ],
            ]
        )

        executor = _make_claude_executor(sdk_client)

        shared_context_id = "ctx-resume-shared"

        # Turn 1.
        queue1 = EventQueue()
        ctx1 = make_request_context(
            "What is the capital of France?",
            task_id="task-a",
            context_id=shared_context_id,
        )
        await executor.execute(ctx1, queue1)
        _drain_events(queue1)
        await queue1.close()

        # Verify client stored.
        assert shared_context_id in executor._active_clients

        # Turn 2: same context_id, different task_id.
        queue2 = EventQueue()
        ctx2 = make_request_context(
            "What did I ask you about before?",
            task_id="task-b",
            context_id=shared_context_id,
        )
        await executor.execute(ctx2, queue2)
        events2 = _drain_events(queue2)
        await queue2.close()

        # Still exactly one connect() — turn 2 reused the existing client.
        assert len(sdk_client.connect_calls) == 1

        # Turn 2 completed successfully.
        status_events = [e for e in events2 if isinstance(e, TaskStatusUpdateEvent)]
        assert status_events[-1].status.state == TaskState.completed

        # Both queries were sent.
        assert len(sdk_client.query_calls) == 2
        assert sdk_client.query_calls[0] == "What is the capital of France?"
        assert sdk_client.query_calls[1] == "What did I ask you about before?"

    @pytest.mark.asyncio
    async def test_second_turn_response_can_reference_first_turn(self):
        """Turn 2 response content demonstrates contextual continuity."""
        from a2a.server.events import EventQueue

        from ...protocol.a2a.tests.conftest import make_request_context

        # Turn 2's response text explicitly references turn 1's content.
        sdk_client = _InProcessSDKClient(
            message_rounds=[
                [
                    _make_result(result="Paris", is_error=False, session_id="s-ref-1"),
                ],
                [
                    _make_result(
                        result="You previously asked about the capital of France.",
                        is_error=False,
                        session_id="s-ref-2",
                    ),
                ],
            ]
        )

        executor = _make_claude_executor(sdk_client)
        ctx_id = "ctx-contextual"

        queue1 = EventQueue()
        ctx1 = make_request_context(
            "capital of France", task_id="t-ref-1", context_id=ctx_id
        )
        await executor.execute(ctx1, queue1)
        _drain_events(queue1)
        await queue1.close()

        queue2 = EventQueue()
        ctx2 = make_request_context(
            "what did I ask before?", task_id="t-ref-2", context_id=ctx_id
        )
        await executor.execute(ctx2, queue2)
        events2 = _drain_events(queue2)
        await queue2.close()

        status_events = [e for e in events2 if isinstance(e, TaskStatusUpdateEvent)]
        last = status_events[-1]
        assert last.status.state == TaskState.completed

        # The response should reference the first turn's content.
        response_text = last.status.message.parts[0].root.text
        assert "France" in response_text or "previously" in response_text

    @pytest.mark.asyncio
    async def test_different_context_ids_get_independent_clients(self):
        """Two concurrent contexts each get their own client instance."""
        from a2a.server.events import EventQueue

        from ...protocol.a2a.tests.conftest import make_request_context

        client_x = _InProcessSDKClient(
            messages=[_make_result(result="x-done", is_error=False, session_id="s-x")]
        )
        client_y = _InProcessSDKClient(
            messages=[_make_result(result="y-done", is_error=False, session_id="s-y")]
        )

        call_count = 0

        def factory_fn(_opts: Any) -> _InProcessSDKClient:
            nonlocal call_count
            call_count += 1
            return client_x if call_count == 1 else client_y

        executor = ClaudeA2AExecutor(
            model=ClaudeModels.MEDIUM,
            root_dir="/tmp",
            mode="read-only",
            client_factory=factory_fn,
            options_factory=lambda **kwargs: kwargs,
            max_retries=0,
            retry_base_delay=0.0,
        )

        queue_x = EventQueue()
        queue_y = EventQueue()

        await asyncio.gather(
            executor.execute(
                make_request_context("task x", task_id="t-x", context_id="ctx-x"),
                queue_x,
            ),
            executor.execute(
                make_request_context("task y", task_id="t-y", context_id="ctx-y"),
                queue_y,
            ),
        )

        ex = _drain_events(queue_x)
        ey = _drain_events(queue_y)
        await queue_x.close()
        await queue_y.close()

        # Both contexts have their own stored client.
        assert "ctx-x" in executor._active_clients
        assert "ctx-y" in executor._active_clients
        assert (
            executor._active_clients["ctx-x"] is not executor._active_clients["ctx-y"]
        )

        assert [e for e in ex if isinstance(e, TaskStatusUpdateEvent)][
            -1
        ].status.state == TaskState.completed
        assert [e for e in ey if isinstance(e, TaskStatusUpdateEvent)][
            -1
        ].status.state == TaskState.completed


@pytest.mark.integration
class TestA2AMixedProviderTeam:
    """One Claude + one Gemini executor in the same team.

    Proves the mixed-provider scenario from live CLI testing: heterogeneous
    executors coexist in one TeamCoordinator, URL routing selects the right
    executor, both complete independently without cross-contamination.
    """

    @pytest.mark.asyncio
    async def test_claude_and_gemini_both_complete(self):
        """Claude executor and Gemini executor both complete their tasks."""
        claude_client = _InProcessSDKClient(
            messages=[
                AssistantMessage(
                    content=[TextBlock(text="Claude says hello")],
                    model=ClaudeModels.MEDIUM,
                ),
                _make_result(result=None, is_error=False, session_id="sess-claude"),
            ]
        )
        claude_executor = _make_claude_executor(claude_client)

        gemini_recorder = _RunSubagentRecorder(
            result=SubagentResult(
                session_id="gemini-session",
                response_text="Gemini says hello",
                written_files=[],
            )
        )
        gemini_executor = GeminiA2AExecutor(
            root_dir=__import__("pathlib").Path("/tmp"),
            model=GeminiModels.LOW,
            agent_name="test-agent",
            run_subagent=gemini_recorder,
        )

        coordinator, agent_urls = await _build_coordinator_with_apps(
            [
                (claude_executor, "claude-provider", 30200),
                (gemini_executor, "gemini-provider", 30201),
            ],
            name="mixed-team",
        )
        try:
            session = coordinator.session
            assert len(session.members) == 2

            claude_url = next(u for u in agent_urls if "30200" in u)
            gemini_url = next(u for u in agent_urls if "30201" in u)

            results = await coordinator.dispatch_parallel(
                {
                    claude_url: "Hello from team to Claude",
                    gemini_url: "Hello from team to Gemini",
                }
            )

            assert len(results) == 2
            task_claude = results[claude_url]
            task_gemini = results[gemini_url]

            assert task_claude.status.state == TaskState.completed
            assert task_gemini.status.state == TaskState.completed

            # Both share the team context_id.
            assert task_claude.context_id == session.team_id
            assert task_gemini.context_id == session.team_id

            claude_text = extract_artifact_text(task_claude)
            gemini_text = extract_artifact_text(task_gemini)

            assert "Claude" in claude_text
            assert "Gemini" in gemini_text

            # No cross-contamination: Claude's client got exactly one query.
            assert claude_client.query_calls == ["Hello from team to Claude"]
            # Gemini's recorder got exactly one call.
            assert len(gemini_recorder.calls) == 1
            assert (
                gemini_recorder.calls[0]["initial_task"] == "Hello from team to Gemini"
            )

        finally:
            await coordinator.dissolve_team()

    @pytest.mark.asyncio
    async def test_mixed_team_no_cross_contamination(self):
        """Routing to Claude does not invoke Gemini and vice versa."""
        claude_client = _InProcessSDKClient(
            messages=[
                _make_result(result="claude only", is_error=False, session_id="s-cc")
            ]
        )
        claude_executor = _make_claude_executor(claude_client)

        gemini_recorder = _RunSubagentRecorder(
            result=SubagentResult(
                session_id=None,
                response_text="gemini only",
                written_files=[],
            )
        )
        gemini_executor = GeminiA2AExecutor(
            root_dir=__import__("pathlib").Path("/tmp"),
            model=GeminiModels.LOW,
            agent_name="test-agent",
            run_subagent=gemini_recorder,
        )

        coordinator, agent_urls = await _build_coordinator_with_apps(
            [
                (claude_executor, "cc-claude", 30202),
                (gemini_executor, "cc-gemini", 30203),
            ],
            name="no-cross-team",
        )
        try:
            claude_url = next(u for u in agent_urls if "30202" in u)
            gemini_url = next(u for u in agent_urls if "30203" in u)

            # Dispatch only to Claude.
            results = await coordinator.dispatch_parallel(
                {claude_url: "only for claude"}
            )

            assert len(results) == 1
            assert results[claude_url].status.state == TaskState.completed

            # Gemini received zero calls.
            assert len(gemini_recorder.calls) == 0
            assert len(claude_client.query_calls) == 1

            # Now dispatch only to Gemini.
            results2 = await coordinator.dispatch_parallel(
                {gemini_url: "only for gemini"}
            )

            assert len(results2) == 1
            assert results2[gemini_url].status.state == TaskState.completed

            # Claude received no additional calls.
            assert len(claude_client.query_calls) == 1
            assert len(gemini_recorder.calls) == 1

        finally:
            await coordinator.dissolve_team()

    @pytest.mark.asyncio
    async def test_mixed_team_member_identity_preserved(self):
        """Each member retains its display_name from AgentCard after team formation."""
        claude_executor = _make_claude_executor(
            _InProcessSDKClient(
                messages=[_make_result(result="ok", is_error=False, session_id="s-id")]
            )
        )
        gemini_executor = GeminiA2AExecutor(
            root_dir=__import__("pathlib").Path("/tmp"),
            model=GeminiModels.LOW,
            agent_name="test-agent",
            run_subagent=_RunSubagentRecorder(),
        )

        coordinator, _ = await _build_coordinator_with_apps(
            [
                (claude_executor, "identity-claude", 30204),
                (gemini_executor, "identity-gemini", 30205),
            ],
            name="identity-team",
        )
        try:
            session = coordinator.session
            display_names = {m.display_name for m in session.members.values()}
            assert "identity-claude" in display_names
            assert "identity-gemini" in display_names

        finally:
            await coordinator.dissolve_team()
