"""Unit and integration tests for the TeamCoordinator orchestration layer.

Phase 1: TeamSession model + TeamCoordinator skeleton tests.
Phase 2: dispatch_parallel, collect_results, relay_output tests.
Phase 4: ping_agents, timeout/degradation tests.
Phase 5: Integration test suite with @pytest.mark.team.

All mock tests use httpx.ASGITransport for in-process A2A apps.
No real TCP sockets are used in unit/integration tests.

ADR: .vault/adr/2026-02-20-a2a-team-adr.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart

from ...protocol.a2a import create_app
from ...protocol.a2a.tests.conftest import (
    EchoExecutor,
    PrefixExecutor,
    _make_card,
)
from ..team import (
    MemberStatus,
    TeamCoordinator,
    TeamStatus,
    extract_artifact_text,
)

if TYPE_CHECKING:
    from a2a.server.events import EventQueue


# ===================================================================
# Helpers — in-process A2A server factories
# ===================================================================


def _build_app_transport(
    executor: AgentExecutor, name: str, port: int
) -> httpx.ASGITransport:
    """Build an httpx.ASGITransport backed by an in-process A2A app."""
    card = _make_card(name, port)
    app = create_app(executor, card)
    return httpx.ASGITransport(app=app)


def _make_client_for(
    executor: AgentExecutor,
    name: str,
    port: int,
) -> tuple[httpx.AsyncClient, str]:
    """Return (httpx_client, base_url) for an in-process A2A app."""
    transport = _build_app_transport(executor, name, port)
    base_url = f"http://localhost:{port}"
    client = httpx.AsyncClient(transport=transport, base_url=base_url)
    return client, base_url


async def _build_coordinator_with_apps(
    executors: list[tuple[AgentExecutor, str, int]],
    name: str = "test-team",
    api_key: str | None = None,
) -> tuple[TeamCoordinator, list[str]]:
    """Bootstrap a TeamCoordinator with in-process agent apps.

    Returns (coordinator, agent_urls).  The coordinator's HTTP client is
    patched so that each agent URL is backed by an ASGITransport — no real
    sockets needed.

    The caller must call coordinator.dissolve_team() in teardown.
    """
    # Build per-agent transports and a mounts dict for httpx.AsyncClient
    mounts: dict[str, httpx.ASGITransport] = {}
    agent_urls: list[str] = []
    for executor, agent_name, port in executors:
        base_url = f"http://localhost:{port}"
        agent_urls.append(base_url + "/")
        mounts[f"http://localhost:{port}/"] = _build_app_transport(
            executor, agent_name, port
        )
        mounts[f"http://localhost:{port}"] = _build_app_transport(
            executor, agent_name, port
        )

    coordinator = TeamCoordinator(api_key=api_key)
    # Inject a single shared httpx.AsyncClient with per-host ASGITransport mounts
    coordinator._http_client = httpx.AsyncClient(mounts=mounts)
    await coordinator.form_team(name, agent_urls)
    return coordinator, agent_urls


# ===================================================================
# Phase 1 — TeamSession model + TeamCoordinator skeleton
# ===================================================================


@pytest.mark.team
@pytest.mark.asyncio
async def test_form_team_sets_context_id_equal_to_team_id():
    """Decision 2: team_id and context_id must be the same UUID."""
    coordinator, _ = await _build_coordinator_with_apps(
        [(EchoExecutor(), "echo-agent", 19901)],
        name="ctx-id-team",
    )
    try:
        session = coordinator.session
        assert session.team_id == session.context_id, (
            f"team_id={session.team_id!r} != context_id={session.context_id!r}"
        )
        assert len(session.team_id) == 36, "team_id must be a standard UUID string"
    finally:
        await coordinator.dissolve_team()


@pytest.mark.team
@pytest.mark.asyncio
async def test_team_status_transitions():
    """Session ACTIVE after form_team, DISSOLVED after dissolve_team."""
    coordinator, _ = await _build_coordinator_with_apps(
        [(EchoExecutor(), "echo-agent", 19902)],
        name="status-team",
    )
    session = coordinator.session
    assert session.status == TeamStatus.ACTIVE

    await coordinator.dissolve_team()
    assert session.status == TeamStatus.DISSOLVED


@pytest.mark.team
@pytest.mark.asyncio
async def test_dissolve_is_idempotent():
    """Calling dissolve_team() twice must not raise."""
    coordinator, _ = await _build_coordinator_with_apps(
        [(EchoExecutor(), "echo-agent", 19903)],
        name="idempotent-team",
    )
    await coordinator.dissolve_team()
    # Second call — must be a no-op
    await coordinator.dissolve_team()
    assert coordinator.session.status == TeamStatus.DISSOLVED


@pytest.mark.team
@pytest.mark.asyncio
async def test_member_status_on_form():
    """All members must be IDLE after form_team."""
    coordinator, _ = await _build_coordinator_with_apps(
        [
            (EchoExecutor(), "echo-a", 19904),
            (PrefixExecutor("[B] "), "prefix-b", 19905),
        ],
        name="member-status-team",
    )
    try:
        for member in coordinator.session.members.values():
            assert member.status == MemberStatus.IDLE, (
                f"Expected IDLE for {member.name!r}, got {member.status!r}"
            )
    finally:
        await coordinator.dissolve_team()


# ===================================================================
# Phase 2 — dispatch_parallel, collect_results, relay_output
# ===================================================================


@pytest.mark.team
@pytest.mark.asyncio
async def test_dispatch_parallel_fan_out():
    """dispatch_parallel must issue one task per agent and return Task objects."""
    coordinator, _ = await _build_coordinator_with_apps(
        [
            (EchoExecutor(), "echo-a", 19910),
            (PrefixExecutor("[B] "), "prefix-b", 19911),
        ],
        name="fan-out-team",
    )
    try:
        session = coordinator.session
        agent_names = list(session.members.keys())
        assert len(agent_names) == 2

        assignments = {agent_names[0]: "task for A", agent_names[1]: "task for B"}
        results = await coordinator.dispatch_parallel(assignments)

        assert len(results) == 2
        for _name, task in results.items():
            assert task is not None
            # Each Task must carry the team_id as context_id (Decision 2)
            assert task.context_id == session.team_id, (
                f"Task context_id {task.context_id!r} != team_id {session.team_id!r}"
            )
    finally:
        await coordinator.dissolve_team()


@pytest.mark.team
@pytest.mark.asyncio
async def test_collect_results_all_complete():
    """collect_results must extract artifact text from all completed tasks."""
    coordinator, _ = await _build_coordinator_with_apps(
        [
            (EchoExecutor(), "echo-a", 19912),
            (PrefixExecutor("[Pre] "), "prefix-b", 19913),
        ],
        name="collect-team",
    )
    try:
        session = coordinator.session
        agent_names = list(session.members.keys())

        assignments = {
            agent_names[0]: "hello world",
            agent_names[1]: "collect test",
        }
        await coordinator.dispatch_parallel(assignments)
        results = await coordinator.collect_results()

        assert len(results) == 2
        for name, text in results.items():
            assert isinstance(text, str)
            assert len(text) > 0, f"Empty result text for agent {name!r}"
    finally:
        await coordinator.dissolve_team()


@pytest.mark.team
@pytest.mark.asyncio
async def test_relay_output_injects_reference_task_id():
    """relay_output must set reference_task_ids=[src_task.id] on the outbound message.

    Decision 5: coordinator injects reference_task_ids into the relay message.
    We verify this by subclassing EchoExecutor to capture what reference_task_ids
    the server sees on the inbound message.
    """
    captured_ref_ids: list[list[str]] = []

    class CapturingExecutor(AgentExecutor):
        async def execute(
            self, context: RequestContext, event_queue: EventQueue
        ) -> None:
            assert context.task_id is not None
            assert context.context_id is not None
            updater = TaskUpdater(event_queue, context.task_id, context.context_id)
            # Capture the reference_task_ids from the inbound message
            msg = context.message
            captured_ref_ids.append(list(msg.reference_task_ids or []))  # type: ignore[union-attr]
            text = context.get_user_input()
            await updater.start_work()
            await updater.complete(
                message=updater.new_agent_message(
                    parts=[Part(root=TextPart(text=f"Relay: {text}"))]
                )
            )

        async def cancel(
            self, context: RequestContext, event_queue: EventQueue
        ) -> None:
            assert context.task_id is not None
            assert context.context_id is not None
            updater = TaskUpdater(event_queue, context.task_id, context.context_id)
            await updater.cancel()

    coordinator, _ = await _build_coordinator_with_apps(
        [
            (EchoExecutor(), "echo-src", 19920),
            (CapturingExecutor(), "capture-dst", 19921),
        ],
        name="relay-team",
    )
    try:
        session = coordinator.session
        agent_names = list(session.members.keys())
        src_name, dst_name = agent_names[0], agent_names[1]

        # Dispatch to source agent first
        src_tasks = await coordinator.dispatch_parallel({src_name: "source task"})
        src_task = src_tasks[src_name]

        # Relay src output to destination agent
        await coordinator.relay_output(src_task, dst_name, "process the above")

        # CapturingExecutor must have seen reference_task_ids containing src_task.id
        assert len(captured_ref_ids) == 1, (
            "CapturingExecutor should have been called once"
        )
        assert src_task.id in captured_ref_ids[0], (
            f"Expected src_task.id {src_task.id!r} in reference_task_ids "
            f"but got {captured_ref_ids[0]!r}"
        )
    finally:
        await coordinator.dissolve_team()


@pytest.mark.team
@pytest.mark.asyncio
async def test_dispatch_parallel_partial_failure():
    """dispatch_parallel must tolerate per-agent errors and return partial results."""
    coordinator, _ = await _build_coordinator_with_apps(
        [(EchoExecutor(), "echo-ok", 19930)],
        name="partial-fail-team",
    )
    try:
        session = coordinator.session
        good_agent = next(iter(session.members.keys()))

        # Inject a fake non-existent member to simulate failure
        from a2a.types import AgentCapabilities, AgentCard, AgentSkill

        from ..team import MemberStatus, TeamMember

        bad_card = AgentCard(
            name="bad-agent",
            url="http://localhost:19931/",
            version="0.1.0",
            description="Non-existent agent",
            default_input_modes=["text"],
            default_output_modes=["text"],
            capabilities=AgentCapabilities(streaming=False),
            skills=[AgentSkill(id="x", name="X", description="X", tags=[])],
        )
        session.members["bad-agent"] = TeamMember(
            name="bad-agent",
            url="http://localhost:19931/",
            card=bad_card,
            status=MemberStatus.IDLE,
        )

        assignments = {
            good_agent: "good task",
            "bad-agent": "bad task",
        }
        results = await coordinator.dispatch_parallel(assignments)

        # good_agent must succeed; bad-agent may fail (partial result acceptable)
        assert good_agent in results
        assert results[good_agent].status.state.value == "completed"
    finally:
        await coordinator.dissolve_team()


# ===================================================================
# Phase 4 — ping_agents, timeout/degradation
# ===================================================================


@pytest.mark.team
@pytest.mark.asyncio
async def test_ping_agents_reachable():
    """ping_agents returns True for all reachable members."""
    coordinator, _ = await _build_coordinator_with_apps(
        [(EchoExecutor(), "echo-ping", 19940)],
        name="ping-team",
    )
    try:
        reachability = await coordinator.ping_agents()
        assert len(reachability) == 1
        for name, reachable in reachability.items():
            assert reachable, f"Expected {name!r} to be reachable"
    finally:
        await coordinator.dissolve_team()


@pytest.mark.team
@pytest.mark.asyncio
async def test_ping_agents_unreachable_returns_false():
    """ping_agents returns False for agents with non-existent URLs."""
    coordinator, _ = await _build_coordinator_with_apps(
        [(EchoExecutor(), "echo-real", 19941)],
        name="unreachable-ping-team",
    )
    try:
        session = coordinator.session
        from a2a.types import AgentCapabilities, AgentCard, AgentSkill

        from ..team import MemberStatus, TeamMember

        ghost_card = AgentCard(
            name="ghost-agent",
            url="http://localhost:19942/",
            version="0.1.0",
            description="Non-existent agent",
            default_input_modes=["text"],
            default_output_modes=["text"],
            capabilities=AgentCapabilities(streaming=False),
            skills=[AgentSkill(id="x", name="X", description="X", tags=[])],
        )
        session.members["ghost-agent"] = TeamMember(
            name="ghost-agent",
            url="http://localhost:19942/",
            card=ghost_card,
            status=MemberStatus.IDLE,
        )

        reachability = await coordinator.ping_agents()
        assert reachability.get("ghost-agent") is False, (
            "Expected ghost-agent to be unreachable"
        )
    finally:
        await coordinator.dissolve_team()


@pytest.mark.team
@pytest.mark.asyncio
async def test_dispatch_parallel_degrades_gracefully_on_failure():
    """dispatch_parallel omits failing agents and resets their status to IDLE."""

    class FailingExecutor(AgentExecutor):
        """Immediately raises — simulates a crashed or unreachable agent."""

        async def execute(
            self,
            context: RequestContext,
            event_queue: EventQueue,
        ) -> None:
            raise RuntimeError("simulated agent failure")

        async def cancel(
            self, context: RequestContext, event_queue: EventQueue
        ) -> None:
            pass

    coordinator, _ = await _build_coordinator_with_apps(
        [
            (EchoExecutor(), "echo-fast", 19950),
            (FailingExecutor(), "broken-agent", 19951),
        ],
        name="degrade-team",
    )
    try:
        results = await coordinator.dispatch_parallel(
            {"echo-fast": "quick task", "broken-agent": "this will fail"}
        )
        assert "echo-fast" in results, "fast agent must appear in results"
        assert "broken-agent" not in results, "failed agent must be omitted"
        # Failed member must NOT be stuck at WORKING — status must be reset to IDLE
        assert coordinator.session.members["broken-agent"].status == MemberStatus.IDLE
    finally:
        await coordinator.dissolve_team()


# ===================================================================
# Phase 5 — Integration test suite
# ===================================================================


@pytest.mark.integration
@pytest.mark.team
class TestTwoAgentParallelDispatchIntegration:
    """Integration: two-agent parallel dispatch with EchoExecutor + PrefixExecutor."""

    @pytest.mark.asyncio
    async def test_two_agent_parallel_dispatch(self):
        """Both agents complete; contextId matches team_id on both tasks."""
        coordinator, _ = await _build_coordinator_with_apps(
            [
                (EchoExecutor(), "echo-int", 19960),
                (PrefixExecutor("[P] "), "prefix-int", 19961),
            ],
            name="integration-team",
        )
        try:
            session = coordinator.session
            agent_names = list(session.members.keys())
            assert len(agent_names) == 2

            assignments = {
                agent_names[0]: "integration task A",
                agent_names[1]: "integration task B",
            }
            results = await coordinator.dispatch_parallel(assignments)

            assert len(results) == 2
            task_ids = set()
            for _name, task in results.items():
                assert task.status.state.value == "completed"
                # Decision 2: contextId == team_id
                assert task.context_id == session.team_id, (
                    f"context_id {task.context_id!r} != team_id {session.team_id!r}"
                )
                task_ids.add(task.id)

            # Two tasks must have distinct IDs
            assert len(task_ids) == 2, "Task IDs must be unique per agent"
        finally:
            await coordinator.dissolve_team()


@pytest.mark.integration
@pytest.mark.team
class TestRelayChainIntegration:
    """Integration: two-agent relay chain with reference_task_ids assertion."""

    @pytest.mark.asyncio
    async def test_relay_chain(self):
        """Agent A dispatched, A's output relayed to B; reference_task_ids verified."""
        captured_ref_ids: list[list[str]] = []

        class RefCapturingExecutor(AgentExecutor):
            async def execute(
                self, context: RequestContext, event_queue: EventQueue
            ) -> None:
                assert context.task_id is not None
                assert context.context_id is not None
                updater = TaskUpdater(event_queue, context.task_id, context.context_id)
                msg = context.message
                captured_ref_ids.append(list(msg.reference_task_ids or []))  # type: ignore[union-attr]
                text = context.get_user_input()
                await updater.start_work()
                await updater.complete(
                    message=updater.new_agent_message(
                        parts=[Part(root=TextPart(text=f"B received: {text}"))]
                    )
                )

            async def cancel(
                self, context: RequestContext, event_queue: EventQueue
            ) -> None:
                assert context.task_id is not None
                assert context.context_id is not None
                updater = TaskUpdater(event_queue, context.task_id, context.context_id)
                await updater.cancel()

        coordinator, _ = await _build_coordinator_with_apps(
            [
                (EchoExecutor(), "echo-relay-a", 19970),
                (RefCapturingExecutor(), "relay-b", 19971),
            ],
            name="relay-chain-team",
        )
        try:
            session = coordinator.session
            agent_names = list(session.members.keys())
            agent_a, agent_b = agent_names[0], agent_names[1]

            # Dispatch to agent A
            tasks_a = await coordinator.dispatch_parallel({agent_a: "relay source"})
            task_a = tasks_a[agent_a]
            assert task_a.status.state.value == "completed"

            # Relay A's output to B
            task_b = await coordinator.relay_output(task_a, agent_b, "process this")
            assert task_b.status.state.value == "completed"

            # B must have received reference_task_ids with A's task ID (Decision 5)
            assert len(captured_ref_ids) == 1
            assert task_a.id in captured_ref_ids[0], (
                f"Expected task_a.id {task_a.id!r} in reference_task_ids "
                f"but got {captured_ref_ids[0]!r}"
            )

            # B's response text must contain A's echoed output
            b_text = extract_artifact_text(task_b)
            assert len(b_text) > 0, "Agent B response text must be non-empty"
        finally:
            await coordinator.dissolve_team()
