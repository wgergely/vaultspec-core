"""Tests for the <vaultspec> managed content block tag parser."""

from __future__ import annotations

import pytest

from vaultspec_core.core.tags import (
    TagError,
    find_blocks,
    get_block_content,
    has_block,
    strip_block,
    upsert_block,
)

pytestmark = [pytest.mark.unit]


# --- find_blocks ---


class TestFindBlocks:
    def test_single_block(self):
        content = 'User content\n\n<vaultspec type="config">\nManaged\n</vaultspec>\n'
        blocks = find_blocks(content)
        assert len(blocks) == 1
        assert blocks[0].block_type == "config"
        assert blocks[0].start_line == 3
        assert blocks[0].end_line == 5

    def test_multiple_blocks_different_types(self):
        content = (
            '<vaultspec type="config">\nA\n</vaultspec>\n'
            '\n<vaultspec type="rules">\nB\n</vaultspec>\n'
        )
        blocks = find_blocks(content)
        assert len(blocks) == 2
        assert blocks[0].block_type == "config"
        assert blocks[1].block_type == "rules"

    def test_toml_commented_tags(self):
        content = '# <vaultspec type="agents">\n[agents.x]\n# </vaultspec>\n'
        blocks = find_blocks(content)
        assert len(blocks) == 1
        assert blocks[0].block_type == "agents"

    def test_empty_content(self):
        assert find_blocks("") == []

    def test_no_tags(self):
        assert find_blocks("Just some text\nno tags here\n") == []

    def test_duplicate_type_raises(self):
        content = (
            '<vaultspec type="config">\nA\n</vaultspec>\n'
            '<vaultspec type="config">\nB\n</vaultspec>\n'
        )
        with pytest.raises(TagError, match="Duplicate"):
            find_blocks(content)

    def test_unclosed_tag_raises(self):
        content = '<vaultspec type="config">\nContent without close\n'
        with pytest.raises(TagError, match="Unclosed"):
            find_blocks(content)

    def test_nested_tags_raises(self):
        content = (
            '<vaultspec type="config">\n'
            '<vaultspec type="rules">\n'
            "Nested\n</vaultspec>\n</vaultspec>\n"
        )
        with pytest.raises(TagError, match="Nested"):
            find_blocks(content)

    def test_orphaned_close_ignored(self):
        content = "Some text\n</vaultspec>\nMore text\n"
        blocks = find_blocks(content)
        assert blocks == []

    def test_tags_inside_code_fence_ignored(self):
        content = (
            "Normal text\n"
            "```\n"
            '<vaultspec type="config">\n'
            "This is inside code\n"
            "</vaultspec>\n"
            "```\n"
            "More text\n"
        )
        blocks = find_blocks(content)
        assert blocks == []

    def test_tags_inside_tilde_fence_ignored(self):
        content = '~~~python\n<vaultspec type="config">\n</vaultspec>\n~~~\n'
        blocks = find_blocks(content)
        assert blocks == []

    def test_real_tag_after_code_fence(self):
        content = (
            "```\n"
            '<vaultspec type="config">\n'
            "</vaultspec>\n"
            "```\n"
            '\n<vaultspec type="config">\n'
            "Real managed content\n"
            "</vaultspec>\n"
        )
        blocks = find_blocks(content)
        assert len(blocks) == 1
        assert blocks[0].block_type == "config"
        assert blocks[0].start_line == 6

    def test_error_includes_line_number(self):
        content = 'Line 1\nLine 2\n<vaultspec type="config">\nNo close\n'
        with pytest.raises(TagError) as exc_info:
            find_blocks(content)
        assert exc_info.value.line == 3


# --- has_block ---


class TestHasBlock:
    def test_exists(self):
        content = '<vaultspec type="config">\nX\n</vaultspec>\n'
        assert has_block(content, "config") is True

    def test_not_exists(self):
        content = '<vaultspec type="config">\nX\n</vaultspec>\n'
        assert has_block(content, "rules") is False

    def test_malformed_returns_false(self):
        content = '<vaultspec type="config">\nNo close\n'
        assert has_block(content, "config") is False


# --- get_block_content ---


class TestGetBlockContent:
    def test_extracts_content(self):
        content = '<vaultspec type="config">\nLine A\nLine B\n</vaultspec>\n'
        assert get_block_content(content, "config") == "Line A\nLine B"

    def test_empty_block(self):
        content = '<vaultspec type="config">\n</vaultspec>\n'
        assert get_block_content(content, "config") == ""

    def test_missing_block(self):
        content = "No tags here\n"
        assert get_block_content(content, "config") is None


# --- upsert_block ---


class TestUpsertBlock:
    def test_insert_into_empty_file(self):
        result = upsert_block("", "config", "Managed content")
        assert '<vaultspec type="config">' in result
        assert "Managed content" in result
        assert "</vaultspec>" in result

    def test_append_to_existing_content(self):
        result = upsert_block("User content\n", "config", "Managed")
        assert result.startswith("User content\n")
        assert '<vaultspec type="config">' in result
        assert "Managed" in result

    def test_replace_existing_block(self):
        original = (
            "User above\n\n"
            '<vaultspec type="config">\nOld content\n</vaultspec>\n\n'
            "User below\n"
        )
        result = upsert_block(original, "config", "New content")
        assert "New content" in result
        assert "Old content" not in result
        assert "User above" in result
        assert "User below" in result

    def test_toml_with_comment_prefix(self):
        result = upsert_block("", "agents", "[agents.x]\n", comment_prefix="# ")
        assert '# <vaultspec type="agents">' in result
        assert "# </vaultspec>" in result
        assert "[agents.x]" in result

    def test_preserves_other_blocks(self):
        original = (
            '<vaultspec type="config">\nConfig\n</vaultspec>\n\n'
            '<vaultspec type="rules">\nRules\n</vaultspec>\n'
        )
        result = upsert_block(original, "config", "New config")
        assert "New config" in result
        assert "Rules" in result

    def test_malformed_raises(self):
        content = '<vaultspec type="config">\nNo close\n'
        with pytest.raises(TagError):
            upsert_block(content, "config", "New")


# --- strip_block ---


class TestStripBlock:
    def test_removes_block(self):
        content = (
            "User above\n\n"
            '<vaultspec type="config">\nManaged\n</vaultspec>\n\n'
            "User below\n"
        )
        result = strip_block(content, "config")
        assert "Managed" not in result
        assert "<vaultspec" not in result
        assert "User above" in result
        assert "User below" in result

    def test_preserves_other_blocks(self):
        content = (
            '<vaultspec type="config">\nConfig\n</vaultspec>\n\n'
            '<vaultspec type="rules">\nRules\n</vaultspec>\n'
        )
        result = strip_block(content, "config")
        assert "Config" not in result
        assert "Rules" in result

    def test_noop_when_not_found(self):
        content = "Just user content\n"
        assert strip_block(content, "config") == content

    def test_strips_entire_file_if_only_block(self):
        content = '<vaultspec type="config">\nManaged only\n</vaultspec>\n'
        result = strip_block(content, "config")
        assert result == ""

    def test_malformed_raises(self):
        content = '<vaultspec type="config">\nNo close\n'
        with pytest.raises(TagError):
            strip_block(content, "config")
