"""Tests for low-level frontmatter parsing.

Targets :func:`~vaultspec_core.vaultcore.parser.parse_frontmatter`.

Covers fallback semantics (PyYAML → simple parser), value normalization,
colon-in-value handling, quoted strings, whitespace trimming, and body
preservation.
"""

from __future__ import annotations

import pytest

from ...protocol.providers import GeminiModels
from .. import parse_frontmatter

pytestmark = [pytest.mark.unit]


class TestParseFrontmatter:
    def test_valid_frontmatter(self):
        content = (
            f"---\ntier: LOW\nmodel: {GeminiModels.LOW}\n"
            "---\n\n# Persona\nBody text here."
        )
        meta, body = parse_frontmatter(content)
        assert meta["tier"] == "LOW"
        assert meta["model"] == GeminiModels.LOW
        assert "# Persona" in body

    def test_no_frontmatter(self):
        content = "Just plain body text without frontmatter."
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_empty_frontmatter(self):
        content = "---\n\n---\nBody after empty frontmatter."
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert "Body after empty frontmatter." in body

    def test_colon_in_value(self):
        content = "---\ndescription: A test: with colons: everywhere\n---\nBody."
        meta, _body = parse_frontmatter(content)
        assert meta["description"] == "A test: with colons: everywhere"

    def test_quoted_description(self):
        content = (
            "---\n"
            'description: "A quoted description with special chars"\n'
            "tier: HIGH\n"
            "---\n"
            "Body."
        )
        meta, _body = parse_frontmatter(content)
        # PyYAML strips quotes (correct YAML behavior); simple parser preserves them.
        assert meta["description"] in (
            "A quoted description with special chars",
            '"A quoted description with special chars"',
        )
        assert meta["tier"] == "HIGH"

    def test_whitespace_handling(self):
        content = "---\n  key  :  value with spaces  \n---\nBody."
        meta, _body = parse_frontmatter(content)
        assert meta["key"] == "value with spaces"

    def test_body_preserved(self):
        content = "---\ntier: LOW\n---\nLine 1\nLine 2\nLine 3"
        _meta, body = parse_frontmatter(content)
        assert body == "Line 1\nLine 2\nLine 3"
