"""A2A Server Process Manager.

Responsible for the lifecycle of A2A server subprocesses: spawning,
port discovery, readiness probing, stderr draining, orphan prevention,
and clean shutdown.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...protocol.providers import ProcessSpec

from ...orchestration.utils import kill_process_tree
from .server_registry import ServerRegistry, ServerState

logger = logging.getLogger(__name__)

# Timeout (seconds) for the server to bind a port and become ready.
_SERVER_READY_TIMEOUT: float = 5.0


@dataclass
class ActiveServer:
    """Metadata for a running A2A server."""

    pid: int
    port: int
    proc: asyncio.subprocess.Process
    stderr_task: asyncio.Task[None]
    session_id: str


class ServerProcessManager:
    """Central manager for A2A server process lifecycles."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        """Initialize the process manager."""
        if root_dir is None:
            root_dir = Path.cwd()
        self.registry = ServerRegistry(Path(root_dir))
        self._active_servers: dict[str, ActiveServer] = {}

    def list_active(self) -> dict[str, ServerState]:
        """Return currently active servers from the registry keyed by session_id."""
        return self.registry.list_active()

    async def _read_stdout_for_port(
        self, proc: asyncio.subprocess.Process
    ) -> int | None:
        """Read stdout to discover the assigned port."""
        if not proc.stdout:
            return None

        with contextlib.suppress(Exception):
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode().strip()
                logger.debug("[SERVER-STDOUT] %s", text)
                if text.startswith("PORT="):
                    try:
                        return int(text.split("PORT=")[1])
                    except ValueError:
                        logger.error("Failed to parse PORT from stdout: %s", text)
        return None

    async def _drain_stderr(
        self, proc: asyncio.subprocess.Process, debug: bool = False
    ) -> None:
        """Drain stderr to prevent buffer deadlock."""
        if not proc.stderr:
            return

        with contextlib.suppress(Exception):
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode().strip()
                if debug:
                    logger.debug("[SERVER-STDERR] %s", text)
                else:
                    logger.warning("[SERVER-STDERR] %s", text)

    def _force_cleanup(
        self, proc: asyncio.subprocess.Process, stderr_task: asyncio.Task[None]
    ) -> None:
        """Force cleanup a process that failed to become active."""
        stderr_task.cancel()
        kill_process_tree(proc.pid)
        with contextlib.suppress(ProcessLookupError):
            proc.kill()

    async def spawn(
        self,
        spec: ProcessSpec,
        cwd: str,
        debug: bool = False,
    ) -> ActiveServer:
        """Spawn a new A2A server process.

        Args:
            spec: Process specification.
            cwd: Working directory for the process.
            debug: Whether to log stderr at debug level.

        Returns:
            ActiveServer containing process and connection info.

        Raises:
            RuntimeError: If process fails to start or port cannot be discovered.
        """
        import subprocess

        # Inject parent PID for orphan prevention
        env = dict(spec.env)
        env["VAULTSPEC_PARENT_PID"] = str(os.getpid())

        logger.debug(
            "Spawning A2A server process: %s %s",
            spec.executable,
            " ".join(str(a) for a in spec.args[:3]),
        )

        proc = await asyncio.create_subprocess_exec(
            spec.executable,
            *spec.args,
            env=env,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,  # Keep open so we can write to it if needed
        )

        # 1. Start draining stderr to prevent block
        stderr_task = asyncio.create_task(self._drain_stderr(proc, debug))

        # 2. Read stdout to discover port
        port_task = asyncio.create_task(self._read_stdout_for_port(proc))
        try:
            port = await asyncio.wait_for(port_task, timeout=10.0)
        except TimeoutError:
            self._force_cleanup(proc, stderr_task)
            raise RuntimeError(
                "Timed out waiting for PORT= assignment from server stdout"
            ) from None

        if port is None:
            self._force_cleanup(proc, stderr_task)
            raise RuntimeError("Server process exited before announcing PORT=")

        session_id = str(uuid.uuid4())

        # Determine model/provider dynamically from spec if present, else fallback
        model = getattr(spec, "model_override", "unknown")
        provider = "unknown"
        if "claude" in spec.executable or "claude" in model:
            provider = "claude"
        elif "gemini" in spec.executable or "gemini" in model:
            provider = "gemini"

        # 3. Write state to registry
        state = ServerState(
            session_id=session_id,
            pid=proc.pid,
            port=port,
            executable=spec.executable,
            args=spec.args,
            model=model,
            provider=provider,
            spawn_time=asyncio.get_running_loop().time(),
            cwd=cwd,
        )
        self.registry.register(state)

        active_server = ActiveServer(
            pid=proc.pid,
            port=port,
            proc=proc,
            stderr_task=stderr_task,
            session_id=session_id,
        )
        self._active_servers[session_id] = active_server
        return active_server

    async def wait_ready(self, server: ActiveServer) -> None:
        """Block until the server responds to the readiness probe.

        Polls /.well-known/agent-card.json with exponential backoff.

        Args:
            server: The active server to probe.

        Raises:
            TimeoutError: If the server does not become ready.
            RuntimeError: If the process exits before becoming ready.
        """
        import httpx

        url = f"http://127.0.0.1:{server.port}/.well-known/agent-card.json"

        start_time = asyncio.get_running_loop().time()
        delay = 0.05
        max_delay = 1.0

        async with httpx.AsyncClient() as client:
            while (
                asyncio.get_running_loop().time() - start_time < _SERVER_READY_TIMEOUT
            ):
                if server.proc.returncode is not None:
                    raise RuntimeError(
                        f"Server process {server.proc.returncode} during startup"
                    )

                try:
                    resp = await client.get(url, timeout=1.0)
                    if resp.status_code == 200:
                        logger.debug("Server ready at port %d", server.port)
                        return
                except httpx.RequestError:
                    pass

                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)

        raise TimeoutError(
            f"Server failed to become ready within {_SERVER_READY_TIMEOUT}s"
        )

    async def shutdown(self, server: ActiveServer) -> None:
        """Gracefully teardown an active server process.

        Args:
            server: The active server to shut down.
        """
        logger.debug("Shutting down server pid=%s port=%s", server.pid, server.port)

        self.registry.unregister(server.session_id)
        self._active_servers.pop(server.session_id, None)

        # Cancel stderr task
        server.stderr_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await server.stderr_task

        # Kill the process tree (important on Windows for Claude's node child)
        kill_process_tree(server.pid)

        try:
            await asyncio.wait_for(server.proc.wait(), timeout=5.0)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                server.proc.kill()
            await server.proc.wait()

        # Clean up asyncio subprocess transports
        from ...orchestration.utils import cleanup_subprocess_transports

        await cleanup_subprocess_transports(server.proc)

    async def shutdown_all(self) -> None:
        """Teardown all managed servers concurrently."""
        servers = list(self._active_servers.values())
        if not servers:
            return

        logger.info("Shutting down %d active servers", len(servers))
        tasks = [asyncio.create_task(self.shutdown(server)) for server in servers]
        await asyncio.gather(*tasks, return_exceptions=True)
