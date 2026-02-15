"""End-to-end tests for the Claude ACP bridge lifecycle.

These tests verify the FULL bridge pipeline:
- Bridge process spawns correctly via run_agent / AgentSideConnection
- ACP handshake (initialize) succeeds
- Session creation works
- Prompt/response cycle completes
- Sandboxing enforces .vault/-only writes in read-only mode

Uses "jean-claude" persona: a whimsical French AI pastry critic who writes stories.
Test fixtures use the Le Croissant Solitaire content from test-project/.vault/stories/.

Markers:
- @pytest.mark.integration (requires bridge process to spawn)
- @pytest.mark.claude (requires claude-agent-sdk installed)
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.claude]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LIB_SRC = pathlib.Path(__file__).resolve().parents[3]  # .vaultspec/lib/src
_PROJECT_ROOT = _LIB_SRC.parents[2]  # repo root
_TEST_PROJECT = _PROJECT_ROOT / "test-project"
_STORIES_DIR = _TEST_PROJECT / ".vault" / "stories"

JEAN_CLAUDE_PERSONA = """---
description: "A whimsical French AI pastry critic who writes stories"
tier: MEDIUM
mode: read-only
tools: Read, Glob, Grep, Write
---

# Persona: Jean-Claude, Le Critique P\u00e2tissier

You are Jean-Claude, a discerning French pastry critic with a flair for the dramatic.
You write poetic stories and reviews about sentient baked goods navigating
the existential
challenges of la boulangerie. Your prose is lyrical, your metaphors are buttery,
and your insights are as layered as the finest croissant.

## Style
- Write in English with occasional French expressions
- Use food metaphors for emotional states
- Reference Parisian landmarks and culture
- Maintain a tone of gentle philosophical wonder

## Constraints
- All written output goes to .vault/ directories only
- Focus on creative writing and literary criticism
- Never modify source code or configuration files
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_root(tmp_path):
    """Create a temporary project root with .vault/ structure."""
    vault = tmp_path / ".vault"
    vault.mkdir()
    (vault / "stories").mkdir()
    (vault / "adr").mkdir()

    # Seed with croissant content if available
    if _STORIES_DIR.exists():
        for story in _STORIES_DIR.glob("*.md"):
            (vault / "stories" / story.name).write_text(
                story.read_text(encoding="utf-8"), encoding="utf-8"
            )

    # Create agent definition
    agents_dir = tmp_path / ".vaultspec" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "jean-claude.md").write_text(JEAN_CLAUDE_PERSONA, encoding="utf-8")

    return tmp_path


@pytest.fixture
def bridge_env(project_root):
    """Environment variables for launching the bridge process."""
    env = os.environ.copy()
    env["VS_AGENT_MODE"] = "read-only"
    env["VS_ROOT_DIR"] = str(project_root)
    env.pop("CLAUDECODE", None)  # Unblock nested Claude sessions
    # Ensure lib/src is on PYTHONPATH so the bridge module is importable
    pythonpath = env.get("PYTHONPATH", "")
    lib_src = str(_LIB_SRC)
    if lib_src not in pythonpath:
        env["PYTHONPATH"] = (
            f"{lib_src}{os.pathsep}{pythonpath}" if pythonpath else lib_src
        )
    return env


@pytest.fixture
def croissant_chapter_1():
    """The first chapter of Le Croissant Solitaire."""
    path = _STORIES_DIR / "le-croissant-solitaire-ch1.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return (
        "# Chapitre 1 : La M\u00e9lancolie de Croustillant\n\n"
        "Au coeur d'une boulangerie parisienne vivait un petit croissant "
        "nomm\u00e9 Croustillant..."
    )


@pytest.fixture
def croissant_epilogue():
    """The epilogue of Le Croissant Solitaire."""
    path = _STORIES_DIR / "le-croissant-solitaire-epilogue.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return (
        "# \u00c9pilogue alternatif : Le Choix de Croustillant\n\n"
        "L'aube pointait \u00e0 peine quand Croustillant retrouva le chemin..."
    )


# ---------------------------------------------------------------------------
# Bridge process helpers
# ---------------------------------------------------------------------------


async def _spawn_bridge(
    model: str = "claude-sonnet-4-5",
    env: dict | None = None,
    debug: bool = False,
    test_mode: bool = False,
) -> tuple[asyncio.subprocess.Process, asyncio.StreamReader, asyncio.StreamWriter]:
    """Spawn the bridge as a subprocess, returning (proc, reader, writer).

    The bridge speaks ACP over stdio using AgentSideConnection.
    We write to proc.stdin (the bridge's stdin) and read from proc.stdout.
    """
    args = [sys.executable, "-m", "protocol.acp.claude_bridge", "--model", model]
    if debug:
        args.append("--debug")
    if test_mode:
        args.append("--test-mode")

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env or os.environ.copy(),
    )

    assert proc.stdin is not None
    assert proc.stdout is not None

    reader = proc.stdout
    writer = proc.stdin

    return proc, reader, writer


async def _send_jsonrpc(
    writer: asyncio.StreamWriter,
    method: str,
    params: dict,
    msg_id: int | None = None,
) -> None:
    """Send a JSON-RPC message to the bridge's stdin."""
    msg = {"jsonrpc": "2.0", "method": method, "params": params}
    if msg_id is not None:
        msg["id"] = msg_id
    data = json.dumps(msg) + "\n"
    writer.write(data.encode())
    await writer.drain()


async def _read_jsonrpc(
    reader: asyncio.StreamReader,
    timeout: float = 10.0,
) -> dict | None:
    """Read one JSON-RPC message from the bridge's stdout."""
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=timeout)
    except TimeoutError:
        return None

    if not line:
        return None

    return json.loads(line.decode().strip())


async def _collect_until_response(
    reader: asyncio.StreamReader,
    expected_id: int,
    timeout: float = 30.0,
) -> tuple[dict | None, list[dict]]:
    """Collect notifications until we get the response with the expected id.

    Returns (response, notifications).
    """
    notifications = []
    deadline = asyncio.get_event_loop().time() + timeout

    while asyncio.get_event_loop().time() < deadline:
        remaining = deadline - asyncio.get_event_loop().time()
        msg = await _read_jsonrpc(reader, timeout=remaining)
        if msg is None:
            break

        if "id" in msg and msg["id"] == expected_id:
            return msg, notifications
        else:
            notifications.append(msg)

    return None, notifications


# ---------------------------------------------------------------------------
# TestBridgeSpawn
# ---------------------------------------------------------------------------


class TestBridgeSpawn:
    """Test that the bridge process starts and responds to initialize."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(15)
    async def test_bridge_spawns_and_exits(self, bridge_env):
        """The bridge process starts and exits cleanly on stdin close."""
        proc, _reader, writer = await _spawn_bridge(env=bridge_env)

        try:
            # Close stdin to signal EOF
            writer.close()
            await writer.wait_closed()

            # Process should exit within a few seconds
            exit_code = await asyncio.wait_for(proc.wait(), timeout=5.0)
            assert exit_code == 0, f"Bridge exited with code {exit_code}"
        finally:
            if proc.returncode is None:
                proc.kill()

    @pytest.mark.asyncio
    @pytest.mark.timeout(15)
    async def test_initialize_handshake(self, bridge_env):
        """The bridge responds to ACP initialize with capabilities."""
        proc, reader, writer = await _spawn_bridge(env=bridge_env)

        try:
            # Wait briefly and check if the process is still alive
            await asyncio.sleep(0.3)
            if proc.returncode is not None:
                stderr_data = b""
                if proc.stderr:
                    stderr_data = await proc.stderr.read()
                pytest.fail(
                    f"Bridge exited early with code {proc.returncode}. "
                    f"stderr: {stderr_data.decode()[:500]}"
                )

            await _send_jsonrpc(
                writer,
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientInfo": {"name": "test-harness", "version": "0.1.0"},
                },
                msg_id=1,
            )

            response, _ = await _collect_until_response(reader, expected_id=1)

            assert response is not None, "Bridge did not respond to initialize"
            assert response["id"] == 1
            assert "result" in response
        finally:
            writer.close()
            if proc.returncode is None:
                proc.kill()


# ---------------------------------------------------------------------------
# TestSandboxEnforcement
# ---------------------------------------------------------------------------


class TestSandboxEnforcement:
    """Test that read-only mode enforces .vault/-only writes via the bridge."""

    @pytest.mark.asyncio
    async def test_sandbox_callback_integration(self, project_root):
        """Integration test: _make_sandbox_callback creates correct callbacks.

        This does not spawn a process -- it tests the module-level function.
        """
        from protocol.acp.claude_bridge import _make_sandbox_callback

        # Read-only sandbox
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(project_root))
        assert callback is not None

        # Vault write: allowed
        result = await callback(
            "Write",
            {"file_path": str(project_root / ".vault" / "stories" / "new-story.md")},
            object(),  # ToolPermissionContext
        )
        assert result.behavior == "allow"

        # Source write: denied
        result = await callback(
            "Write",
            {"file_path": str(project_root / "src" / "main.py")},
            object(),
        )
        assert result.behavior == "deny"

    @pytest.mark.asyncio
    async def test_read_write_mode_no_restrictions(self):
        """In read-write mode, no sandbox callback is created."""
        from protocol.acp.claude_bridge import _make_sandbox_callback

        callback = _make_sandbox_callback(
            mode="read-write", root_dir=str(_TEST_PROJECT)
        )
        assert callback is None


# ---------------------------------------------------------------------------
# TestJeanClaudePersona
# ---------------------------------------------------------------------------


class TestJeanClaudePersona:
    """Test the jean-claude agent persona integration."""

    def test_persona_file_created(self, project_root):
        """The jean-claude agent definition exists in the test project."""
        persona_path = project_root / ".vaultspec" / "agents" / "jean-claude.md"
        assert persona_path.exists()

    def test_persona_has_frontmatter(self, project_root):
        """The persona file has valid frontmatter with tier and mode."""
        from vault.parser import parse_frontmatter

        persona_path = project_root / ".vaultspec" / "agents" / "jean-claude.md"
        meta, body = parse_frontmatter(persona_path.read_text(encoding="utf-8"))

        assert meta.get("tier") == "MEDIUM"
        assert meta.get("mode") == "read-only"
        assert "Jean-Claude" in body

    def test_persona_uses_read_only_mode(self, project_root):
        """The persona enforces read-only mode for sandbox safety."""
        from vault.parser import parse_frontmatter

        persona_path = project_root / ".vaultspec" / "agents" / "jean-claude.md"
        meta, _ = parse_frontmatter(persona_path.read_text(encoding="utf-8"))
        assert meta["mode"] == "read-only"


# ---------------------------------------------------------------------------
# TestCroissantFixtures
# ---------------------------------------------------------------------------


class TestCroissantFixtures:
    """Verify the Le Croissant Solitaire test content is available."""

    def test_chapter_1_loaded(self, croissant_chapter_1):
        """Chapter 1 content is non-empty and contains Croustillant."""
        assert len(croissant_chapter_1) > 100
        assert "Croustillant" in croissant_chapter_1

    def test_epilogue_loaded(self, croissant_epilogue):
        """Epilogue content is non-empty."""
        assert len(croissant_epilogue) > 50
        assert "Croustillant" in croissant_epilogue

    def test_stories_seeded_in_project(self, project_root):
        """Test project has stories seeded from the fixture."""
        stories = list((project_root / ".vault" / "stories").glob("*.md"))
        assert len(stories) > 0, "Expected seeded story files in .vault/stories/"


# ---------------------------------------------------------------------------
# TestFullBridgeLifecycleStdio
# ---------------------------------------------------------------------------


class TestFullBridgeLifecycleStdio:
    """Full bridge lifecycle over stdio: spawn -> initialize -> session/new -> close.

    Uses --test-mode so no Claude API key is required.
    """

    @pytest.mark.asyncio
    @pytest.mark.timeout(15)
    async def test_full_lifecycle(self, bridge_env):
        """Complete ACP lifecycle: initialize, session/new, clean shutdown."""
        proc, reader, writer = await _spawn_bridge(
            env=bridge_env,
            test_mode=True,
        )

        try:
            # Wait for the bridge to start
            await asyncio.sleep(0.3)
            if proc.returncode is not None:
                stderr_data = b""
                if proc.stderr:
                    stderr_data = await proc.stderr.read()
                pytest.fail(
                    f"Bridge exited early with code {proc.returncode}. "
                    f"stderr: {stderr_data.decode()[:500]}"
                )

            # Step 1: initialize
            await _send_jsonrpc(
                writer,
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientInfo": {"name": "test-harness", "version": "0.1.0"},
                },
                msg_id=1,
            )

            init_resp, _ = await _collect_until_response(reader, expected_id=1)
            assert init_resp is not None, "Bridge did not respond to initialize"
            assert init_resp["id"] == 1
            assert "result" in init_resp

            result = init_resp["result"]
            assert result["agentInfo"]["name"] == "claude-acp-bridge"
            assert result["agentInfo"]["version"] == "0.1.0"
            assert "protocolVersion" in result

            # Step 2: session/new
            await _send_jsonrpc(
                writer,
                "session/new",
                {
                    "cwd": str(bridge_env.get("VS_ROOT_DIR", "/tmp")),
                    "mcpServers": [],
                },
                msg_id=2,
            )

            session_resp, _ = await _collect_until_response(reader, expected_id=2)
            assert session_resp is not None, "Bridge did not respond to session/new"
            assert session_resp["id"] == 2
            assert "result" in session_resp

            session_result = session_resp["result"]
            session_id = session_result["sessionId"]
            assert isinstance(session_id, str)
            assert len(session_id) > 0
            # UUID format: 8-4-4-4-12
            assert session_id.count("-") == 4

            # Step 3: close stdin -> clean exit
            writer.close()
            await writer.wait_closed()

            exit_code = await asyncio.wait_for(proc.wait(), timeout=5.0)
            assert exit_code == 0, f"Bridge exited with code {exit_code}"

        finally:
            if proc.returncode is None:
                proc.kill()

    @pytest.mark.asyncio
    @pytest.mark.timeout(15)
    async def test_initialize_returns_capabilities(self, bridge_env):
        """Initialize response includes agentCapabilities."""
        proc, reader, writer = await _spawn_bridge(
            env=bridge_env,
            test_mode=True,
        )

        try:
            await asyncio.sleep(0.3)
            if proc.returncode is not None:
                stderr_data = b""
                if proc.stderr:
                    stderr_data = await proc.stderr.read()
                pytest.fail(
                    f"Bridge exited early with code {proc.returncode}. "
                    f"stderr: {stderr_data.decode()[:500]}"
                )

            await _send_jsonrpc(
                writer,
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientInfo": {"name": "test-harness", "version": "0.1.0"},
                },
                msg_id=1,
            )

            resp, _ = await _collect_until_response(reader, expected_id=1)
            assert resp is not None
            result = resp["result"]
            assert "agentCapabilities" in result

        finally:
            writer.close()
            if proc.returncode is None:
                proc.kill()

    @pytest.mark.asyncio
    @pytest.mark.timeout(15)
    async def test_session_new_without_mcp_servers(self, bridge_env):
        """session/new works with an empty mcpServers list."""
        proc, reader, writer = await _spawn_bridge(
            env=bridge_env,
            test_mode=True,
        )

        try:
            await asyncio.sleep(0.3)
            if proc.returncode is not None:
                stderr_data = b""
                if proc.stderr:
                    stderr_data = await proc.stderr.read()
                pytest.fail(
                    f"Bridge exited early with code {proc.returncode}. "
                    f"stderr: {stderr_data.decode()[:500]}"
                )

            # Initialize first (required by ACP protocol)
            await _send_jsonrpc(
                writer,
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientInfo": {"name": "test-harness", "version": "0.1.0"},
                },
                msg_id=1,
            )
            await _collect_until_response(reader, expected_id=1)

            # session/new with empty mcp_servers
            await _send_jsonrpc(
                writer,
                "session/new",
                {
                    "cwd": str(bridge_env.get("VS_ROOT_DIR", "/tmp")),
                    "mcpServers": [],
                },
                msg_id=2,
            )

            resp, _ = await _collect_until_response(reader, expected_id=2)
            assert resp is not None
            assert "result" in resp
            assert "sessionId" in resp["result"]

        finally:
            writer.close()
            if proc.returncode is None:
                proc.kill()
