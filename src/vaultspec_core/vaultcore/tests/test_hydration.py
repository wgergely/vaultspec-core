"""Tests for vault document template hydration."""

import logging

import pytest

from vaultspec_core.vaultcore import hydrate_template
from vaultspec_core.vaultcore.hydration import create_vault_doc
from vaultspec_core.vaultcore.models import DocType

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


class TestCreateVaultDocStemCollision:
    """Ensure vault add rejects files whose stem collides with an existing doc."""

    @pytest.fixture()
    def vault_project(self, tmp_path):
        """Scaffold a minimal vault with one existing doc and real templates.

        Uses seed_builtins to copy real templates - never shadows them.
        """
        from vaultspec_core.builtins import seed_builtins

        rules_dir = tmp_path / ".vaultspec" / "rules"
        rules_dir.mkdir(parents=True)
        seed_builtins(rules_dir, force=True)

        # Create vault type directories
        for dt in DocType:
            (tmp_path / ".vault" / dt.value).mkdir(parents=True, exist_ok=True)

        # Create an existing vault document with a known stem
        (tmp_path / ".vault" / "adr" / "2026-03-17-my-feat-adr.md").write_text(
            "---\ntags:\n  - '#adr'\n  - '#my-feat'\n"
            "date: '2026-03-17'\nrelated: []\n---\n# Existing\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_exact_path_collision_rejected(self, vault_project):
        """Re-creating the same file raises FileExistsError."""
        with pytest.raises(FileExistsError, match="already exists"):
            create_vault_doc(
                vault_project,
                DocType.ADR,
                "my-feat",
                "2026-03-17",
                title="Duplicate",
            )

    def test_cross_type_stem_collision_rejected(self, vault_project):
        """A different type dir but same stem is rejected."""
        # Manually place a file in research/ with the same stem as
        # the ADR we're about to create
        research_dir = vault_project / ".vault" / "research"
        research_dir.mkdir(parents=True, exist_ok=True)
        (research_dir / "2026-03-18-new-feat-research.md").write_text(
            "---\ntags: ['#research', '#new-feat']\n---\n",
            encoding="utf-8",
        )

        # Place a file with stem "2026-03-20-collide-adr" in research/
        (research_dir / "2026-03-20-collide-adr.md").write_text(
            "---\ntags: ['#research']\n---\n",
            encoding="utf-8",
        )

        # Now create an ADR that generates stem "2026-03-20-collide-adr"
        with pytest.raises(FileExistsError, match=r"stem.*already exists"):
            create_vault_doc(
                vault_project,
                DocType.ADR,
                "collide",
                "2026-03-20",
                title="Collision",
            )

    def test_unique_stem_succeeds(self, vault_project):
        """A truly unique stem creates the file without error."""
        path = create_vault_doc(
            vault_project,
            DocType.ADR,
            "unique-feat",
            "2026-03-20",
            title="Unique",
        )
        assert path.exists()
        assert path.stem == "2026-03-20-unique-feat-adr"
