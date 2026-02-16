"""Tests for SubagentClient file I/O passthrough and read-only enforcement.

Verifies that write_text_file in read-only mode only permits writes to
.vault/ paths, rejecting all other destinations.
"""

from __future__ import annotations

import pytest

from protocol.acp.client import SubagentClient

pytestmark = [pytest.mark.unit]


class TestReadOnlyModeEnforcement:
    """Tests that read-only mode restricts writes to .vault/ only."""

    @pytest.fixture
    def readonly_client(self, test_root_dir):
        """SubagentClient in read-only mode."""
        return SubagentClient(root_dir=test_root_dir, debug=False, mode="read-only")

    @pytest.fixture
    def readwrite_client(self, test_root_dir):
        """SubagentClient in default read-write mode."""
        return SubagentClient(root_dir=test_root_dir, debug=False, mode="read-write")

    @pytest.mark.asyncio
    async def test_readonly_allows_vault_writes(self, readonly_client, test_root_dir):
        """Read-only mode permits writes to .vault/ directory."""
        target = test_root_dir / ".vault" / "adr" / "test-output.md"
        await readonly_client.write_text_file(
            content="# ADR Output",
            path=str(target),
            session_id="s1",
        )
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "# ADR Output"

    @pytest.mark.asyncio
    async def test_readonly_blocks_source_writes(self, readonly_client, test_root_dir):
        """Read-only mode rejects writes outside .vault/ directory."""
        target = test_root_dir / "src" / "main.py"
        with pytest.raises(ValueError, match="read-only mode"):
            await readonly_client.write_text_file(
                content="# Should not be written",
                path=str(target),
                session_id="s1",
            )

    @pytest.mark.asyncio
    async def test_readonly_blocks_root_writes(self, readonly_client, test_root_dir):
        """Read-only mode rejects writes to the project root."""
        target = test_root_dir / "config.toml"
        with pytest.raises(ValueError, match="read-only mode"):
            await readonly_client.write_text_file(
                content="[settings]",
                path=str(target),
                session_id="s1",
            )

    @pytest.mark.asyncio
    async def test_readwrite_allows_any_writes(self, readwrite_client, test_root_dir):
        """Read-write mode permits writes to any path in workspace."""
        target = test_root_dir / "src" / "main.py"
        await readwrite_client.write_text_file(
            content="fn main() {}",
            path=str(target),
            session_id="s1",
        )
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "fn main() {}"

    @pytest.mark.asyncio
    async def test_readonly_tracks_vault_writes(self, readonly_client, test_root_dir):
        """Read-only client tracks .vault/ writes in written_files list."""
        target = test_root_dir / ".vault" / "plan" / "output.md"
        await readonly_client.write_text_file(
            content="# Plan",
            path=str(target),
            session_id="s1",
        )
        assert str(target) in readonly_client.written_files

    @pytest.mark.asyncio
    async def test_readonly_blocks_vaultspec_writes(
        self, readonly_client, test_root_dir
    ):
        """Read-only mode rejects writes to .vaultspec/ (not .vault/)."""
        target = test_root_dir / ".vaultspec" / "agents" / "rogue.md"
        with pytest.raises(ValueError, match="read-only mode"):
            await readonly_client.write_text_file(
                content="# Rogue agent",
                path=str(target),
                session_id="s1",
            )
