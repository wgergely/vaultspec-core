from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def _build_minimal_workspace(root: Path) -> None:
    """Create the minimal workspace structure needed for MCP startup."""
    (root / ".vault").mkdir()
    templates_dir = root / ".vaultspec" / "rules" / "templates"
    templates_dir.mkdir(parents=True)
    (templates_dir / "research.md").write_text(
        "---\n"
        "tags:\n"
        "  - '#research'\n"
        "  - '#{feature}'\n"
        "date: '{yyyy-mm-dd}'\n"
        "related: []\n"
        "---\n"
        "# {topic}\n",
        encoding="utf-8",
    )


def _read_startup_line(stream, sink: queue.Queue[bytes]) -> None:
    """Read stream lines without blocking the main test thread."""
    for line in iter(stream.readline, b""):
        sink.put(line)


@pytest.mark.integration
def test_mcp_entrypoint_starts_and_keeps_stdout_clean(tmp_path: Path) -> None:
    _build_minimal_workspace(tmp_path)

    env = os.environ.copy()
    env["VAULTSPEC_TARGET_DIR"] = str(tmp_path)

    proc = subprocess.Popen(
        [sys.executable, "-c", "from vaultspec_core.mcp_server.app import run; run()"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    stderr_queue: queue.Queue[bytes] = queue.Queue()
    stderr_thread = threading.Thread(
        target=_read_startup_line,
        args=(proc.stderr, stderr_queue),
        daemon=True,
    )
    stderr_thread.start()
    stdout_queue: queue.Queue[bytes] = queue.Queue()
    stdout_thread = threading.Thread(
        target=_read_startup_line,
        args=(proc.stdout, stdout_queue),
        daemon=True,
    )
    stdout_thread.start()

    try:
        startup_lines: list[str] = []
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                line = stderr_queue.get(timeout=0.25).decode("utf-8", errors="replace")
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue
            startup_lines.append(line)
            if "Starting vaultspec-mcp server root=" in line:
                break

        startup_output = "".join(startup_lines)
        assert "Starting vaultspec-mcp server" in startup_output, startup_output
        assert "root=" in startup_output, startup_output
        assert proc.poll() is None

        time.sleep(0.2)
        assert stdout_queue.empty()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
