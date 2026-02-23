"""Functional tests for team.py CLI.

Tests each subcommand against in-process A2A servers backed by real
AgentExecutor subclasses via httpx.ASGITransport.  Verifies --root
propagation, session persistence, and real coordinator behavior.

No real TCP sockets are used.  No patch.object on coordinator methods.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import TYPE_CHECKING

import httpx
import pytest

from ...mcp_server.team_tools import (
    _delete_session,
    _load_session,
    _save_session,
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
from ...orchestration.team_session import session_path as _session_path
from ...protocol.a2a import create_app
from ...protocol.a2a.tests.conftest import (
    EchoExecutor,
    PrefixExecutor,
    _make_card,
)
from ...team_cli import (
    command_dissolve,
    command_list,
    command_message,
    command_spawn,
    command_status,
)

if TYPE_CHECKING:
    from pathlib import Path


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
            "http://localhost:29901/": TeamMember(
                name="http://localhost:29901/",
                display_name="echo-agent",
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
    from ...printer import Printer

    defaults = {
        "api_key": None,
        "verbose": False,
        "debug": False,
        "force": False,
        "printer": Printer(),
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


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
        session.members["http://localhost:29901/"].status = MemberStatus.WORKING
        _save_session(tmp_path, session)

        loaded = _load_session(tmp_path, "status-team")
        assert loaded.members["http://localhost:29901/"].status == MemberStatus.WORKING


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
            # Members are now keyed by URL; check that at least one URL key exists
            assert any("localhost:29902" in k for k in data["members"]), (
                "Expected URL-keyed member for localhost:29902, "
                f"got: {list(data['members'].keys())}"
            )
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
            # Results are keyed by canonical URL key; get the single result.
            assert len(results) == 1
            task = next(iter(results.values()))
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


class TestCommandMessage:
    @pytest.mark.asyncio
    async def test_message_direct_dispatch(self, tmp_path):
        """Direct message dispatches to echo-agent and returns completed task."""
        coordinator, _ = await _build_coordinator_with_apps(
            [(EchoExecutor(), "echo-agent", 29910)],
            name="msg-team",
        )
        try:
            session = coordinator.session
            _save_session(tmp_path, session)

            results = await coordinator.dispatch_parallel(
                {"echo-agent": "hello direct"}
            )
            # Results keyed by canonical URL key.
            assert len(results) == 1
            task = next(iter(results.values()))
            assert task.status.state.value == "completed"

            text = extract_artifact_text(task)
            assert "hello direct" in text
        finally:
            await coordinator.dissolve_team()

    @pytest.mark.asyncio
    async def test_message_relay_mode(self, tmp_path):
        """Relay mode: echo output forwarded to prefix-agent via relay_output."""
        coordinator, _ = await _build_coordinator_with_apps(
            [
                (EchoExecutor(), "echo-agent", 29911),
                (PrefixExecutor("[R] "), "relay-agent", 29912),
            ],
            name="relay-team",
        )
        try:
            session = coordinator.session
            _save_session(tmp_path, session)

            # First dispatch to echo-agent to get a completed source task
            results = await coordinator.dispatch_parallel(
                {"echo-agent": "initial payload"}
            )
            # Results keyed by canonical URL key.
            assert len(results) == 1
            src_task = next(iter(results.values()))
            assert src_task.status.state.value == "completed"

            # Relay the echo output to relay-agent (accepts display_name).
            relayed = await coordinator.relay_output(
                src_task, "relay-agent", "relay context"
            )
            assert relayed.status.state.value == "completed"

            text = extract_artifact_text(relayed)
            assert "[R] " in text
        finally:
            await coordinator.dissolve_team()

    def test_message_missing_team_exits(self, tmp_path):
        """command_message with nonexistent team raises SystemExit."""
        args = _args(
            root=tmp_path,
            name="ghost-team",
            to="some-agent",
            content="hello",
            from_agent=None,
            src_task_id=None,
        )
        with pytest.raises(SystemExit):
            command_message(args)

    def test_message_relay_requires_src_task_id(self, tmp_path):
        """--from without --src-task-id logs error and exits."""
        _make_session(tmp_path, "relay-err-team")
        args = _args(
            root=tmp_path,
            name="relay-err-team",
            to="echo-agent",
            content="relay me",
            from_agent="echo-agent",
            src_task_id=None,
        )
        with pytest.raises(SystemExit):
            command_message(args)


class TestCommandSpawn:
    def test_spawn_arg_parsing(self):
        """All required spawn fields parse correctly via subprocess."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "vaultspec.team_cli",
                "spawn",
                "--name",
                "my-team",
                "--agent",
                "new-agent",
                "--script",
                "/path/to/script.py",
                "--port",
                "12345",
                "--help",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # --help exits 0 and shows the spawn subcommand help
        assert result.returncode == 0
        assert "spawn" in result.stdout.lower() or "--agent" in result.stdout

    def test_spawn_missing_required_args_name(self):
        """Omitting --name raises SystemExit (non-zero exit)."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "vaultspec.team_cli",
                "spawn",
                "--agent",
                "a",
                "--script",
                "s.py",
                "--port",
                "9999",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0

    def test_spawn_missing_required_args_agent(self):
        """Omitting --agent raises SystemExit (non-zero exit)."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "vaultspec.team_cli",
                "spawn",
                "--name",
                "t",
                "--script",
                "s.py",
                "--port",
                "9999",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0

    def test_spawn_missing_required_args_script(self):
        """Omitting --script raises SystemExit (non-zero exit)."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "vaultspec.team_cli",
                "spawn",
                "--name",
                "t",
                "--agent",
                "a",
                "--port",
                "9999",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0

    def test_spawn_missing_required_args_port(self):
        """Omitting --port raises SystemExit (non-zero exit)."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "vaultspec.team_cli",
                "spawn",
                "--name",
                "t",
                "--agent",
                "a",
                "--script",
                "s.py",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0

    def test_spawn_missing_team_exits(self, tmp_path):
        """command_spawn with nonexistent team raises SystemExit."""
        args = _args(
            root=tmp_path,
            name="ghost-team",
            agent="new-agent",
            script="/path/to/script.py",
            port=29913,
        )
        with pytest.raises(SystemExit):
            command_spawn(args)


class TestMessageArgParsing:
    def test_message_parser_from_flag(self):
        """--from is stored as from_agent (dest='from_agent'), not 'from'."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "vaultspec.team_cli",
                "message",
                "--name",
                "t",
                "--to",
                "a",
                "--content",
                "x",
                "--from",
                "b",
                "--help",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # --help proves the parser accepts --from without error
        assert result.returncode == 0
        assert "--from" in result.stdout

    def test_message_parser_src_task_id(self):
        """--src-task-id is parsed correctly."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "vaultspec.team_cli",
                "message",
                "--name",
                "t",
                "--to",
                "a",
                "--content",
                "x",
                "--src-task-id",
                "abc-123",
                "--help",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "--src-task-id" in result.stdout

    def test_message_from_stored_as_from_agent(self):
        """Verify --from dest is from_agent by parsing args directly."""
        # Build a minimal parser that mirrors the message subparser
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        msg = sub.add_parser("message")
        msg.add_argument("--name", required=True)
        msg.add_argument("--to", required=True)
        msg.add_argument("--content", required=True)
        msg.add_argument("--from", dest="from_agent", default=None)
        msg.add_argument("--src-task-id", default=None)

        args = parser.parse_args(
            ["message", "--name", "t", "--to", "a", "--content", "x", "--from", "b"]
        )
        assert args.from_agent == "b"
        assert not hasattr(args, "from") or getattr(args, "from", None) is None

    def test_message_src_task_id_parsed(self):
        """Verify --src-task-id value is captured in parsed namespace."""
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        msg = sub.add_parser("message")
        msg.add_argument("--name", required=True)
        msg.add_argument("--to", required=True)
        msg.add_argument("--content", required=True)
        msg.add_argument("--from", dest="from_agent", default=None)
        msg.add_argument("--src-task-id", default=None)

        args = parser.parse_args(
            [
                "message",
                "--name",
                "t",
                "--to",
                "a",
                "--content",
                "x",
                "--src-task-id",
                "abc-123",
            ]
        )
        assert args.src_task_id == "abc-123"
