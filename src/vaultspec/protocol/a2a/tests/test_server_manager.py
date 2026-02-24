"""Tests for A2A ServerProcessManager."""

import os
import sys

import pytest

from tests.constants import PROJECT_ROOT
from vaultspec.protocol.a2a.server_manager import ActiveServer, ServerProcessManager
from vaultspec.protocol.providers.base import ProcessSpec


@pytest.fixture
async def manager(tmp_path):
    """Provides a clean ServerProcessManager for tests."""
    mgr = ServerProcessManager(root_dir=tmp_path)
    yield mgr

    # Teardown: ensure all servers are shutdown
    await mgr.shutdown_all()


@pytest.mark.asyncio
async def test_spawn_and_shutdown_success(manager, tmp_path):
    """Test successful spawn, port discovery, and shutdown using a mock server."""

    mock_server_path = os.path.join(os.path.dirname(__file__), "mock_server.py")

    spec = ProcessSpec(
        executable=sys.executable,
        args=[mock_server_path],
        env=dict(os.environ),
        cleanup_paths=[],
    )

    # 1. Spawn
    server = await manager.spawn(spec, cwd=str(PROJECT_ROOT))

    assert isinstance(server, ActiveServer)
    assert server.port > 0
    assert server.pid > 0
    assert server.session_id in manager.list_active()

    # Wait until it's actually ready to serve
    await manager.wait_ready(server)

    # 2. Shutdown
    await manager.shutdown(server)

    assert server.session_id not in manager.list_active()
    assert server.proc.returncode is not None


@pytest.mark.asyncio
async def test_spawn_timeout_no_port(manager, tmp_path):
    """Test spawn failure when PORT= is never logged."""

    # We use python -c to run a one-liner that just hangs without printing PORT=
    spec = ProcessSpec(
        executable=sys.executable,
        args=["-c", "import time; time.sleep(12)"],
        env=dict(os.environ),
        cleanup_paths=[],
    )

    with pytest.raises(RuntimeError, match="Timed out waiting for PORT="):
        await manager.spawn(spec, cwd=str(tmp_path))
