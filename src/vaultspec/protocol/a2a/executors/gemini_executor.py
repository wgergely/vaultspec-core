"""A2A AgentExecutor for Gemini CLI.

Executes tasks by spawning the `gemini` CLI for each turn.
This treats the CLI as a stateless completions engine, managing context
by prepending it to the prompt if necessary (though current implementation
is simple single-turn).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import TYPE_CHECKING

from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart

from .base import BaseA2AExecutor
from ...providers.base import resolve_executable

if TYPE_CHECKING:
    from a2a.server.events import EventQueue

logger = logging.getLogger(__name__)

__all__ = ["GeminiA2AExecutor"]


class GeminiA2AExecutor(BaseA2AExecutor):
    """Executor that delegates to the Google Gemini CLI."""

    def __init__(
        self,
        *,
        model: str,
        root_dir: str,
        mode: str = "read-write",
        **kwargs,
    ) -> None:
        super().__init__(max_retries=3, retry_base_delay=1.0)
        self._model = model
        self._root_dir = root_dir
        self._mode = mode
        
        # Resolve executable correctly for Windows (handling .cmd/.bat)
        cli_name = "gemini"
        exe, args = resolve_executable(cli_name)
        self._cli_executable = exe
        self._cli_prefix_args = args

    async def _on_task_start(
        self, task_id: str, context_id: str, cancel_event: asyncio.Event
    ) -> None:
        """Verify CLI availability and responsiveness."""
        if not shutil.which(self._cli_executable) and not os.path.exists(self._cli_executable):
             logger.debug("Gemini executable '%s' not found in PATH or disk.", self._cli_executable)
             pass
        else:
             logger.debug("Gemini executable '%s' found.", self._cli_executable)
             
        # Pre-flight check: ensure CLI is responsive
        try:
            logger.debug("Running pre-flight check: %s --version", self._cli_executable)
            proc = await asyncio.create_subprocess_exec(
                self._cli_executable,
                *(self._cli_prefix_args + ["--version"]),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                cwd=self._root_dir,
            )
            # Enforce strict 2s timeout for pre-flight
            await asyncio.wait_for(proc.wait(), timeout=2.0)
            if proc.returncode != 0:
                logger.warning("Gemini pre-flight check failed with code %s", proc.returncode)
        except asyncio.TimeoutError:
            logger.error("Gemini CLI pre-flight check timed out (2s). CLI is unresponsive.")
            if proc.returncode is None:
                proc.kill()
            raise RuntimeError("Gemini CLI is unresponsive/hanging (pre-flight timeout)")
        except Exception as e:
            logger.error("Gemini CLI pre-flight check failed: %s", e)
            raise RuntimeError(f"Gemini CLI pre-flight failed: {e}") from e

    async def _run_stream(
        self,
        *,
        prompt: str,
        updater: TaskUpdater,
        context_id: str,
        task_id: str,
        cancel_event: asyncio.Event,
    ) -> bool:
        """Run `gemini <prompt>` and stream stdout."""
        
        cmd_args = self._cli_prefix_args + [prompt]
        
        logger.info("Spawning Gemini CLI: %s %s", self._cli_executable, " ".join(cmd_args))
        
        try:
            process = await asyncio.create_subprocess_exec(
                self._cli_executable,
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                cwd=self._root_dir,
            )
        except Exception as e:
            logger.error("Failed to spawn Gemini CLI: %s", e)
            raise RuntimeError(f"Failed to spawn Gemini CLI: {e}") from e

        full_text = []
        
        async def read_stream(stream, is_stderr):
            while True:
                if cancel_event.is_set():
                    return

                try:
                    line = await asyncio.wait_for(stream.readline(), timeout=1.0)
                except asyncio.TimeoutError:
                    if process.returncode is not None:
                        break
                    continue
                
                if not line:
                    break
                    
                text = line.decode(errors="replace")
                if is_stderr:
                    logger.debug("[gemini stderr] %s", text.strip())
                else:
                    full_text.append(text)
                    await updater.add_artifact(
                        parts=[Part(root=TextPart(text=text))],
                        artifact_id=task_id,
                        name="response",
                        append=True, 
                        last_chunk=False
                    )

        try:
            tasks = [
                asyncio.create_task(read_stream(process.stdout, False)),
                asyncio.create_task(read_stream(process.stderr, True)),
            ]
            
            # Enforce 1s timeout to ensure we fail fast in keyless environments/tests
            try:
                await asyncio.wait_for(process.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                logger.error("Gemini CLI timed out (1s limit)")
                process.kill()
                await process.wait()
                
                # Notify client of failure so it stops waiting
                await updater.failed(
                    message=updater.new_agent_message(
                        parts=[Part(root=TextPart(text="Gemini CLI timed out (auth/input required)"))]
                    )
                )
                raise RuntimeError("Gemini CLI timed out")

            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            
            if process.returncode != 0:
                raise RuntimeError(f"Gemini CLI exited with code {process.returncode}")
                
            await updater.complete(
                message=updater.new_agent_message(
                    parts=[Part(root=TextPart(text="".join(full_text)))]
                )
            )
            return False 

        except Exception as e:
            logger.error("Gemini execution failed: %s", e)
            if process.returncode is None:
                process.kill()
            raise e