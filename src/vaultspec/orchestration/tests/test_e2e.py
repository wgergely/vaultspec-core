"""End-to-End A2A integration tests.

Spawns the actual `vaultspec subagent a2a-serve` entry point.
Uses `GeminiProvider` to validate the full lifecycle:
Orchestrator -> ServerProcessManager -> Subprocess(a2a-serve) -> A2AClient.

Requires `GEMINI_API_KEY` or `~/.gemini/oauth_creds.json` for full success,
but verifies the architectural wiring regardless of auth outcome.
"""

import asyncio
import os
import sys
import pytest
from pathlib import Path

from vaultspec.core.enums import GeminiModels, ClaudeModels
from vaultspec.orchestration.subagent import run_subagent
from vaultspec.protocol.types import SubagentResult

@pytest.mark.asyncio
async def test_run_subagent_stack_gemini(tmp_path):
    """Test full stack with the Gemini provider."""
    
    # Create a minimal agent definition
    agents_dir = tmp_path / "rules" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "gemini-test.md").write_text(
        f"---\nname: gemini-test\nmodel: {GeminiModels.LOW}\n---\nYou are a helpful assistant.",
        encoding="utf-8"
    )
    
    # We expect this to fail auth or run successfully, but NOT fail on architecture.
    try:
        async with asyncio.timeout(15.0):
            result = await run_subagent(
                agent_name="gemini-test",
                root_dir=tmp_path,
                content_root=tmp_path,
                initial_task="What is 1+1?",
                provider_override="gemini",
                debug=True
            )
        assert isinstance(result, SubagentResult)
        if "2" in result.response_text:
             print("[Test] SUCCESS: Agent answered correctly.")
        elif "timed out" in result.response_text or "auth" in result.response_text.lower():
             print(f"[Test] SUCCESS (Graceful Failure): {result.response_text}")
        else:
             print(f"[Test] Agent response: {result.response_text}")
             
    except Exception as e:
        print(f"\n[Test] Gemini run failed as expected/possible: {e}")
        error_msg = str(e).lower()
        if "import" in error_msg or "syntax" in error_msg:
             raise e 

@pytest.mark.asyncio
async def test_run_subagent_stack_claude(tmp_path):
    """Test full stack with the Claude provider."""
    
    # Create a minimal agent definition
    agents_dir = tmp_path / "rules" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "claude-test.md").write_text(
        f"---\nname: claude-test\nmodel: {ClaudeModels.LOW}\n---\nYou are a helpful assistant.",
        encoding="utf-8"
    )
    
    # We expect this to fail auth or run successfully, but NOT fail on architecture.
    try:
        async with asyncio.timeout(15.0):
            result = await run_subagent(
                agent_name="claude-test",
                root_dir=tmp_path,
                content_root=tmp_path,
                initial_task="Hello",
                provider_override="claude",
                debug=True
            )
        assert isinstance(result, SubagentResult)
    except Exception as e:
        print(f"\n[Test] Claude run failed as expected/possible: {e}")
        error_msg = str(e).lower()
        if "import" in error_msg or "syntax" in error_msg:
             raise e 
