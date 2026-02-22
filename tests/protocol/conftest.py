"""Shared fixtures for Protocol Matrix tests."""

import asyncio
import logging
import os
import sys
from pathlib import Path

import httpx
import pytest


@pytest.fixture(autouse=True)
def force_debug_level(caplog):
    """Force caplog to capture DEBUG level logs for every test."""
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="vaultspec")


# --- Workspace ---


@pytest.fixture
def workspace(tmp_path):
    """Setup minimal workspace structure."""
    root = tmp_path
    (root / ".vaultspec" / "rules" / "agents").mkdir(parents=True)
    return root


# --- Agent Definitions ---


@pytest.fixture
def echo_agent_def() -> str:
    """Returns the definition for a deterministic Echo Agent."""
    return (
        "---\n"
        "tier: LOW\n"
        "mode: read-write\n"
        "---\n\n"
        "# Persona\n"
        "You are an Echo Agent. Your goal is to repeat the user's input exactly.\n"
        "Rules:\n"
        "1. Prefix your response with 'Echo: '.\n"
        "2. Do not add any other text, explanation, or markdown.\n"
        "3. If the input is empty, reply 'Echo: (empty)'.\n"
    )


@pytest.fixture
def state_agent_def() -> str:
    """Returns the definition for a deterministic State Agent."""
    return (
        "---\n"
        "tier: LOW\n"
        "mode: read-write\n"
        "---\n\n"
        "# Persona\n"
        "You are a State Agent. Your goal is to remember key-value pairs.\n"
        "Rules:\n"
        "1. If the user says 'Set <key>=<value>', reply 'OK'.\n"
        "2. If the user says 'Get <key>', reply with the value only.\n"
        "3. Do not add any other text.\n"
    )


# --- A2A Server Spawning ---


@pytest.fixture
async def agent_spawner(tmp_path):
    """Fixture to spawn an A2A agent server process."""
    processes = []

    async def _spawn(name: str, port: int, provider: str, root_dir: Path):
        # Ensure agent definition exists
        agent_def = root_dir / ".vaultspec" / "rules" / "agents" / f"{name}.md"
        if not agent_def.exists():
            agent_def.parent.mkdir(parents=True, exist_ok=True)
            agent_def.write_text(
                "---\ntier: LOW\n---\n# Persona\nEcho Agent", encoding="utf-8"
            )

        cmd = [
            sys.executable,
            "-m",
            "vaultspec.subagent_cli",
            "--root",
            str(root_dir),
            "a2a-serve",
            "--agent",
            name,
            "--port",
            str(port),
            "--executor",
            provider,
            "--mode",
            "read-write",
        ]

        logging.debug(f"Spawning A2A server: {name} on port {port}")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        processes.append(proc)

        url = f"http://localhost:{port}/.well-known/agent-card.json"

        for _i in range(20):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(url, timeout=1.0)
                    if resp.status_code == 200:
                        logging.debug(f"Agent {name} started successfully")
                        return f"http://localhost:{port}/"
            except (httpx.ConnectError, httpx.TimeoutException):
                pass

            if proc.returncode is not None:
                stdout, stderr = await proc.communicate()
                raise RuntimeError(
                    f"Agent {name} died (code {proc.returncode}).\n"
                    f"STDOUT: {stdout.decode()}\nSTDERR: {stderr.decode()}"
                )

            await asyncio.sleep(0.5)

        raise RuntimeError(f"Agent {name} startup timeout.")

    yield _spawn

    for p in processes:
        if p.returncode is None:
            p.terminate()
            try:
                await asyncio.wait_for(p.wait(), timeout=2.0)
            except TimeoutError:
                p.kill()


_SUBPROCESS_ENV_KEYS = (
    "PATH",
    "PYTHONPATH",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "VAULTSPEC_LOG_LEVEL",
    # Windows-specific vars required for subprocess execution
    "SYSTEMROOT",
    "TEMP",
    "TMP",
)


@pytest.fixture
def mcp_server_config(tmp_path):
    """Fixture to provide MCP server configuration for tool injection."""
    subprocess_env = {k: os.environ[k] for k in _SUBPROCESS_ENV_KEYS if k in os.environ}
    return {
        "vaultspec-mcp": {
            "command": sys.executable,
            "args": ["-m", "vaultspec.subagent_cli", "--root", str(tmp_path), "serve"],
            "env": subprocess_env,
        }
    }
