from vault.models import DocType, DocumentMetadata, VaultConstants
from vault.parser import parse_vault_metadata


def test_doctype_enum():
    assert DocType.ADR == "adr"
    assert DocType.ADR.tag == "#adr"
    assert DocType.from_tag("#plan") == DocType.PLAN
    assert DocType.from_tag("#invalid") is None


def test_document_metadata_validation_success():
    meta = DocumentMetadata(
        tags=["#adr", "#editor-demo"],
        date="2026-02-08",
        related=["[[2026-02-07-research]]"],
    )
    errors = meta.validate()
    assert len(errors) == 0


def test_document_metadata_validation_fail_tags():
    # Only one tag
    meta = DocumentMetadata(tags=["#adr"], date="2026-02-08")
    errors = meta.validate()
    assert any("Exactly 2 tags required" in e for e in errors)

    # Two directory tags
    meta = DocumentMetadata(tags=["#adr", "#plan"], date="2026-02-08")
    errors = meta.validate()
    assert any("Exactly one feature tag" in e for e in errors)

    # Invalid feature tag format
    meta = DocumentMetadata(tags=["#adr", "#EditorDemo"], date="2026-02-08")
    errors = meta.validate()
    assert any("Invalid feature tag format" in e for e in errors)


def test_document_metadata_validation_fail_date():
    meta = DocumentMetadata(tags=["#adr", "#feat"], date="2026/02/08")
    errors = meta.validate()
    assert any("Invalid date format" in e for e in errors)


def test_vault_constants_validate_filename():
    assert (
        len(VaultConstants.validate_filename("2026-02-08-feature-adr.md", DocType.ADR))
        == 0
    )
    assert len(VaultConstants.validate_filename("invalid.md", DocType.ADR)) > 0
    # Mismatch type
    assert (
        len(VaultConstants.validate_filename("2026-02-08-feature-plan.md", DocType.ADR))
        > 0
    )


def test_parse_vault_metadata():
    content = """---
tags:
  - "#adr"
  - "#editor-demo"
date: 2026-02-08
related:
  - "[[ref1]]"
  - "[[ref2]]"
---
# Content
"""
    meta, _body = parse_vault_metadata(content)
    assert meta.tags == ["#adr", "#editor-demo"]
    assert meta.date == "2026-02-08"
    assert meta.related == ["[[ref1]]", "[[ref2]]"]
    assert "# Content" in _body


def test_parse_vault_metadata_inline_list():
    content = """---
tags: ["#plan", "#feat"]
date: "2026-02-08"
---
"""
    meta, _body = parse_vault_metadata(content)
    assert meta.tags == ["#plan", "#feat"]
    assert meta.date == "2026-02-08"
