"""Tests for the feature index generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from ...config import reset_config
from ..index import generate_feature_index

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


@dataclass
class FakeDocType:
    """Minimal stand-in for DocType enum."""

    value: str


@dataclass
class FakeDocNode:
    """Minimal stand-in for DocNode."""

    path: Path | None
    name: str
    doc_type: Any = None
    feature: str | None = None
    date: str | None = None
    title: str | None = None
    tags: set[str] = field(default_factory=set)
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    word_count: int = 0
    out_links: set[str] = field(default_factory=set)
    in_links: set[str] = field(default_factory=set)
    phantom: bool = False


def _node(
    root: Path,
    name: str,
    dtype: str,
    feat: str,
    date: str,
    title: str,
) -> FakeDocNode:
    return FakeDocNode(
        path=root / ".vault" / dtype / f"{name}.md",
        name=name,
        doc_type=FakeDocType(dtype),
        feature=feat,
        date=date,
        title=title,
        tags={f"#{dtype}", f"#{feat}"},
    )


def _gen(tmp_path, feat, nodes):
    return generate_feature_index(tmp_path, feat, nodes=nodes, date_str="2026-03-23")


class TestGenerateFeatureIndex:
    def test_creates_index_file(self, tmp_path):
        nodes = [
            _node(tmp_path, "d1", "research", "f", "2026-03-01", "R"),
            _node(tmp_path, "d2", "adr", "f", "2026-03-02", "A"),
        ]
        path = _gen(tmp_path, "f", nodes)
        assert path.exists()
        assert path.name == "f.index.md"

    def test_index_has_correct_frontmatter(self, tmp_path):
        nodes = [
            _node(tmp_path, "d1", "research", "f", "2026-03-01", "R"),
        ]
        path = _gen(tmp_path, "f", nodes)
        content = path.read_text(encoding="utf-8")
        assert "generated: true" in content
        assert "'#f'" in content
        assert "2026-03-23" in content

    def test_index_has_single_feature_tag(self, tmp_path):
        nodes = [
            _node(tmp_path, "x", "adr", "my-feat", "2026-03-01", "X"),
        ]
        path = _gen(tmp_path, "my-feat", nodes)
        content = path.read_text(encoding="utf-8")
        assert content.count("  - '#") == 1
        assert "'#my-feat'" in content
        assert "'#adr'" not in content

    def test_related_contains_all_feature_docs(self, tmp_path):
        nodes = [
            _node(tmp_path, "a", "research", "f", "2026-03-01", "A"),
            _node(tmp_path, "b", "adr", "f", "2026-03-02", "B"),
            _node(tmp_path, "c", "plan", "f", "2026-03-03", "C"),
        ]
        path = _gen(tmp_path, "f", nodes)
        content = path.read_text(encoding="utf-8")
        assert "[[a]]" in content
        assert "[[b]]" in content
        assert "[[c]]" in content

    def test_body_groups_by_type(self, tmp_path):
        nodes = [
            _node(tmp_path, "a", "research", "f", "2026-03-01", "RA"),
            _node(tmp_path, "b", "adr", "f", "2026-03-02", "AB"),
        ]
        path = _gen(tmp_path, "f", nodes)
        content = path.read_text(encoding="utf-8")
        assert "### adr" in content
        assert "### research" in content
        assert "`a`" in content
        assert "`b`" in content

    def test_idempotent_update(self, tmp_path):
        nodes = [
            _node(tmp_path, "a", "research", "f", "2026-03-01", "A"),
        ]
        p1 = _gen(tmp_path, "f", nodes)
        c1 = p1.read_text(encoding="utf-8")

        p2 = _gen(tmp_path, "f", nodes)
        c2 = p2.read_text(encoding="utf-8")

        assert p1 == p2
        assert c1 == c2

    def test_update_reflects_new_docs(self, tmp_path):
        v1 = [_node(tmp_path, "a", "research", "f", "2026-03-01", "A")]
        _gen(tmp_path, "f", v1)

        v2 = [
            *v1,
            _node(tmp_path, "b", "adr", "f", "2026-03-02", "B"),
        ]
        path = _gen(tmp_path, "f", v2)
        content = path.read_text(encoding="utf-8")
        assert "[[b]]" in content
        assert "### adr" in content

    def test_excludes_self_from_related(self, tmp_path):
        nodes = [
            _node(tmp_path, "a", "research", "f", "2026-03-01", "A"),
            FakeDocNode(
                path=tmp_path / ".vault" / "f.index.md",
                name="f.index",
                feature="f",
            ),
        ]
        path = _gen(tmp_path, "f", nodes)
        content = path.read_text(encoding="utf-8")
        assert "[[f.index]]" not in content
        assert "[[a]]" in content
