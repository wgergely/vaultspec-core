"""Multi-agent team coordination layer.

Provides TeamCoordinator, TeamSession, TeamMember, and associated enums for
orchestrating N-agent A2A teams. Operates above the A2A transport layer,
using A2AClient and A2ACardResolver as the transport primitives.

ADR: .vault/adr/2026-02-20-a2a-team-adr.md
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

import httpx
from a2a.client import A2ACardResolver, ClientFactory
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

from .utils import kill_process_tree
from ..protocol.a2a.server_manager import ServerProcessManager
from ..protocol.providers import ProcessSpec

__all__ = [
    "MemberStatus",
    "TeamCoordinator",
    "TeamMember",
    "TeamSession",
    "TeamStatus",
    "extract_artifact_text",
    "resolve_member_key",
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
    """A single agent participating in a team.

    ``name`` is the dict key used to address this member (URL for agents
    discovered via ``form_team``; caller-supplied logical name for agents
    added via ``spawn_agent``).  ``display_name`` is the human-readable
    name taken from the agent's ``AgentCard``.
    """

    name: str
    display_name: str
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


def resolve_member_key(members: dict[str, TeamMember], ref: str) -> str:
    """Resolve a member reference to its dict key.

    Accepts either the exact dict key (URL or logical name) or a
    ``display_name`` match.  Raises ``KeyError`` if the reference is
    ambiguous or not found.

    Args:
        members: The ``TeamSession.members`` dict.
        ref: A URL key, logical name, or display_name to resolve.

    Returns:
        The resolved dict key into ``members``.

    Raises:
        KeyError: If ``ref`` cannot be resolved uniquely.
    """
    if ref in members:
        return ref
    # Fall back to display_name search.
    matches = [key for key, m in members.items() if m.display_name == ref]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        keys = ", ".join(repr(k) for k in matches)
        raise KeyError(
            f"Ambiguous agent reference {ref!r}: matches multiple members ({keys}). "
            "Use the full URL to disambiguate."
        )
    available = ", ".join(f"{m.display_name!r} ({key})" for key, m in members.items())
    raise KeyError(f"Agent {ref!r} is not a member of this team. Members: {available}")


def extract_artifact_text(task: Task) -> str:
    """Extract the first text part from a completed task's status message.

    Navigates task.status.message.parts[0].text.  Returns an empty string if
    any part of the path is absent.

    Args:
        task: The A2A ``Task`` whose status message to inspect.

    Returns:
        The text content of the first ``TextPart``, or ``""`` if not present.
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
        """Initialize the TeamCoordinator.

        Args:
            api_key: Optional API key forwarded as ``X-API-Key`` on every
                outbound HTTP request.
            collect_timeout: Maximum seconds to wait when polling in-flight
                tasks to completion via ``collect_results``.
        """
        self._api_key = api_key
        self._collect_timeout = collect_timeout
        self._session: TeamSession | None = None
        # Map agent-name -> in-flight task ID (for collect_results / dissolve cleanup)
        self._in_flight: dict[str, str] = {}
        # Per-member A2AClient instances, keyed by agent name
        self._clients: dict[str, Any] = {}
        # Single underlying httpx.AsyncClient shared across all A2A connections
        self._http_client: httpx.AsyncClient | None = None
        # Map agent-name -> spawned subprocess (managed by spawn_agent / dissolve_team)
        self._spawned: dict[str, asyncio.subprocess.Process] = {}
        # Map agent-name -> PID for processes restored from disk (no Process handle)
        self._spawned_pids: dict[str, int] = {}
        
        # Lifecycle manager for spawned agents
        self._server_manager = ServerProcessManager()
    async def __aenter__(self) -> TeamCoordinator:
        """Open the shared HTTP client for use in an async context manager."""
        headers: dict[str, str] = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        self._http_client = httpx.AsyncClient(headers=headers, timeout=60.0)
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the shared HTTP client on context manager exit."""
        await self._close_http()
        # Ensure all spawned servers are shut down
        await self._server_manager.shutdown_all()

    def _ensure_http_client(self) -> httpx.AsyncClient:
        """Return the shared HTTP client, creating it lazily if necessary.

        Returns:
            The active ``httpx.AsyncClient`` instance.
        """
        if self._http_client is None:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["X-API-Key"] = self._api_key
            self._http_client = httpx.AsyncClient(headers=headers, timeout=60.0)
        return self._http_client

    async def _close_http(self) -> None:
        """Close the shared httpx.AsyncClient if one is open."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _get_client(self, ref: str) -> Any:
        """Return (or lazily create) the A2AClient for the given agent.

        Accepts either the exact dict key (URL or logical name) or the
        agent's display_name.  The client is cached under the resolved key.

        Args:
            ref: A URL key, logical name, or display_name.

        Returns:
            The ``A2AClient`` bound to the member's ``AgentCard``.
        """
        if self._session is None:
            raise RuntimeError("No active team session. Call form_team() first.")
        key = resolve_member_key(self._session.members, ref)
        if key not in self._clients:
            member = self._session.members[key]
            # Use SDK factory to connect. Ideally we'd reuse self._http_client but
            # Factory handles transport details.
            self._clients[key] = await ClientFactory.connect(member.url)
        return self._clients[key]

    def _session_member(self, ref: str) -> TeamMember:
        """Return the TeamMember for the given reference.

        Accepts either the exact dict key (URL or logical name) or the
        agent's display_name.  Delegates to :func:`resolve_member_key`.

        Args:
            ref: A URL key, logical name, or display_name to look up.

        Returns:
            The corresponding ``TeamMember``.

        Raises:
            RuntimeError: If no active team session exists.
            KeyError: If the reference cannot be resolved uniquely.
        """
        if self._session is None:
            raise RuntimeError("No active team session. Call form_team() first.")
        key = resolve_member_key(self._session.members, ref)
        return self._session.members[key]

    @property
    def session(self) -> TeamSession:
        """Return the active team session.

        Returns:
            The current ``TeamSession``.

        Raises:
            RuntimeError: If no team session has been formed yet.
        """
        if self._session is None:
            raise RuntimeError("No active team session.")
        return self._session

    def _build_message(
        self,
        parts: list[Part],
        reference_task_ids: list[str] | None = None,
    ) -> Message:
        """Build an outbound A2A Message stamped with the team context.

        Args:
            parts: Message content parts to include.
            reference_task_ids: Optional list of task IDs to reference.

        Returns:
            A ``Message`` with a fresh ``message_id`` and the session's
            ``context_id`` set.
        """
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
        """Build a SendMessageRequest with a unique JSON-RPC id.

        Args:
            parts: Message content parts to include.
            reference_task_ids: Optional list of task IDs to reference.

        Returns:
            A ``SendMessageRequest`` wrapping the constructed message.
        """
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
        """Poll tasks/get until the task reaches a terminal state.

        Args:
            agent_name: Name of the team member that owns the task.
            task_id: The A2A task ID to poll.

        Returns:
            The ``Task`` once it has reached a terminal state.
        """
        client = await self._get_client(agent_name)
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
        """Send a single message and return the resulting Task (always terminal).

        Args:
            agent_name: Name of the team member to send the message to.
            request: The ``SendMessageRequest`` to dispatch.

        Returns:
            The terminal ``Task`` produced by the agent.
        """
        client = await self._get_client(agent_name)
        logger.debug("Sending A2A message to %r", agent_name)
        response = await client.send_message(request)
        result = response.root
        # Unwrap: result is SendMessageSuccessResponse | JSONRPCErrorResponse
        if isinstance(result, JSONRPCErrorResponse):
            raise RuntimeError(f"A2A error from {agent_name!r}: {result.error}")
        task = result.result
        if isinstance(task, Task):
            logger.debug(
                "Task %s created for %r (state=%s)",
                task.id,
                agent_name,
                task.status.state.value,
            )
            if task.status.state not in _TERMINAL_STATES:
                logger.debug(
                    "Polling task %s for %r to terminal state", task.id, agent_name
                )
                task = await self._poll_task_to_terminal(agent_name, task.id)
            logger.info(
                "Task %s for %r reached terminal state: %s",
                task.id,
                agent_name,
                task.status.state.value,
            )
            return task
        # result.result might be a Message for streaming responses; guard it.
        raise TypeError(f"Expected Task from {agent_name!r}, got {type(task).__name__}")

    def restore_session(
        self,
        session: TeamSession,
        spawned_pids: dict[str, int] | None = None,
    ) -> None:
        """Restore a previously persisted session without re-fetching agent cards.

        Used by CLI tools that reload session state from disk. Clears any cached
        per-member clients since the HTTP client may have changed.

        Args:
            session: A ``TeamSession`` previously obtained from ``form_team``.
            spawned_pids: Optional mapping of agent name to OS PID for
                subprocesses that were spawned in a previous session.  These
                are terminated by ``dissolve_team()`` via ``os.kill``.
        """
        self._session = session
        self._clients.clear()
        if spawned_pids:
            self._spawned_pids = dict(spawned_pids)

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

        logger.info(
            "Forming team %r from %d agent(s): %s",
            name,
            len(agent_urls),
            ", ".join(agent_urls),
        )
        team_id = str(uuid.uuid4())
        http = self._ensure_http_client()

        members: dict[str, TeamMember] = {}
        for url in agent_urls:
            # Normalise: ensure trailing slash so the key is stable.
            if not url.endswith("/"):
                url = url + "/"
            resolver = A2ACardResolver(httpx_client=http, base_url=url)
            card = await resolver.get_agent_card()
            display_name = card.name or url
            # Key by URL (unique); display_name is the human-readable label.
            members[url] = TeamMember(
                name=url,
                display_name=display_name,
                url=url,
                card=card,
                status=MemberStatus.IDLE,
            )
            logger.debug("Recruited agent %r (%s) from %s", display_name, url, url)

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
                client = await self._get_client(agent_name)
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

        # Shutdown all active servers managed by the coordinator
        await self._server_manager.shutdown_all()

        # Terminate processes restored from disk (PIDs only, no Process handle).
        for agent_name, pid in list(self._spawned_pids.items()):
            try:
                os.kill(pid, signal.SIGTERM)
                kill_process_tree(pid)
                logger.debug("Terminated restored process %s (pid=%d)", agent_name, pid)
            except ProcessLookupError:
                logger.debug(
                    "Restored process %s (pid=%d) already exited", agent_name, pid
                )
            except OSError as exc:
                logger.warning(
                    "Failed to terminate restored process %s (pid=%d): %s",
                    agent_name,
                    pid,
                    exc,
                )
        self._spawned_pids.clear()

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

        logger.info(
            "dispatch_parallel: dispatching to %d agent(s): %s",
            len(assignments),
            ", ".join(assignments.keys()),
        )

        # Resolve all refs to canonical keys up-front so _in_flight and status
        # are always indexed by the canonical key (URL or logical spawn name).
        resolved: dict[str, str] = {
            ref: resolve_member_key(self._session.members, ref) for ref in assignments
        }
        for key in resolved.values():
            self._session.members[key].status = MemberStatus.WORKING

        async def _send_one(key: str, text: str) -> tuple[str, Task]:
            """Dispatch a single text task to one agent and return the result.

            Args:
                key: Canonical member key.
                text: Task text to send.

            Returns:
                A ``(key, Task)`` tuple for the completed task.
            """
            request = self._make_send_request(
                parts=[Part(root=TextPart(text=text))],
            )
            task = await self._dispatch_one(key, request)
            self._in_flight[key] = task.id
            return key, task

        results: dict[str, Task] = {}
        canonical_keys = list(resolved.values())
        coros = [_send_one(key, assignments[ref]) for ref, key in resolved.items()]
        outcomes = await asyncio.gather(*coros, return_exceptions=True)

        for i, item in enumerate(outcomes):
            if isinstance(item, BaseException):
                logger.error("dispatch_parallel agent error: %s", item)
                key = canonical_keys[i]
                self._session.members[key].status = MemberStatus.IDLE
                continue
            key, task = item
            results[key] = task
            self._session.members[key].status = MemberStatus.IDLE

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
            """Poll a single in-flight task until terminal and extract its text.

            Args:
                agent_name: Name of the team member that owns the task.
                task_id: The A2A task ID to poll.

            Returns:
                A ``(agent_name, artifact_text)`` tuple.
            """
            client = await self._get_client(agent_name)
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

    async def collect_tasks(self) -> dict[str, Task]:
        """Poll all in-flight tasks until terminal and return the Task objects.

        Like :meth:`collect_results` but returns full ``Task`` objects instead
        of extracted text, for callers that need to pass tasks to
        :meth:`relay_output`.

        Returns:
            Mapping of agent name → completed ``Task``.
        """
        if self._session is None:
            raise RuntimeError("No active team session. Call form_team() first.")

        async def _poll_one_task(agent_name: str, task_id: str) -> tuple[str, Task]:
            """Poll a single in-flight task until terminal and return it.

            Args:
                agent_name: Name of the team member that owns the task.
                task_id: The A2A task ID to poll.

            Returns:
                A ``(agent_name, Task)`` tuple for the completed task.
            """
            client = await self._get_client(agent_name)
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
                    raise RuntimeError(f"task error: {result.error}")
                task = result.result
                if task.status.state in _TERMINAL_STATES:
                    return agent_name, task
                await asyncio.sleep(wait)
                wait = min(wait * 2, 5.0)

        coros = [
            _poll_one_task(name, task_id) for name, task_id in self._in_flight.items()
        ]
        tasks: dict[str, Task] = {}
        async with asyncio.timeout(self._collect_timeout):
            outcomes = await asyncio.gather(*coros, return_exceptions=True)

        for item in outcomes:
            if isinstance(item, BaseException):
                logger.error("collect_tasks poll error: %s", item)
                continue
            agent_name, task = item
            tasks[agent_name] = task

        return tasks

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
        logger.info(
            "relay_output: src_task=%s -> dst=%r (text_len=%d)",
            src_task.id,
            dst_agent,
            len(text),
        )
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

    async def spawn_agent(
        self,
        script_path: str,
        port: int,
        name: str,
    ) -> TeamMember:
        """Spawn a subprocess running an A2A agent server and add it to the team.

        Uses ``ServerProcessManager`` to spawn the agent process and wait for
        readiness. Then discovers its ``AgentCard`` and adds it as a new
        ``TeamMember``.

        Args:
            script_path: Path to a Python script that starts an A2A server.
            port: TCP port the agent will listen on.
            name: Logical name for the new team member.

        Returns:
            The newly created ``TeamMember``.

        Raises:
            RuntimeError: If no active team session exists, if the agent
                does not become reachable within the timeout, or if the
                subprocess exits prematurely.
        """
        if self._session is None:
            raise RuntimeError("No active team session. Call form_team() first.")

        # Construct a ProcessSpec for ServerProcessManager
        spec = ProcessSpec(
            executable=sys.executable,
            args=[script_path, "--port", str(port)],
            env=dict(os.environ),
            cleanup_paths=[],
            session_meta={"agent_name": name},
            protocol="a2a",
        )

        logger.info("Spawning agent %r on port %d", name, port)
        server = await self._server_manager.spawn(spec, cwd=os.getcwd())
        
        # Wait for readiness (handled by manager)
        await self._server_manager.wait_ready(server)
        
        base_url = f"http://localhost:{server.port}"
        http = self._ensure_http_client()
        
        # Discover the agent card and register the member.
        resolver = A2ACardResolver(httpx_client=http, base_url=f"{base_url}/")
        card = await resolver.get_agent_card()
        member = TeamMember(
            name=name,
            display_name=card.name or name,
            url=f"{base_url}/",
            card=card,
            status=MemberStatus.IDLE,
        )
        self._session.members[name] = member
        logger.info("Agent %r joined team %r", name, self._session.name)
        return member

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
            """Ping a single team member's well-known endpoint.

            Args:
                member: The ``TeamMember`` to check reachability for.

            Returns:
                A ``(member_name, reachable)`` tuple.
            """
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
