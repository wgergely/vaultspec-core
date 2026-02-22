"""Functional tests for team.py CLI.

Tests each subcommand against in-process A2A servers backed by real
AgentExecutor subclasses via httpx.ASGITransport.  Verifies --root
propagation, session persistence, and real coordinator behavior.

No real TCP sockets are used.  No patch.object on coordinator methods.
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING

import httpx
import pytest

from ...mcp_server.team_tools import (
    _delete_session,
    _load_session,
    _save_session,
    _session_path,
)
from ...orchestration import (
    MemberStatus,
    TeamCoordinator,
    TeamMember,
    TeamSession,
    TeamStatus,
    extract_artifact_text,
)
from ...orchestration import parse_agents as _parse_agents
from ...protocol.a2a import create_app
from ...protocol.a2a.tests.conftest import (
    EchoExecutor,
    PrefixExecutor,
    _make_card,
)
from ...team_cli import (
    command_dissolve,
    command_list,
    command_status,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_app_transport(executor, name: str, port: int) -> httpx.ASGITransport:
    """Build an httpx.ASGITransport backed by an in-process A2A app."""
    card = _make_card(name, port)
    app = create_app(executor, card)
    return httpx.ASGITransport(app=app)


async def _build_coordinator_with_apps(
    executors: list[tuple[object, str, int]],
    name: str = "test-team",
) -> tuple[TeamCoordinator, list[str]]:
    """Bootstrap a TeamCoordinator with in-process ASGI agent apps.

    Returns (coordinator, agent_urls).  The coordinator's HTTP client is
    configured with per-host ASGITransport mounts so that agent card
    discovery and message dispatch go through real A2A server stacks.
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


def _make_session(root: Path, name: str = "my-team") -> TeamSession:
    """Build a minimal TeamSession saved to disk."""
    from a2a.types import AgentCapabilities, AgentCard, AgentSkill

    card = AgentCard(
        name="echo-agent",
        url="http://localhost:29901/",
        version="0.1.0",
        description="Test agent",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[AgentSkill(id="x", name="X", description="X", tags=[])],
    )
    session = TeamSession(
        team_id="test-team-id-0001",
        name=name,
        context_id="test-team-id-0001",
        status=TeamStatus.ACTIVE,
        created_at=0.0,
        members={
            "echo-agent": TeamMember(
                name="echo-agent",
                url="http://localhost:29901/",
                card=card,
                status=MemberStatus.IDLE,
            )
        },
    )
    _save_session(root, session)
    return session


def _args(**kwargs) -> argparse.Namespace:
    """Build a Namespace with defaults for team CLI tests."""
    defaults = {
        "api_key": None,
        "verbose": False,
        "debug": False,
        "force": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Unit tests — pure helpers
# ---------------------------------------------------------------------------


class TestParseAgents:
    def test_single_agent(self):
        urls = _parse_agents("localhost:10010")
        assert urls == ["http://localhost:10010/"]

    def test_multiple_agents(self):
        urls = _parse_agents("localhost:10010,localhost:10011")
        assert len(urls) == 2
        assert "http://localhost:10010/" in urls
        assert "http://localhost:10011/" in urls

    def test_with_explicit_http(self):
        urls = _parse_agents("http://myhost:9000")
        assert urls == ["http://myhost:9000/"]

    def test_ignores_empty(self):
        urls = _parse_agents("localhost:10010,,localhost:10011")
        assert len(urls) == 2


class TestSessionPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        """Session saved to disk can be reloaded with identical data."""
        session = _make_session(tmp_path, "test-team")
        loaded = _load_session(tmp_path, "test-team")

        assert loaded.team_id == session.team_id
        assert loaded.context_id == session.context_id
        assert loaded.name == session.name
        assert loaded.status == session.status
        assert set(loaded.members.keys()) == set(session.members.keys())

    def test_load_missing_session_exits(self, tmp_path):
        """Loading a non-existent session raises ToolError."""
        from mcp.server.fastmcp.exceptions import ToolError

        with pytest.raises(ToolError):
            _load_session(tmp_path, "nonexistent-team")

    def test_delete_removes_file(self, tmp_path):
        """_delete_session removes the JSON file."""
        _make_session(tmp_path, "del-team")
        path = _session_path(tmp_path, "del-team")
        assert path.exists()
        _delete_session(tmp_path, "del-team")
        assert not path.exists()

    def test_member_status_preserved(self, tmp_path):
        """MemberStatus is correctly serialized and deserialized."""
        session = _make_session(tmp_path, "status-team")
        session.members["echo-agent"].status = MemberStatus.WORKING
        _save_session(tmp_path, session)

        loaded = _load_session(tmp_path, "status-team")
        assert loaded.members["echo-agent"].status == MemberStatus.WORKING


# ---------------------------------------------------------------------------
# command_status tests
# ---------------------------------------------------------------------------


class TestCommandStatus:
    def test_status_prints_team_info(self, tmp_path, capsys):
        """command_status prints team name, ID, and members."""
        _make_session(tmp_path, "info-team")
        args = _args(root=tmp_path, name="info-team")
        command_status(args)

        out = capsys.readouterr().out
        assert "info-team" in out
        assert "test-team-id-0001" in out
        assert "echo-agent" in out

    def test_status_missing_team_exits(self, tmp_path):
        """command_status on unknown team name exits with error."""
        args = _args(root=tmp_path, name="ghost-team")
        with pytest.raises(SystemExit):
            command_status(args)


# ---------------------------------------------------------------------------
# command_list tests
# ---------------------------------------------------------------------------


class TestCommandList:
    def test_list_shows_teams(self, tmp_path, capsys):
        """command_list prints each active team session."""
        _make_session(tmp_path, "alpha")
        _make_session(tmp_path, "beta")
        args = _args(root=tmp_path)
        command_list(args)

        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" in out

    def test_list_empty(self, tmp_path, capsys):
        """command_list prints message when no teams exist."""
        args = _args(root=tmp_path)
        command_list(args)
        out = capsys.readouterr().out
        assert "No active teams" in out


# ---------------------------------------------------------------------------
# command_create tests — real coordinator with in-process A2A agents
# ---------------------------------------------------------------------------


class TestCommandCreate:
    @pytest.mark.asyncio
    async def test_create_persists_session(self, tmp_path):
        """Real form_team against in-process A2A agent; session saved to disk."""
        coordinator, _ = await _build_coordinator_with_apps(
            [(EchoExecutor(), "echo-agent", 29902)],
            name="create-team",
        )
        try:
            session = coordinator.session
            _save_session(tmp_path, session)

            session_path = _session_path(tmp_path, "create-team")
            assert session_path.exists()
            data = json.loads(session_path.read_text(encoding="utf-8"))
            assert data["team_id"] == session.team_id
            assert data["name"] == "create-team"
            assert data["context_id"] == session.context_id
            assert data["team_id"] == data["context_id"]
            assert len(data["team_id"]) == 36
            assert "echo-agent" in data["members"]
            assert data["status"] == "active"
        finally:
            await coordinator.dissolve_team()

    def test_create_then_status_reloads(self, tmp_path, capsys):
        """After create, status subcommand can reload the session from disk."""
        _make_session(tmp_path, "persistent-team")

        args = _args(root=tmp_path, name="persistent-team")
        command_status(args)

        out = capsys.readouterr().out
        assert "persistent-team" in out
        assert "test-team-id-0001" in out


# ---------------------------------------------------------------------------
# command_dissolve tests — real coordinator dissolution
# ---------------------------------------------------------------------------


class TestCommandDissolve:
    @pytest.mark.asyncio
    async def test_dissolve_removes_json(self, tmp_path):
        """Real dissolve_team against in-process agents; session file deleted."""
        coordinator, _ = await _build_coordinator_with_apps(
            [(EchoExecutor(), "echo-agent", 29903)],
            name="to-dissolve",
        )
        session = coordinator.session
        _save_session(tmp_path, session)
        assert _session_path(tmp_path, "to-dissolve").exists()

        await coordinator.dissolve_team()
        assert session.status == TeamStatus.DISSOLVED
        _delete_session(tmp_path, "to-dissolve")
        assert not _session_path(tmp_path, "to-dissolve").exists()

    def test_dissolve_missing_team_exits(self, tmp_path):
        """command_dissolve on nonexistent team exits with error."""
        args = _args(root=tmp_path, name="ghost", force=True)
        with pytest.raises(SystemExit):
            command_dissolve(args)


# ---------------------------------------------------------------------------
# command_assign / command_broadcast — real dispatch with in-process agents
# ---------------------------------------------------------------------------


class TestCommandAssign:
    @pytest.mark.asyncio
    async def test_assign_dispatches_real_task(self, tmp_path):
        """Real dispatch_parallel against EchoExecutor; verify task completion."""
        coordinator, _ = await _build_coordinator_with_apps(
            [(EchoExecutor(), "echo-agent", 29904)],
            name="assign-team",
        )
        try:
            session = coordinator.session
            _save_session(tmp_path, session)

            results = await coordinator.dispatch_parallel(
                {"echo-agent": "do this thing"}
            )
            task = results["echo-agent"]
            assert task.status.state.value == "completed"
            assert task.context_id == session.team_id

            text = extract_artifact_text(task)
            assert "do this thing" in text
        finally:
            await coordinator.dissolve_team()


class TestCommandBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_dispatches_to_all(self, tmp_path):
        """Real dispatch_parallel to multiple agents; all complete with real output."""
        coordinator, _ = await _build_coordinator_with_apps(
            [
                (EchoExecutor(), "echo-agent", 29905),
                (PrefixExecutor("[B] "), "prefix-agent", 29906),
            ],
            name="broadcast-team",
        )
        try:
            session = coordinator.session
            _save_session(tmp_path, session)

            agent_names = list(session.members.keys())
            assignments = dict.fromkeys(agent_names, "hello all")
            results = await coordinator.dispatch_parallel(assignments)

            assert len(results) == 2
            for _name, task in results.items():
                assert task.status.state.value == "completed"
                assert task.context_id == session.team_id
                text = extract_artifact_text(task)
                assert len(text) > 0
                assert "hello all" in text
        finally:
            await coordinator.dissolve_team()


# ---------------------------------------------------------------------------
# --root propagation test
# ---------------------------------------------------------------------------


class TestRootPropagation:
    def test_root_determines_session_path(self, tmp_path):
        """Sessions are stored under root/.vault/logs/teams/, not a hardcoded path."""
        root_a = tmp_path / "workspace_a"
        root_b = tmp_path / "workspace_b"
        root_a.mkdir()
        root_b.mkdir()

        _make_session(root_a, "shared-name")

        # Session exists in root_a
        loaded = _load_session(root_a, "shared-name")
        assert loaded.team_id == "test-team-id-0001"

        # Session does NOT exist in root_b
        from mcp.server.fastmcp.exceptions import ToolError

        with pytest.raises(ToolError):
            _load_session(root_b, "shared-name")
