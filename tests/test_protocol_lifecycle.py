from __future__ import annotations

import pathlib
import sys
import tempfile
from typing import Any, Dict, List, Optional

import pytest

from orchestration.dispatch import AgentNotFoundError, run_dispatch
from protocol.acp.types import DispatchResult
from protocol.providers.base import AgentProvider, CapabilityLevel, ProcessSpec

# ---------------------------------------------------------------------------
# Stub Agent Script
# ---------------------------------------------------------------------------

STUB_AGENT_PY = """
import sys
import json
import asyncio

async def main():
    # Very basic ACP-like stdio handler
    while True:
        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        try:
            req = json.loads(line)
            method = req.get("method")
            req_id = req.get("id")

            if method == "initialize":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {
                    "protocolVersion": 1,
                    "agentCapabilities": {"loadSession": True},
                    "agentInfo": {"name": "stub-agent", "version": "0.1.0"}
                }}
            elif method == "session/new":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {
                    "sessionId": "stub-session-123"
                }}
            elif method == "session/prompt":
                # Send some thought then the final answer
                thought = {"jsonrpc": "2.0", "method": "session/update", "params": {
                    "sessionId": "stub-session-123",
                    "update": {
                        "sessionUpdate": "agent_thought_chunk",
                        "content": {"type": "text", "text": "I am thinking..."}
                    }
                }}
                print(json.dumps(thought), flush=True)

                msg = {"jsonrpc": "2.0", "method": "session/update", "params": {
                    "sessionId": "stub-session-123",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "Hello from stub agent!"}
                    }
                }}
                print(json.dumps(msg), flush=True)

                resp = {"jsonrpc": "2.0", "id": req_id, "result": {
                    "stopReason": "end_turn"
                }}
            else:
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}

            print(json.dumps(resp), flush=True)
        except Exception:
            break

if __name__ == "__main__":
    asyncio.run(main())
"""

# ---------------------------------------------------------------------------
# Stub Provider
# ---------------------------------------------------------------------------


class StubProvider(AgentProvider):
    def __init__(self, stub_script_path: pathlib.Path):
        self._name = "stub-provider"
        self.stub_script_path = stub_script_path
        self._supported_models = ["stub-model"]

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_models(self) -> List[str]:
        return self._supported_models

    def prepare_process(
        self,
        agent_name: str,
        agent_meta: Dict[str, Any],
        agent_persona: str,
        task_context: str,
        root_dir: pathlib.Path,
        model_override: Optional[str] = None,
    ) -> ProcessSpec:
        return ProcessSpec(
            executable=sys.executable,
            args=[str(self.stub_script_path)],
            env={},
            cleanup_paths=[],
        )

    def get_model_capability(self, model: str) -> CapabilityLevel:
        return CapabilityLevel.MEDIUM

    def get_best_model_for_capability(self, level: CapabilityLevel) -> str:
        return "stub-model"

    def resolve_includes(
        self, text: str, root_dir: pathlib.Path, current_dir: pathlib.Path
    ) -> str:
        return text


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_not_found(mock_root_dir):
    with pytest.raises(AgentNotFoundError):
        await run_dispatch(
            agent_name="nonexistent",
            initial_task="hello",
            root_dir=mock_root_dir,
            interactive=False,
        )


@pytest.mark.asyncio
async def test_basic_dispatch_lifecycle_real_client(mock_root_dir, test_agent_md):
    """
    Test run_dispatch using the REAL DispatchClient and a real (stub) subprocess.
    This verifies the orchestration, connection, and interactive loop logic.
    """
    # Create the agent definition
    (mock_root_dir / ".rules" / "agents" / "test-agent.md").write_text(
        test_agent_md, encoding="utf-8"
    )

    # Create the stub agent script
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tf:
        tf.write(STUB_AGENT_PY)
        stub_script = pathlib.Path(tf.name)

    try:
        provider = StubProvider(stub_script)

        # Run dispatch with real client class and stub provider
        result = await run_dispatch(
            agent_name="test-agent",
            initial_task="Please say hello.",
            root_dir=mock_root_dir,
            interactive=False,
            provider_instance=provider,
            debug=True,
        )

        assert isinstance(result, DispatchResult)
        assert "Hello from stub agent!" in result.response_text
        assert result.session_id == "stub-session-123"

    finally:
        if stub_script.exists():
            stub_script.unlink()
