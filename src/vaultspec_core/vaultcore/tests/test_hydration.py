"""Tests for vault document template hydration."""

import logging

import pytest

from vaultspec_core.vaultcore import hydrate_template

pytestmark = [pytest.mark.unit]


def test_hydrate_template_basic():
    """Verify that placeholders in a template are correctly replaced."""
    template = """---
tags: ["#adr", "#{feature}"]
date: {yyyy-mm-dd}
---

# {title}
"""
    result = hydrate_template(template, "my-feature", "2026-03-01", title="My Title")

    assert 'tags: ["#adr", "#my-feature"]' in result
    assert "date: 2026-03-01" in result
    assert "# My Title" in result


def test_hydrate_template_placeholders():
    """Verify supported placeholders and the topic alias are hydrated."""
    template = "{feature} {yyyy-mm-dd} {title} {topic}"
    result = hydrate_template(template, "feat", "2026-02-01", title="Plan Title")
    assert result == "feat 2026-02-01 Plan Title Plan Title"


def test_hydrate_template_leaves_missing_title_and_warns(caplog):
    """Verify unresolved placeholders remain when optional title is omitted."""
    template = "{feature} {title}"
    with caplog.at_level(logging.WARNING):
        result = hydrate_template(template, "adr", "2026-03-01")

    assert result == "adr {title}"
    assert "Potential unhydrated placeholder found in template: {title}" in caplog.text
