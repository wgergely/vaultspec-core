"""Tests for the body-link checker."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .._base import Severity, VaultSnapshot
from ..body_links import check_body_links

if TYPE_CHECKING:
    from pathlib import Path

from ...models import DocumentMetadata

pytestmark = [pytest.mark.unit]

_ROOT_STR = "/fake/root"


def _snap(
    name: str,
    body: str,
    related: list[str] | None = None,
) -> tuple[Path, VaultSnapshot]:
    """Build a single-document snapshot for testing."""
    from pathlib import Path

    root = Path(_ROOT_STR)
    doc_path = root / ".vault" / "adr" / f"{name}.md"
    metadata = DocumentMetadata(
        tags=["#adr", "#test-feature"],
        date="2026-03-23",
        related=related or [],
    )
    return root, {doc_path: (metadata, body)}


class TestCheckBodyLinks:
    def test_reports_error_for_wiki_link_in_body(self):
        root, snapshot = _snap("doc1", "Text with [[my-target]] here.")
        result = check_body_links(root, snapshot=snapshot)
        assert not result.is_clean
        assert result.error_count == 1
        assert result.diagnostics[0].severity == Severity.ERROR
        assert "[[my-target]]" in result.diagnostics[0].message

    def test_reports_error_for_wiki_link_with_display_text(self):
        root, snapshot = _snap("doc2", "See [[my-target|Display]] here.")
        result = check_body_links(root, snapshot=snapshot)
        assert result.error_count == 1
        assert "[[my-target]]" in result.diagnostics[0].message

    def test_reports_error_for_markdown_path_link_in_body(self):
        root, snapshot = _snap("doc3", "See [the module](src/module.py) for details.")
        result = check_body_links(root, snapshot=snapshot)
        assert result.error_count == 1
        assert "[the module](src/module.py)" in result.diagnostics[0].message

    def test_ignores_markdown_url_links(self):
        root, snapshot = _snap(
            "doc4",
            "Visit [Docs](https://docs.example.com) and [Mail](mailto:x@y.com).",
        )
        result = check_body_links(root, snapshot=snapshot)
        assert result.is_clean

    def test_ignores_anchor_links(self):
        root, snapshot = _snap("doc5", "Jump to [Section](#overview).")
        result = check_body_links(root, snapshot=snapshot)
        assert result.is_clean

    def test_ignores_wiki_links_in_frontmatter_related(self):
        root, snapshot = _snap(
            "doc6",
            "Clean body text with no links.",
            related=["[[some-doc]]", "[[other-doc]]"],
        )
        result = check_body_links(root, snapshot=snapshot)
        assert result.is_clean

    def test_skips_index_files(self):
        from pathlib import Path

        root = Path(_ROOT_STR)
        doc_path = root / ".vault" / "test-feature.index.md"
        metadata = DocumentMetadata(
            tags=["#test-feature"],
            date="2026-03-23",
            related=["[[some-doc]]"],
        )
        body = "This index lists [[doc-a]] and [[doc-b]]."
        snapshot: VaultSnapshot = {doc_path: (metadata, body)}
        result = check_body_links(root, snapshot=snapshot)
        assert result.is_clean

    def test_feature_filter(self):
        from pathlib import Path

        root = Path(_ROOT_STR)
        path_a = root / ".vault" / "adr" / "a.md"
        path_b = root / ".vault" / "adr" / "b.md"
        meta_a = DocumentMetadata(
            tags=["#adr", "#alpha"], date="2026-03-23", related=[]
        )
        meta_b = DocumentMetadata(tags=["#adr", "#beta"], date="2026-03-23", related=[])
        snapshot: VaultSnapshot = {
            path_a: (meta_a, "Body with [[link-a]]."),
            path_b: (meta_b, "Body with [[link-b]]."),
        }
        result = check_body_links(root, snapshot=snapshot, feature="alpha")
        assert result.error_count == 1
        assert "link-a" in result.diagnostics[0].message

    def test_multiple_links_in_one_document(self):
        body = (
            "First [[wiki-a]] then [[wiki-b]] and "
            "[a file](path/to/file.rs) plus [another](lib/mod.py)."
        )
        root, snapshot = _snap("multi", body)
        result = check_body_links(root, snapshot=snapshot)
        assert result.error_count == 4

    def test_clean_body_returns_clean_result(self):
        root, snapshot = _snap("clean", "Plain text with `code spans`.")
        result = check_body_links(root, snapshot=snapshot)
        assert result.is_clean

    def test_ignores_links_in_fenced_code_blocks(self):
        body = (
            "Some text.\n\n"
            "```toml\n"
            "[[tool.uv.index]]\n"
            'name = "testpypi"\n'
            "```\n\n"
            "More text."
        )
        root, snapshot = _snap("fenced", body)
        result = check_body_links(root, snapshot=snapshot)
        assert result.is_clean

    def test_ignores_links_in_inline_code(self):
        body = "Reference `[[some-doc]]` in inline code."
        root, snapshot = _snap("inline", body)
        result = check_body_links(root, snapshot=snapshot)
        assert result.is_clean

    def test_ignores_links_in_html_comments(self):
        body = (
            "<!-- LINK RULES:\n"
            "     - [[wiki-links]] are ONLY for .vault/ documents.\n"
            "     - NEVER use [[wiki-links]] in the document body. -->\n\n"
            "Clean body text."
        )
        root, snapshot = _snap("comment", body)
        result = check_body_links(root, snapshot=snapshot)
        assert result.is_clean

    def test_does_not_support_fix(self):
        root, snapshot = _snap("nope", "Body text.")
        result = check_body_links(root, snapshot=snapshot)
        assert not result.supports_fix
