"""Parse/file-operation tests for the CLI sync engine.

Covers: frontmatter parsing, build_file, atomic_write, _is_cli_managed,
init_paths, SyncResult.
"""

from __future__ import annotations

import pytest

from ...core import (
    SyncResult,
    atomic_write,
    build_file,
    init_paths,
    print_summary,
)
from ...core import types as _types
from ...core.config_gen import _is_cli_managed
from ...core.types import CONFIG_HEADER
from ...vaultcore import parse_frontmatter
from .conftest import TEST_PROJECT

pytestmark = [pytest.mark.unit]


class TestParseFrontmatter:
    def test_valid_yaml(self):
        content = "---\nname: hello\ntrigger: always_on\n---\n\n# Body"
        meta, body = parse_frontmatter(content)
        assert meta["name"] == "hello"
        assert meta["trigger"] == "always_on"
        assert body.strip() == "# Body"

    def test_no_frontmatter(self):
        content = "# Just a heading\n\nSome text."
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_empty_frontmatter(self):
        """Empty frontmatter (no chars between ---) doesn't match the regex,
        so the whole content is returned as-is."""
        content = "---\n---\n\nBody content"
        meta, body = parse_frontmatter(content)
        assert meta == {}
        # Regex requires at least one char between delimiters, so body == original
        assert "Body content" in body

    def test_whitespace_only_frontmatter(self):
        """Frontmatter with only whitespace parses to empty dict."""
        content = "---\n \n---\n\nBody content"
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert body.strip() == "Body content"

    def test_leading_whitespace_stripped(self):
        content = "\n\n---\nname: test\n---\n\nbody"
        meta, body = parse_frontmatter(content)
        assert meta["name"] == "test"
        assert body.strip() == "body"

    def test_multiline_body_preserved(self):
        content = "---\nk: v\n---\n\nLine 1\nLine 2\nLine 3"
        _meta, body = parse_frontmatter(content)
        assert "Line 1\nLine 2\nLine 3" in body


class TestBuildFile:
    def test_round_trip(self):
        fm = {"name": "test-rule", "trigger": "always_on"}
        body = "# My Rule\n\nDo the thing."
        output = build_file(fm, body)
        assert output.startswith("---\n")
        assert "---\n\n" in output
        meta2, body2 = parse_frontmatter(output)
        assert meta2["name"] == "test-rule"
        assert "Do the thing." in body2

    def test_empty_body(self):
        fm = {"name": "empty"}
        output = build_file(fm, "")
        assert output.endswith("---\n\n")
        meta2, body2 = parse_frontmatter(output)
        assert meta2["name"] == "empty"
        assert body2.strip() == ""


class TestAtomicWrite:
    def test_creates_new_file(self):
        p = TEST_PROJECT / "new.md"
        atomic_write(p, "hello world")
        assert p.read_text(encoding="utf-8") == "hello world"

    def test_overwrites_existing(self):
        p = TEST_PROJECT / "existing.md"
        p.write_text("old content", encoding="utf-8")
        atomic_write(p, "new content")
        assert p.read_text(encoding="utf-8") == "new content"

    def test_no_temp_file_left(self):
        p = TEST_PROJECT / "clean.md"
        atomic_write(p, "data")
        assert not (TEST_PROJECT / "clean.md.tmp").exists()


class TestIsCliManaged:
    def test_managed_file(self):
        p = TEST_PROJECT / "CLAUDE.md"
        p.write_text(f"{CONFIG_HEADER}\nrest of content", encoding="utf-8")
        assert _is_cli_managed(p) is True

    def test_custom_file(self):
        p = TEST_PROJECT / "CLAUDE.md"
        p.write_text("# My custom config\n\nHand-written.", encoding="utf-8")
        assert _is_cli_managed(p) is False

    def test_nonexistent_file(self):
        p = TEST_PROJECT / "nope.md"
        assert _is_cli_managed(p) is False

    def test_empty_file(self):
        p = TEST_PROJECT / "empty.md"
        p.write_text("", encoding="utf-8")
        assert _is_cli_managed(p) is False


class TestInitPaths:
    def test_sets_globals(self):
        init_paths(TEST_PROJECT)
        assert TEST_PROJECT == _types.ROOT_DIR
        assert TEST_PROJECT / ".vaultspec" / "rules" / "rules" == _types.RULES_SRC_DIR
        assert TEST_PROJECT / ".vaultspec" / "rules" / "agents" == _types.AGENTS_SRC_DIR
        assert TEST_PROJECT / ".vaultspec" / "rules" / "skills" == _types.SKILLS_SRC_DIR
        assert TEST_PROJECT / ".vaultspec" / "rules" / "system" == _types.SYSTEM_SRC_DIR
        assert (
            TEST_PROJECT / ".vaultspec" / "rules" / "system" / "framework.md"
            == _types.FRAMEWORK_CONFIG_SRC
        )
        assert (
            TEST_PROJECT / ".vaultspec" / "rules" / "system" / "project.md"
            == _types.PROJECT_CONFIG_SRC
        )

    def test_tool_configs_populated(self):
        init_paths(TEST_PROJECT)
        assert "claude" in _types.TOOL_CONFIGS
        assert "gemini" in _types.TOOL_CONFIGS
        assert "agent" in _types.TOOL_CONFIGS
        assert "agents" in _types.TOOL_CONFIGS
        expected_rules = TEST_PROJECT / ".claude" / "rules"
        assert _types.TOOL_CONFIGS["claude"].rules_dir == expected_rules


class TestSyncResult:
    def test_default_values(self):
        r = SyncResult()
        assert r.added == 0
        assert r.updated == 0
        assert r.skipped == 0
        assert r.pruned == 0
        assert r.errors == []

    def test_print_summary_no_changes(self, capsys):
        print_summary("Test", SyncResult())
        captured = capsys.readouterr()
        assert "no changes" in captured.out

    def test_print_summary_with_counts(self, capsys):
        r = SyncResult(added=2, updated=1, pruned=3)
        print_summary("Rules", r)
        captured = capsys.readouterr()
        assert "2 added" in captured.out
        assert "1 updated" in captured.out
        assert "3 pruned" in captured.out
