"""Multi-agent team coordination layer.

Provides TeamCoordinator, TeamSession, TeamMember, and associated enums for
orchestrating N-agent A2A teams. Operates above the A2A transport layer,
using A2AClient and A2ACardResolver as the transport primitives.

ADR: .vault/adr/2026-02-20-a2a-team-adr.md
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    CancelTaskRequest,
    GetTaskRequest,
    JSONRPCErrorResponse,
    Message,
    MessageSendParams,
    Part,
    Role,
    SendMessageRequest,
    Task,
    TaskIdParams,
    TaskQueryParams,
    TaskState,
    TextPart,
)

__all__ = [
    "MemberStatus",
    "TeamCoordinator",
    "TeamMember",
    "TeamSession",
    "TeamStatus",
    "extract_artifact_text",
]

logger = logging.getLogger(__name__)

# Terminal task states — collect_results polls until all members reach one of these.
_TERMINAL_STATES: frozenset[TaskState] = frozenset(
    {TaskState.completed, TaskState.canceled, TaskState.failed}
)

# Default collect_results timeout in seconds.
_DEFAULT_COLLECT_TIMEOUT = 300.0


class MemberStatus(StrEnum):
    """Lifecycle states for a team member."""

    SPAWNING = "spawning"
    IDLE = "idle"
    WORKING = "working"
    SHUTDOWN_REQUESTED = "shutdown_requested"
    TERMINATED = "terminated"


class TeamStatus(StrEnum):
    """Lifecycle states for a team session."""

    FORMING = "forming"
    ACTIVE = "active"
    DISSOLVING = "dissolving"
    DISSOLVED = "dissolved"


@dataclass
class TeamMember:
    """A single agent participating in a team."""

    name: str
    url: str
    card: AgentCard
    status: MemberStatus = field(default=MemberStatus.IDLE)


@dataclass
class TeamSession:
    """Shared state for an active team session.

    Per Decision 2: team_id == context_id. A single UUID is generated at
    formation time and used for both the vaultspec team identifier and the A2A
    contextId sent on every outbound message.
    """

    team_id: str
    name: str
    context_id: str  # Always equals team_id
    members: dict[str, TeamMember]
    status: TeamStatus
    created_at: float


def extract_artifact_text(task: Task) -> str:
    """Extract the first text part from a completed task's status message.

    Navigates task.status.message.parts[0].text.  Returns an empty string if
    any part of the path is absent.
    """
    try:
        parts = task.status.message.parts  # type: ignore[union-attr]
        if not parts:
            return ""
        part = parts[0].root
        if isinstance(part, TextPart):
            return part.text
        return ""
    except (AttributeError, IndexError):
        return ""


class TeamCoordinator:
    """Orchestrates N-agent A2A teams.

    Usage::

        coordinator = TeamCoordinator(api_key=None)
        async with coordinator:
            session = await coordinator.form_team(
                "my-team",
                ["http://localhost:10010/", "http://localhost:10011/"],
            )
            results = await coordinator.dispatch_parallel({
                "agent-a": "task for A",
                "agent-b": "task for B",
            })

    The coordinator holds a single shared httpx.AsyncClient for all outbound
    connections.  The API key, when provided, is forwarded as ``X-API-Key`` on
    every outbound request.
    """

    def __init__(
        self,
        api_key: str | None = None,
        collect_timeout: float = _DEFAULT_COLLECT_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._collect_timeout = collect_timeout
        self._session: TeamSession | None = None
        # Map agent-name -> in-flight task ID (for collect_results / dissolve cleanup)
        self._in_flight: dict[str, str] = {}
        # Per-member A2AClient instances, keyed by agent name
        self._clients: dict[str, A2AClient] = {}
        # Single underlying httpx.AsyncClient shared across all A2A connections
        self._http_client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> TeamCoordinator:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        self._http_client = httpx.AsyncClient(headers=headers)
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._close_http()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_http_client(self) -> httpx.AsyncClient:
        """Return the shared HTTP client, creating it if necessary."""
        if self._http_client is None:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["X-API-Key"] = self._api_key
            self._http_client = httpx.AsyncClient(headers=headers)
        return self._http_client

    async def _close_http(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def _get_client(self, agent_name: str) -> A2AClient:
        """Return (or lazily create) the A2AClient for the given agent."""
        if agent_name not in self._clients:
            member = self._session_member(agent_name)
            self._clients[agent_name] = A2AClient(
                httpx_client=self._ensure_http_client(),
                agent_card=member.card,
            )
        return self._clients[agent_name]

    def _session_member(self, agent_name: str) -> TeamMember:
        if self._session is None:
            raise RuntimeError("No active team session. Call form_team() first.")
        member = self._session.members.get(agent_name)
        if member is None:
            raise KeyError(f"Agent {agent_name!r} is not a member of this team.")
        return member

    @property
    def session(self) -> TeamSession:
        if self._session is None:
            raise RuntimeError("No active team session.")
        return self._session

    def _build_message(
        self,
        parts: list[Part],
        reference_task_ids: list[str] | None = None,
    ) -> Message:
        """Build an outbound A2A Message stamped with the team context."""
        if self._session is None:
            raise RuntimeError("No active team session. Call form_team() first.")
        return Message(
            role=Role.user,
            message_id=str(uuid.uuid4()),
            context_id=self._session.context_id,
            metadata={"team_name": self._session.name},
            reference_task_ids=reference_task_ids or [],
            parts=parts,
        )

    def _make_send_request(
        self,
        parts: list[Part],
        reference_task_ids: list[str] | None = None,
    ) -> SendMessageRequest:
        """Build a SendMessageRequest with a unique JSON-RPC id."""
        return SendMessageRequest(
            id=str(uuid.uuid4()),
            params=MessageSendParams(
                message=self._build_message(parts, reference_task_ids)
            ),
        )

    async def _poll_task_to_terminal(
        self,
        agent_name: str,
        task_id: str,
    ) -> Task:
        """Poll tasks/get until the task reaches a terminal state."""
        client = self._get_client(agent_name)
        wait = 0.1
        async with asyncio.timeout(self._collect_timeout):
            while True:
                response = await client.get_task(
                    GetTaskRequest(
                        id=str(uuid.uuid4()),
                        params=TaskQueryParams(id=task_id),
                    )
                )
                result = response.root
                if isinstance(result, JSONRPCErrorResponse):
                    raise RuntimeError(
                        f"A2A poll error for {agent_name!r}: {result.error}"
                    )
                task = result.result
                if task.status.state in _TERMINAL_STATES:
                    return task
                await asyncio.sleep(wait)
                wait = min(wait * 2, 5.0)

    async def _dispatch_one(
        self,
        agent_name: str,
        request: SendMessageRequest,
    ) -> Task:
        """Send a single message and return the resulting Task (always terminal)."""
        client = self._get_client(agent_name)
        response = await client.send_message(request)
        result = response.root
        # Unwrap: result is SendMessageSuccessResponse | JSONRPCErrorResponse
        if isinstance(result, JSONRPCErrorResponse):
            raise RuntimeError(f"A2A error from {agent_name!r}: {result.error}")
        task = result.result
        if isinstance(task, Task):
            if task.status.state not in _TERMINAL_STATES:
                task = await self._poll_task_to_terminal(agent_name, task.id)
            return task
        # result.result might be a Message for streaming responses; guard it.
        raise TypeError(f"Expected Task from {agent_name!r}, got {type(task).__name__}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def restore_session(self, session: TeamSession) -> None:
        """Restore a previously persisted session without re-fetching agent cards.

        Used by CLI tools that reload session state from disk. Clears any cached
        per-member clients since the HTTP client may have changed.
        """
        self._session = session
        self._clients.clear()

    async def form_team(
        self,
        name: str,
        agent_urls: list[str],
        api_key: str | None = None,
    ) -> TeamSession:
        """Discover agents and assemble a named team session.

        Generates a single UUID that serves as both ``team_id`` and
        ``context_id`` (ADR Decision 2). Fetches each agent's card via
        ``A2ACardResolver``.

        Args:
            name: Human-readable team name forwarded in message metadata.
            agent_urls: Base URLs of the agent servers to recruit.
            api_key: Optional API key override (takes precedence over the
                constructor value for this session).

        Returns:
            The active ``TeamSession``.
        """
        effective_key = api_key if api_key is not None else self._api_key
        if effective_key and self._http_client is not None:
            # Re-create with updated key header (rare; session-level override)
            await self._close_http()
            self._http_client = httpx.AsyncClient(headers={"X-API-Key": effective_key})
            self._clients.clear()

        team_id = str(uuid.uuid4())
        http = self._ensure_http_client()

        members: dict[str, TeamMember] = {}
        for url in agent_urls:
            resolver = A2ACardResolver(httpx_client=http, base_url=url)
            card = await resolver.get_agent_card()
            # Use the card name as the member key; fall back to URL if blank.
            member_name = card.name or url
            members[member_name] = TeamMember(
                name=member_name,
                url=url,
                card=card,
                status=MemberStatus.IDLE,
            )
            logger.debug("Recruited agent %r from %s", member_name, url)

        self._session = TeamSession(
            team_id=team_id,
            name=name,
            context_id=team_id,  # Decision 2: identical values
            members=members,
            status=TeamStatus.ACTIVE,
            created_at=time.time(),
        )
        logger.info(
            "Team %r formed (id=%s, members=%d)",
            name,
            team_id,
            len(members),
        )
        return self._session

    async def dissolve_team(self) -> None:
        """Tear down the active team session.

        Cancels in-flight tasks (best-effort), closes per-member A2A clients,
        and marks the session dissolved.  Idempotent — calling on an already-
        dissolved session is a no-op.
        """
        if self._session is None:
            return
        if self._session.status == TeamStatus.DISSOLVED:
            return

        self._session.status = TeamStatus.DISSOLVING

        # Best-effort cancel of any in-flight tasks.
        for agent_name, task_id in list(self._in_flight.items()):
            try:
                client = self._get_client(agent_name)
                await client.cancel_task(
                    CancelTaskRequest(
                        id=str(uuid.uuid4()),
                        params=TaskIdParams(id=task_id),
                    )
                )
                logger.debug("Cancelled in-flight task %s for %s", task_id, agent_name)
            except Exception as exc:
                logger.warning(
                    "Failed to cancel task %s for %s during dissolve: %s",
                    task_id,
                    agent_name,
                    exc,
                )

        self._in_flight.clear()
        self._clients.clear()

        # Mark all members terminated
        for member in self._session.members.values():
            member.status = MemberStatus.TERMINATED

        self._session.status = TeamStatus.DISSOLVED
        logger.info(
            "Team %r dissolved (id=%s)", self._session.name, self._session.team_id
        )

    async def dispatch_parallel(
        self,
        assignments: dict[str, str],
    ) -> dict[str, Task]:
        """Fan out tasks to multiple agents concurrently.

        Sends one message per agent in ``assignments`` via ``asyncio.gather``.
        Sets member status to ``WORKING`` before dispatch; ``IDLE`` on
        completion or error. The outbound message carries ``context_id ==
        session.team_id`` (Decision 2).

        Args:
            assignments: Mapping of agent name → task text.

        Returns:
            Mapping of agent name → resulting ``Task``.  On per-agent error
            the entry is omitted (the error is logged).
        """
        if self._session is None:
            raise RuntimeError("No active team session. Call form_team() first.")

        for name in assignments:
            self._session_member(name).status = MemberStatus.WORKING

        async def _send_one(agent_name: str, text: str) -> tuple[str, Task]:
            request = self._make_send_request(
                parts=[Part(root=TextPart(text=text))],
            )
            task = await self._dispatch_one(agent_name, request)
            self._in_flight[agent_name] = task.id
            return agent_name, task

        results: dict[str, Task] = {}
        agent_names = list(assignments.keys())
        coros = [_send_one(name, text) for name, text in assignments.items()]
        outcomes = await asyncio.gather(*coros, return_exceptions=True)

        for i, item in enumerate(outcomes):
            if isinstance(item, BaseException):
                logger.error("dispatch_parallel agent error: %s", item)
                self._session_member(agent_names[i]).status = MemberStatus.IDLE
                continue
            agent_name, task = item
            results[agent_name] = task
            self._session_member(agent_name).status = MemberStatus.IDLE

        return results

    async def collect_results(self) -> dict[str, str]:
        """Poll all in-flight tasks until they reach a terminal state.

        Applies the ``collect_timeout`` guard (default 300 s) to avoid hanging
        indefinitely.

        Returns:
            Mapping of agent name → extracted artifact text.
        """
        if self._session is None:
            raise RuntimeError("No active team session. Call form_team() first.")

        async def _poll_one(agent_name: str, task_id: str) -> tuple[str, str]:
            client = self._get_client(agent_name)
            wait = 0.1
            while True:
                response = await client.get_task(
                    GetTaskRequest(
                        id=str(uuid.uuid4()),
                        params=TaskQueryParams(id=task_id),
                    )
                )
                result = response.root
                if hasattr(result, "error"):
                    return agent_name, f"[error: {result.error}]"
                task = result.result
                if task.status.state in _TERMINAL_STATES:
                    return agent_name, extract_artifact_text(task)
                await asyncio.sleep(wait)
                wait = min(wait * 2, 5.0)

        coros = [_poll_one(name, task_id) for name, task_id in self._in_flight.items()]
        results: dict[str, str] = {}
        async with asyncio.timeout(self._collect_timeout):
            outcomes = await asyncio.gather(*coros, return_exceptions=True)

        for item in outcomes:
            if isinstance(item, BaseException):
                logger.error("collect_results poll error: %s", item)
                continue
            agent_name, text = item
            results[agent_name] = text

        return results

    async def relay_output(
        self,
        src_task: Task,
        dst_agent: str,
        instructions: str,
    ) -> Task:
        """Relay a completed task's output to another agent.

        Fetches the artifact text from ``src_task``, then dispatches a new
        message to ``dst_agent`` with ``reference_task_ids=[src_task.id]``
        and two ``TextPart`` entries: the source output and the instruction
        (ADR Decision 5).

        Args:
            src_task: The completed source task whose output is to be relayed.
            dst_agent: Name of the destination agent (must be a team member).
            instructions: Additional instructions to append to the relay message.

        Returns:
            The resulting ``Task`` from the destination agent.
        """
        text = extract_artifact_text(src_task)
        request = self._make_send_request(
            parts=[
                Part(root=TextPart(text=text)),
                Part(root=TextPart(text=instructions)),
            ],
            reference_task_ids=[src_task.id],
        )
        task = await self._dispatch_one(dst_agent, request)
        self._in_flight[dst_agent] = task.id
        return task

    async def ping_agents(self) -> dict[str, bool]:
        """Check reachability of all team members.

        Issues ``GET /.well-known/agent-card.json`` to each member URL using
        ``A2ACardResolver``.  Updates member status to ``IDLE`` on success;
        leaves status unchanged on failure.

        Returns:
            Mapping of agent name → reachable bool.
        """
        if self._session is None:
            raise RuntimeError("No active team session. Call form_team() first.")
        http = self._ensure_http_client()

        async def _ping(member: TeamMember) -> tuple[str, bool]:
            try:
                resolver = A2ACardResolver(httpx_client=http, base_url=member.url)
                await resolver.get_agent_card()
                member.status = MemberStatus.IDLE
                return member.name, True
            except Exception as exc:
                logger.warning("Agent %r unreachable: %s", member.name, exc)
                return member.name, False

        coros = [_ping(m) for m in self._session.members.values()]
        outcomes = await asyncio.gather(*coros, return_exceptions=True)

        results: dict[str, bool] = {}
        for item in outcomes:
            if isinstance(item, BaseException):
                logger.error("ping_agents error: %s", item)
                continue
            name, reachable = item
            results[name] = reachable
        return results
