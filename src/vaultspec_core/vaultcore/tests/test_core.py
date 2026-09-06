"""Tests for low-level frontmatter parsing.

Targets :func:`~vaultspec_core.vaultcore.parser.parse_frontmatter`.

Covers fallback semantics (PyYAML → simple parser), value normalization,
colon-in-value handling, quoted strings, whitespace trimming, and body
preservation.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
import yaml
from yaml.constructor import SafeConstructor

if TYPE_CHECKING:
    from pathlib import Path

from ...protocol.providers import GeminiModels
from .. import parse_frontmatter, parse_vault_metadata
from ..parser import SafeLoader

pytestmark = [pytest.mark.unit]

# A UTF-8 byte-order mark (U+FEFF). A file authored with a BOM reads via
# ``read_text(encoding="utf-8")`` as this character followed by its content.
_BOM = "\ufeff"


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


class TestParseFrontmatterBOM:
    """A leading UTF-8 BOM must not hide the frontmatter fence.

    ``str.lstrip`` does not strip U+FEFF, so without the explicit BOM strip in
    the parser a BOM-prefixed document parses as having no frontmatter and is
    silently invisible to every feature scan and check.
    """

    def test_bom_frontmatter_parsed_identically_to_plain(self):
        plain = (
            "---\ntags:\n  - '#research'\n  - '#bom-feature'\n"
            "date: '2026-06-26'\n---\n\n# Body\nProse.\n"
        )
        meta_plain, body_plain = parse_frontmatter(plain)
        meta_bom, body_bom = parse_frontmatter(_BOM + plain)

        assert meta_bom == meta_plain
        assert meta_bom["tags"] == ["#research", "#bom-feature"]
        assert body_bom == body_plain

    def test_bom_followed_by_leading_whitespace(self):
        # The BOM is stripped first, then the existing lstrip handles any
        # additional leading whitespace before the fence.
        content = _BOM + "\n  ---\ntier: LOW\n---\nBody."
        meta, body = parse_frontmatter(content)
        assert meta["tier"] == "LOW"
        assert "Body." in body


class TestParseVaultMetadataBOM:
    """The rigid vault-metadata scanner must also see through a leading BOM."""

    def test_bom_metadata_parsed_identically_to_plain(self):
        plain = (
            "---\ntags:\n  - '#research'\n  - '#bom-feature'\n"
            "date: '2026-06-26'\nmodified: '2026-06-26'\n"
            "related:\n  - '[[other-doc]]'\n---\n\n# Body\nProse.\n"
        )
        meta_plain, body_plain = parse_vault_metadata(plain)
        meta_bom, body_bom = parse_vault_metadata(_BOM + plain)

        assert meta_bom.tags == meta_plain.tags == ["#research", "#bom-feature"]
        assert meta_bom.date == meta_plain.date == "2026-06-26"
        assert meta_bom.related == meta_plain.related == ["[[other-doc]]"]
        assert body_bom == body_plain


class TestParseVaultMetadataStepId:
    """``parse_vault_metadata`` surfaces the exec-record ``step_id`` stamp."""

    def test_step_id_parsed_from_exec_frontmatter(self):
        content = (
            "---\ntags:\n  - '#exec'\n  - '#editor-demo'\n"
            "date: '2026-02-04'\nmodified: '2026-02-04'\n"
            "step_id: 'S03'\nrelated:\n  - '[[2026-02-04-editor-demo-plan]]'\n"
            "---\n\n# Body\nProse.\n"
        )
        meta, _body = parse_vault_metadata(content)
        assert meta.step_id == "S03"

    def test_step_id_none_when_absent(self):
        content = (
            "---\ntags:\n  - '#adr'\n  - '#editor-demo'\n"
            "date: '2026-02-04'\nmodified: '2026-02-04'\n"
            "related: []\n---\n\n# Body\nProse.\n"
        )
        meta, _body = parse_vault_metadata(content)
        assert meta.step_id is None

    def test_step_id_none_when_empty_value(self):
        content = (
            "---\ntags:\n  - '#exec'\n  - '#editor-demo'\n"
            "date: '2026-02-04'\nstep_id: ''\nrelated: []\n---\n\n# Body\n"
        )
        meta, _body = parse_vault_metadata(content)
        assert meta.step_id is None


class TestFrontmatterLoaderSafety:
    """Frontmatter must never instantiate arbitrary objects.

    ``.vault/`` documents are ordinary files on disk, so their frontmatter is
    attacker-reachable whenever a vault is shared, cloned, or generated. The
    loader therefore has to refuse the ``!!python/...`` tag family outright
    rather than trusting the document.
    """

    def test_active_loader_uses_the_safe_constructor(self):
        # CSafeLoader and SafeLoader do not share a loader base class, but both
        # derive from SafeConstructor - the component that actually refuses
        # arbitrary tags - so this holds whichever branch libyaml selected.
        assert issubclass(SafeLoader, SafeConstructor)

    def test_object_tag_is_not_instantiated(self, tmp_path: Path) -> None:
        document = (
            "---\n"
            "tags:\n"
            "  - '#adr'\n"
            "  - '#editor-demo'\n"
            "payload: !!python/object/apply:datetime.date [2026, 7, 28]\n"
            "---\n"
            "\n"
            "# Body\n"
            "Prose.\n"
        )
        path = tmp_path / "2026-07-28-editor-demo-adr.md"
        path.write_text(document, encoding="utf-8")

        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))

        # The tag is refused, so the value survives only as inert text.
        assert not isinstance(meta["payload"], datetime.date)
        assert meta["payload"] == "!!python/object/apply:datetime.date [2026, 7, 28]"
        assert "# Body" in body

    def test_object_tag_does_not_invoke_the_named_callable(
        self, tmp_path: Path
    ) -> None:
        # ``apply`` tags call the named object, which is the arbitrary-execution
        # vector proper - not merely arbitrary construction.
        document = (
            "---\n"
            'evaluated: !!python/object/apply:builtins.eval ["38 + 4"]\n'
            "---\n"
            "Body.\n"
        )
        path = tmp_path / "2026-07-28-editor-demo-research.md"
        path.write_text(document, encoding="utf-8")

        meta, _body = parse_frontmatter(path.read_text(encoding="utf-8"))

        assert meta["evaluated"] != 42
        assert meta["evaluated"] == '!!python/object/apply:builtins.eval ["38 + 4"]'

    def test_unsafe_loader_would_have_honored_the_tags(self):
        # Guards the two tests above against becoming tautologies: it pins the
        # payloads as genuinely dangerous, so those assertions are proving the
        # loader choice rather than an inert fixture.
        constructed = yaml.load(
            "payload: !!python/object/apply:datetime.date [2026, 7, 28]\n",
            Loader=yaml.UnsafeLoader,
        )
        assert constructed["payload"] == datetime.date(2026, 7, 28)

        evaluated = yaml.load(
            'evaluated: !!python/object/apply:builtins.eval ["38 + 4"]\n',
            Loader=yaml.UnsafeLoader,
        )
        assert evaluated["evaluated"] == 42

    def test_safe_loader_rejects_the_tag_rather_than_ignoring_it(self):
        # The rejection must come from the loader itself; parse_frontmatter only
        # degrades to the simple splitter because this raises.
        with pytest.raises(yaml.YAMLError):
            yaml.load(
                "payload: !!python/object/apply:datetime.date [2026, 7, 28]\n",
                Loader=SafeLoader,
            )


class TestFrontmatterRoundTrip:
    """The shapes the vault schema actually emits must survive a real read."""

    def test_canonical_vault_frontmatter_round_trips_from_disk(
        self, tmp_path: Path
    ) -> None:
        document = (
            "---\n"
            "tags:\n"
            "  - '#exec'\n"
            "  - '#editor-demo'\n"
            "date: '2026-07-28'\n"
            "modified: '2026-07-28'\n"
            "step_id: 'S07'\n"
            "body_schema: 'exec-step'\n"
            "related:\n"
            "  - '[[2026-07-28-editor-demo-plan]]'\n"
            "  - '[[2026-07-28-editor-demo-adr]]'\n"
            "---\n"
            "\n"
            "# Body\n"
            "Prose with a colon: and trailing text.\n"
        )
        path = tmp_path / "2026-07-28-editor-demo-P01-S07.md"
        path.write_text(document, encoding="utf-8")
        content = path.read_text(encoding="utf-8")

        meta, body = parse_frontmatter(content)
        assert meta["tags"] == ["#exec", "#editor-demo"]
        assert meta["date"] == "2026-07-28"
        assert meta["modified"] == "2026-07-28"
        assert meta["step_id"] == "S07"
        assert meta["body_schema"] == "exec-step"
        assert meta["related"] == [
            "[[2026-07-28-editor-demo-plan]]",
            "[[2026-07-28-editor-demo-adr]]",
        ]
        # The closing fence is matched as ``---\s*\n?``, so the blank line that
        # separates fence from prose is consumed with it and the body opens on
        # the first real line.
        assert body == "# Body\nProse with a colon: and trailing text.\n"

        vault_meta, vault_body = parse_vault_metadata(content)
        assert vault_meta.tags == ["#exec", "#editor-demo"]
        assert vault_meta.date == "2026-07-28"
        assert vault_meta.modified == "2026-07-28"
        assert vault_meta.step_id == "S07"
        assert vault_meta.body_schema == "exec-step"
        assert vault_meta.related == [
            "[[2026-07-28-editor-demo-plan]]",
            "[[2026-07-28-editor-demo-adr]]",
        ]
        assert vault_body == body

    def test_inline_list_frontmatter_round_trips_from_disk(
        self, tmp_path: Path
    ) -> None:
        document = (
            "---\n"
            "tags: ['#plan', '#editor-demo']\n"
            "date: '2026-07-28'\n"
            "related: []\n"
            "---\n"
            "Body.\n"
        )
        path = tmp_path / "2026-07-28-editor-demo-plan.md"
        path.write_text(document, encoding="utf-8")
        content = path.read_text(encoding="utf-8")

        meta, _body = parse_frontmatter(content)
        assert meta["tags"] == ["#plan", "#editor-demo"]
        assert meta["related"] == []

        vault_meta, _vault_body = parse_vault_metadata(content)
        assert vault_meta.tags == ["#plan", "#editor-demo"]
        assert vault_meta.related == []


class TestParseFrontmatterNonMapping:
    """YAML documents are not necessarily mappings; ``parse_frontmatter``
    must never hand a caller anything but a ``dict``.

    Every consumer of ``parse_frontmatter`` (roughly a dozen call sites,
    including graph construction) calls ``.get()`` on the returned value
    without checking its type first, so a sequence or scalar frontmatter
    block has to degrade to empty metadata at this boundary rather than
    surface as an ``AttributeError`` deep inside a caller.
    """

    def test_sequence_frontmatter_degrades_to_empty_dict(self):
        content = "---\n- a\n- b\n---\n\nBody.\n"
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert "Body." in body

    def test_scalar_frontmatter_degrades_to_empty_dict(self):
        content = "---\njust a bare scalar\n---\n\nBody.\n"
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert "Body." in body

    def test_result_always_supports_get(self):
        # The actual contract under test: whatever parse_frontmatter returns,
        # a consumer calling .get("related", []) the way graph/api.py does
        # must not raise.
        for content in (
            "---\n- a\n- b\n---\nBody.\n",
            "---\njust a bare scalar\n---\nBody.\n",
            "---\ntags: ['#a']\n---\nBody.\n",
        ):
            meta, _body = parse_frontmatter(content)
            meta.get("related", [])  # must not raise AttributeError
