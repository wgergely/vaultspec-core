"""Sandbox tests for ClaudeACPBridge.

Covers: _make_sandbox_callback, _is_vault_path.
"""

from __future__ import annotations

import pytest

from tests.constants import TEST_PROJECT
from vaultspec.protocol.sandbox import (
    _SHELL_TOOLS,
    _is_vault_path,
    _make_sandbox_callback,
)

pytestmark = [pytest.mark.unit]


class TestSandboxCallback:
    """Test the can_use_tool sandbox enforcement."""

    def test_read_write_mode_returns_none(self):
        """In read-write mode, no restrictions apply (callback is None)."""
        callback = _make_sandbox_callback(mode="read-write", root_dir=str(TEST_PROJECT))
        assert callback is None

    @pytest.mark.asyncio
    async def test_read_only_allows_vault_write(self):
        """In read-only mode, writes to .vault/ are allowed."""
        # .vault/adr already exists in test-project/
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))
        assert callback is not None

        result = await callback(
            "Write",
            {"file_path": str(TEST_PROJECT / ".vault" / "adr" / "test.md")},
            object(),  # ToolPermissionContext
        )
        assert result.behavior == "allow"

    @pytest.mark.asyncio
    async def test_read_only_blocks_non_vault_write(self):
        """In read-only mode, writes outside .vault/ are denied."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))

        result = await callback(
            "Write",
            {"file_path": str(TEST_PROJECT / "src" / "main.py")},
            object(),
        )
        assert result.behavior == "deny"
        assert (
            ".vault" in result.message.lower() or "read-only" in result.message.lower()
        )

    @pytest.mark.asyncio
    async def test_read_only_blocks_edit(self):
        """Edit tool is blocked outside .vault/ in read-only mode."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))

        result = await callback(
            "Edit", {"file_path": str(TEST_PROJECT / "README.md")}, object()
        )
        assert result.behavior == "deny"

    @pytest.mark.asyncio
    async def test_read_only_blocks_multiedit(self):
        """MultiEdit tool is blocked outside .vault/ in read-only mode."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))

        result = await callback(
            "MultiEdit", {"file_path": str(TEST_PROJECT / "lib.py")}, object()
        )
        assert result.behavior == "deny"

    @pytest.mark.asyncio
    async def test_read_only_blocks_notebook_edit(self):
        """NotebookEdit tool is blocked outside .vault/ in read-only mode."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))

        result = await callback(
            "NotebookEdit",
            {"file_path": str(TEST_PROJECT / "nb.ipynb")},
            object(),
        )
        assert result.behavior == "deny"

    @pytest.mark.asyncio
    async def test_read_only_allows_read_tools(self):
        """Read-only mode does not block non-write tools."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))

        for tool in ["Read", "Glob", "Grep", "WebSearch"]:
            result = await callback(
                tool,
                {"file_path": str(TEST_PROJECT / "src" / "main.py")},
                object(),
            )
            assert result.behavior == "allow", f"{tool} should be allowed"

    @pytest.mark.asyncio
    async def test_read_only_vault_nested_paths(self):
        """Deep paths inside .vault/ are allowed."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))

        result = await callback(
            "Write",
            {
                "file_path": str(
                    TEST_PROJECT / ".vault" / "exec" / "2026-02-15-test" / "step-1.md"
                )
            },
            object(),
        )
        assert result.behavior == "allow"

    @pytest.mark.asyncio
    async def test_read_only_blocks_vault_prefix_attack(self):
        """Paths like .vault-evil/ outside .vault/ are blocked."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))

        for suffix in [
            ".vault-evil/hack.md",
            ".vaultspec/lib/trojan.py",
            ".vault_backup/data.md",
        ]:
            result = await callback(
                "Write", {"file_path": str(TEST_PROJECT / suffix)}, object()
            )
            assert result.behavior == "deny", f"Should block: {suffix}"

    @pytest.mark.asyncio
    async def test_callback_deny_has_interrupt_false(self):
        """PermissionResultDeny includes interrupt=False."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))

        result = await callback(
            "Write", {"file_path": str(TEST_PROJECT / "bad.py")}, object()
        )
        assert result.interrupt is False

    @pytest.mark.asyncio
    async def test_callback_allow_has_null_fields(self):
        """PermissionResultAllow has updated_input=None and updated_permissions=None."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))

        result = await callback(
            "Read", {"file_path": str(TEST_PROJECT / "file.py")}, object()
        )
        assert result.updated_input is None
        assert result.updated_permissions is None


class TestIsVaultPath:
    """Test the _is_vault_path helper."""

    def test_vault_subdir(self):
        assert (
            _is_vault_path(
                str(TEST_PROJECT / ".vault" / "adr" / "test.md"), str(TEST_PROJECT)
            )
            is True
        )

    def test_vault_root(self):
        assert _is_vault_path(str(TEST_PROJECT / ".vault"), str(TEST_PROJECT)) is True

    def test_outside_vault(self):
        assert (
            _is_vault_path(str(TEST_PROJECT / "src" / "main.py"), str(TEST_PROJECT))
            is False
        )

    def test_vault_prefix_not_vault(self):
        assert (
            _is_vault_path(
                str(TEST_PROJECT / ".vaultspec" / "file.py"), str(TEST_PROJECT)
            )
            is False
        )

    def test_outside_root(self):
        assert _is_vault_path("/completely/different/path", str(TEST_PROJECT)) is False


class TestShellToolsSandbox:
    """Test that shell tools are blocked in read-only mode."""

    def test_shell_tools_frozenset(self):
        """_SHELL_TOOLS contains 'Bash'."""

        assert isinstance(_SHELL_TOOLS, frozenset)
        assert "Bash" in _SHELL_TOOLS

    @pytest.mark.asyncio
    async def test_bash_denied_in_readonly_mode(self):
        """_make_sandbox_callback('read-only', ...) denies Bash tool."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))
        assert callback is not None

        result = await callback("Bash", {"command": "ls"}, object())
        assert result.behavior == "deny"
        assert (
            "read-only" in result.message.lower() or "shell" in result.message.lower()
        )

    def test_bash_allowed_in_readwrite_mode(self):
        """In read-write mode, callback is None (no restrictions, Bash allowed)."""
        callback = _make_sandbox_callback(mode="read-write", root_dir=str(TEST_PROJECT))
        assert callback is None

    @pytest.mark.asyncio
    async def test_write_tools_still_checked_in_readonly(self):
        """Write/Edit are still checked against .vault/ path in read-only mode."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))

        # Write outside .vault/ denied
        result = await callback(
            "Write", {"file_path": str(TEST_PROJECT / "src" / "hack.py")}, object()
        )
        assert result.behavior == "deny"

        # Write inside .vault/ allowed
        result = await callback(
            "Edit",
            {"file_path": str(TEST_PROJECT / ".vault" / "adr" / "test.md")},
            object(),
        )
        assert result.behavior == "allow"

    @pytest.mark.asyncio
    async def test_bash_deny_message_mentions_alternatives(self):
        """Deny message for Bash suggests alternative tools."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))

        result = await callback("Bash", {"command": "ls"}, object())
        assert result.behavior == "deny"
        # The message should mention Read, Glob, or Grep as alternatives
        msg_lower = result.message.lower()
        assert "read" in msg_lower or "glob" in msg_lower or "grep" in msg_lower

    @pytest.mark.asyncio
    async def test_bash_deny_has_interrupt_false(self):
        """Bash denial includes interrupt=False (non-interrupting)."""
        callback = _make_sandbox_callback(mode="read-only", root_dir=str(TEST_PROJECT))

        result = await callback("Bash", {"command": "echo hi"}, object())
        assert result.interrupt is False
