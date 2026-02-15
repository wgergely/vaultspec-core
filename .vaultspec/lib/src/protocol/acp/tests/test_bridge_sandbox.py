"""Sandbox tests for ClaudeACPBridge.

Covers: _make_sandbox_callback, _is_vault_path.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from protocol.acp.claude_bridge import _is_vault_path, _make_sandbox_callback

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# TestSandboxCallback
# ---------------------------------------------------------------------------


class TestSandboxCallback:
    """Test the can_use_tool sandbox enforcement."""

    def test_read_write_mode_returns_none(self):
        """In read-write mode, no restrictions apply (callback is None)."""
        callback = _make_sandbox_callback(mode="read-write", root_dir="/workspace")
        assert callback is None

    @pytest.mark.asyncio
    async def test_read_only_allows_vault_write(self, tmp_path):
        """In read-only mode, writes to .vault/ are allowed."""
        vault_dir = tmp_path / ".vault" / "adr"
        vault_dir.mkdir(parents=True)
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(tmp_path))
        assert callback is not None

        result = await callback(
            "Write",
            {"file_path": str(tmp_path / ".vault" / "adr" / "test.md")},
            MagicMock(),  # ToolPermissionContext
        )
        assert result.behavior == "allow"

    @pytest.mark.asyncio
    async def test_read_only_blocks_non_vault_write(self, tmp_path):
        """In read-only mode, writes outside .vault/ are denied."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(tmp_path))

        result = await callback(
            "Write",
            {"file_path": str(tmp_path / "src" / "main.py")},
            MagicMock(),
        )
        assert result.behavior == "deny"
        assert (
            ".vault" in result.message.lower() or "read-only" in result.message.lower()
        )

    @pytest.mark.asyncio
    async def test_read_only_blocks_edit(self, tmp_path):
        """Edit tool is blocked outside .vault/ in read-only mode."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(tmp_path))

        result = await callback(
            "Edit", {"file_path": str(tmp_path / "README.md")}, MagicMock()
        )
        assert result.behavior == "deny"

    @pytest.mark.asyncio
    async def test_read_only_blocks_multiedit(self, tmp_path):
        """MultiEdit tool is blocked outside .vault/ in read-only mode."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(tmp_path))

        result = await callback(
            "MultiEdit", {"file_path": str(tmp_path / "lib.py")}, MagicMock()
        )
        assert result.behavior == "deny"

    @pytest.mark.asyncio
    async def test_read_only_blocks_notebook_edit(self, tmp_path):
        """NotebookEdit tool is blocked outside .vault/ in read-only mode."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(tmp_path))

        result = await callback(
            "NotebookEdit",
            {"file_path": str(tmp_path / "nb.ipynb")},
            MagicMock(),
        )
        assert result.behavior == "deny"

    @pytest.mark.asyncio
    async def test_read_only_allows_read_tools(self, tmp_path):
        """Read-only mode does not block non-write tools."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(tmp_path))

        for tool in ["Read", "Glob", "Grep", "Bash", "WebSearch"]:
            result = await callback(
                tool,
                {"file_path": str(tmp_path / "src" / "main.py")},
                MagicMock(),
            )
            assert result.behavior == "allow", f"{tool} should be allowed"

    @pytest.mark.asyncio
    async def test_read_only_vault_nested_paths(self, tmp_path):
        """Deep paths inside .vault/ are allowed."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(tmp_path))

        result = await callback(
            "Write",
            {
                "file_path": str(
                    tmp_path / ".vault" / "exec" / "2026-02-15-test" / "step-1.md"
                )
            },
            MagicMock(),
        )
        assert result.behavior == "allow"

    @pytest.mark.asyncio
    async def test_read_only_blocks_vault_prefix_attack(self, tmp_path):
        """Paths like .vault-evil/ outside .vault/ are blocked."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(tmp_path))

        for suffix in [
            ".vault-evil/hack.md",
            ".vaultspec/lib/trojan.py",
            ".vault_backup/data.md",
        ]:
            result = await callback(
                "Write", {"file_path": str(tmp_path / suffix)}, MagicMock()
            )
            assert result.behavior == "deny", f"Should block: {suffix}"

    @pytest.mark.asyncio
    async def test_callback_deny_has_interrupt_false(self, tmp_path):
        """PermissionResultDeny includes interrupt=False."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(tmp_path))

        result = await callback(
            "Write", {"file_path": str(tmp_path / "bad.py")}, MagicMock()
        )
        assert result.interrupt is False

    @pytest.mark.asyncio
    async def test_callback_allow_has_null_fields(self, tmp_path):
        """PermissionResultAllow has updated_input=None and updated_permissions=None."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(tmp_path))

        result = await callback(
            "Read", {"file_path": str(tmp_path / "file.py")}, MagicMock()
        )
        assert result.updated_input is None
        assert result.updated_permissions is None


# ---------------------------------------------------------------------------
# TestIsVaultPath
# ---------------------------------------------------------------------------


class TestIsVaultPath:
    """Test the _is_vault_path helper."""

    def test_vault_subdir(self, tmp_path):
        assert (
            _is_vault_path(str(tmp_path / ".vault" / "adr" / "test.md"), str(tmp_path))
            is True
        )

    def test_vault_root(self, tmp_path):
        assert _is_vault_path(str(tmp_path / ".vault"), str(tmp_path)) is True

    def test_outside_vault(self, tmp_path):
        assert _is_vault_path(str(tmp_path / "src" / "main.py"), str(tmp_path)) is False

    def test_vault_prefix_not_vault(self, tmp_path):
        assert (
            _is_vault_path(str(tmp_path / ".vaultspec" / "file.py"), str(tmp_path))
            is False
        )

    def test_outside_root(self, tmp_path):
        assert _is_vault_path("/completely/different/path", str(tmp_path)) is False
