"""Synthetic vault corpus generator for deterministic testing.

Generates ``.vault/`` directories with predictable content, unique needle
keywords per document, and configurable graph density.  Each document is
parseable by ``vaultspec_core.vaultcore.parse_vault_metadata`` and
``prepare_document``.

The ``graph_density`` parameter defaults to ``0.3`` (non-zero). Tests that
assert on graph connectivity (e.g. ``number_of_edges() > 0``) rely on this
default; callers that need a fully disconnected corpus must pass
``graph_density=0.0`` explicitly.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "PATHOLOGY_NAMES",
    "CorpusManifest",
    "GeneratedDoc",
    "build_multi_project_fixture",
    "build_synthetic_vault",
]

DOC_TYPES: list[str] = ["adr", "plan", "research", "exec", "reference", "audit"]
FEATURES: list[str] = ["alpha-engine", "beta-pipeline", "gamma-index", "delta-store"]

# Mapping from stem suffix to doc type for named_docs inference.
_SUFFIX_TO_TYPE: dict[str, str] = {
    "-adr": "adr",
    "-plan": "plan",
    "-research": "research",
    "-reference": "reference",
    "-audit": "audit",
    "-exec": "exec",
    "-summary": "exec",
}

# Topical paragraphs keyed by doc_type - each doc gets its type paragraph
# plus its needle keyword for deterministic retrieval.
_TYPE_PARAGRAPHS: dict[str, str] = {
    "adr": (
        "This architecture decision record evaluates trade-offs between "
        "competing approaches. The decision balances performance, "
        "maintainability, and operational complexity."
    ),
    "plan": (
        "This implementation plan outlines phases, milestones, and "
        "deliverables. Each phase has clear entry and exit criteria "
        "with defined verification steps."
    ),
    "research": (
        "This research document investigates technical options through "
        "literature review, benchmarking, and prototype evaluation. "
        "Findings inform downstream architectural decisions."
    ),
    "exec": (
        "This execution record documents completed implementation work "
        "including code changes, test results, and deployment notes. "
        "It traces back to the originating plan."
    ),
    "reference": (
        "This reference document captures API contracts, data schemas, "
        "and integration patterns. It serves as the authoritative "
        "specification for implementors."
    ),
    "audit": (
        "This audit report assesses code quality, security posture, "
        "and compliance status. Findings are categorized by severity "
        "with recommended remediation steps."
    ),
}


@dataclass
class GeneratedDoc:
    """A single generated vault document.

    Attributes:
        doc_id: Relative path without extension (e.g. ``"adr/test-001"``).
        doc_type: One of the 6 vault doc types.
        feature: Feature tag (without ``#``).
        needle: Unique keyword embedded in the document body.
        path: Absolute path to the written ``.md`` file.
        related_ids: List of doc_ids this document links to.
        date: ISO date string for the document.
    """

    doc_id: str
    doc_type: str
    feature: str
    needle: str
    date: str
    path: Path
    related_ids: list[str] = field(default_factory=list)


@dataclass
class CorpusManifest:
    """Result of a synthetic vault generation.

    Attributes:
        root: Project root directory containing ``.vault/``.
        docs: All generated documents.
        needles: Mapping from needle keyword to doc_id.
        graph_edges: Directed edges ``(from_id, to_id)`` in the
            related-links graph.
        pathologies: Mapping from pathology name to list of affected
            ``GeneratedDoc`` instances.
        pathology_details: Mapping from pathology name to a list of
            detail dicts with pathology-specific assertion data.
        named_docs: Mapping from logical key to ``GeneratedDoc`` for
            docs requested via the ``named_docs`` parameter.
    """

    root: Path
    docs: list[GeneratedDoc]
    needles: dict[str, str]
    graph_edges: list[tuple[str, str]]
    pathologies: dict[str, list[GeneratedDoc]] = field(default_factory=dict)
    pathology_details: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    named_docs: dict[str, GeneratedDoc] = field(default_factory=dict)


def _needle_for(doc_type: str, index: int) -> str:
    """Generate a unique needle keyword for a document."""
    return f"NEEDLE_{doc_type.upper()}_{index:03d}"


def _make_frontmatter(
    doc_type: str,
    feature: str,
    date: str,
    related: list[str],
) -> str:
    """Render YAML frontmatter for a vault document.

    Produces exactly two tags (one directory tag + one feature tag), an ISO
    ``date``, and ``related:`` as a list of quoted wiki-links.
    """
    tags_str = f'  - "#{doc_type}"\n  - "#{feature}"'
    if related:
        lines = [f'  - "[[{r}]]"' for r in related]
        related_block = "related:\n" + "\n".join(lines)
    else:
        related_block = "related: []"

    return f"---\ntags:\n{tags_str}\ndate: {date}\n{related_block}\n---\n"


def _make_body(
    doc_type: str,
    feature: str,
    needle: str,
    index: int,
) -> str:
    """Render the markdown body with type-specific content and needle."""
    title = f"# {feature} {doc_type} {index:03d}"
    paragraph = _TYPE_PARAGRAPHS[doc_type]
    needle_line = (
        f"This document contains the unique identifier {needle} which "
        f"can be used for precision retrieval testing."
    )
    return f"{title}\n\n{paragraph}\n\n{needle_line}\n"


def _infer_doc_type(stem: str) -> str:
    """Infer doc type from stem suffix for named_docs.

    Args:
        stem: Filename stem (without ``.md``).

    Returns:
        Inferred doc type string.

    Raises:
        ValueError: If the suffix is unrecognised.
    """
    for suffix, dt in _SUFFIX_TO_TYPE.items():
        if stem.endswith(suffix):
            return dt
    raise ValueError(
        f"Cannot infer doc type from stem {stem!r}. "
        f"Stem must end with one of: {list(_SUFFIX_TO_TYPE)}"
    )


# ---------------------------------------------------------------------------
# Pathology helpers
# ---------------------------------------------------------------------------


def _apply_dangling(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Inject a nonexistent wiki-link target into selected docs.

    The broken target stem is recorded in ``pathology_details["dangling"]``
    alongside the source doc path so tests can assert on the specific broken
    entry without hardcoding names.

    Produces the ``exec/<feature>/<feature>-phase1-summary.md`` subdirectory
    shape required by the ``check_dangling`` fix path.
    """
    affected: list[GeneratedDoc] = []
    details: list[dict[str, Any]] = []

    # Pick one exec-type doc to inject dangling link into; prefer exec subdir.
    exec_docs = [d for d in docs if d.doc_type == "exec"]
    targets = exec_docs[:1] if exec_docs else docs[:1]

    for doc in targets:
        broken_stem = "nonexistent-dangling-target-xyzzy"
        # Rewrite the file with the extra dangling link.
        text = doc.path.read_text(encoding="utf-8")
        # Insert the broken wiki-link into related: - replace the closing ---
        # by adding a new related entry before it.
        if "related: []" in text:
            text = text.replace(
                "related: []",
                f'related:\n  - "[[{broken_stem}]]"',
            )
        else:
            # Append to existing related list
            text = text.replace(
                "\n---\n",
                f'\n  - "[[{broken_stem}]]"\n---\n',
                1,
            )
        doc.path.write_text(text, encoding="utf-8")

        affected.append(doc)
        details.append({"target_stem": broken_stem, "source_path": doc.path})

    # Also create a summary file in exec/<feature>/ subdirectory shape
    # that check_dangling's fix path can locate.
    if exec_docs:
        feature = exec_docs[0].feature
        exec_subdir = vault_dir / "exec" / feature
        exec_subdir.mkdir(parents=True, exist_ok=True)
        summary_stem = f"2026-01-01-{feature}-phase1-summary"
        summary_path = exec_subdir / f"{summary_stem}.md"
        broken_stem2 = "nonexistent-summary-target-xyzzy"
        fm = _make_frontmatter("exec", feature, "2026-01-01", [broken_stem2])
        body = f"# {feature} phase1 summary\n\nThis is a generated summary.\n"
        summary_path.write_text(fm + "\n" + body, encoding="utf-8")
        summary_doc = GeneratedDoc(
            doc_id=f"exec/{feature}/{summary_stem}",
            doc_type="exec",
            feature=feature,
            needle="NEEDLE_DANGLING_SUMMARY",
            date="2026-01-01",
            path=summary_path,
            related_ids=[f"exec/{broken_stem2}"],
        )
        affected.append(summary_doc)
        details.append({"target_stem": broken_stem2, "source_path": summary_path})
        docs.append(summary_doc)

    manifest.pathologies["dangling"] = affected
    manifest.pathology_details["dangling"] = details


def _apply_orphan(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Generate an isolated document with no inbound or outbound links."""
    stem = "2026-01-01-orphan-isolated-doc"
    doc_type = "research"
    feature = "orphan-feature"
    path = vault_dir / doc_type / f"{stem}.md"
    fm = _make_frontmatter(doc_type, feature, "2026-01-01", [])
    body = "# orphan isolated doc\n\nThis document has no links.\n"
    path.write_text(fm + "\n" + body, encoding="utf-8")
    doc = GeneratedDoc(
        doc_id=f"{doc_type}/{stem}",
        doc_type=doc_type,
        feature=feature,
        needle="NEEDLE_ORPHAN_001",
        date="2026-01-01",
        path=path,
    )
    docs.append(doc)
    manifest.pathologies["orphan"] = [doc]
    manifest.pathology_details["orphan"] = [{"stem": stem}]


def _apply_missing_frontmatter(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Emit a doc with no YAML frontmatter block at all."""
    stem = "2026-01-01-missing-frontmatter-doc"
    path = vault_dir / "adr" / f"{stem}.md"
    path.write_text(
        "# Missing Frontmatter\n\nThis document has no YAML frontmatter block.\n",
        encoding="utf-8",
    )
    doc = GeneratedDoc(
        doc_id=f"adr/{stem}",
        doc_type="adr",
        feature="",
        needle="NEEDLE_MISSING_FM",
        date="",
        path=path,
    )
    docs.append(doc)
    manifest.pathologies["missing_frontmatter"] = [doc]
    manifest.pathology_details["missing_frontmatter"] = [{"stem": stem}]


def _apply_wrong_directory_tag(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Place a doc in .vault/adr/ tagged #plan (wrong directory tag)."""
    stem = "2026-01-01-wrong-dir-tag-doc"
    path = vault_dir / "adr" / f"{stem}.md"
    # Tag says #plan but file is in adr/ directory.
    fm = (
        '---\ntags:\n  - "#plan"\n  - "#wrong-dir-feature"\n'
        "date: 2026-01-01\nrelated:\n  []\n---\n"
    )
    body = "# wrong directory tag\n\nThis document has a mismatched directory tag.\n"
    path.write_text(fm + "\n" + body, encoding="utf-8")
    doc = GeneratedDoc(
        doc_id=f"adr/{stem}",
        doc_type="plan",  # wrong - it's in adr/
        feature="wrong-dir-feature",
        needle="NEEDLE_WRONG_DIR_TAG",
        date="2026-01-01",
        path=path,
    )
    docs.append(doc)
    manifest.pathologies["wrong_directory_tag"] = [doc]
    manifest.pathology_details["wrong_directory_tag"] = [
        {"stem": stem, "directory": "adr", "tag": "plan"}
    ]


def _apply_stale_index(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Emit a feature.index.md whose related count disagrees with actual files."""
    feature = "stale-feature"
    stem = f"{feature}.index"
    path = vault_dir / "plan" / f"{stem}.md"
    # Claim 99 related entries but write only 1
    fm = (
        '---\ntags:\n  - "#plan"\n  - "#stale-feature"\n'
        'date: 2026-01-01\nrelated:\n  - "[[nonexistent-plan-001]]"\n---\n'
    )
    body = "# stale-feature index\n\nThis index has a stale count.\n"
    path.write_text(fm + "\n" + body, encoding="utf-8")
    doc = GeneratedDoc(
        doc_id=f"plan/{stem}",
        doc_type="plan",
        feature=feature,
        needle="NEEDLE_STALE_INDEX",
        date="2026-01-01",
        path=path,
    )
    docs.append(doc)
    manifest.pathologies["stale_index"] = [doc]
    manifest.pathology_details["stale_index"] = [
        {"stem": stem, "claimed_count": 99, "actual_count": 1}
    ]


def _apply_cycle(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Introduce a wiki-link cycle A -> B -> C -> A."""
    feature = "cycle-feature"
    cycle_stems = [
        "2026-01-01-cycle-doc-alpha",
        "2026-01-01-cycle-doc-beta",
        "2026-01-01-cycle-doc-gamma",
    ]
    cycle_docs: list[GeneratedDoc] = []

    for i, stem in enumerate(cycle_stems):
        next_stem = cycle_stems[(i + 1) % len(cycle_stems)]
        path = vault_dir / "research" / f"{stem}.md"
        fm = _make_frontmatter("research", feature, "2026-01-01", [next_stem])
        body = f"# cycle doc {i}\n\nPart of a wiki-link cycle.\n"
        path.write_text(fm + "\n" + body, encoding="utf-8")
        doc = GeneratedDoc(
            doc_id=f"research/{stem}",
            doc_type="research",
            feature=feature,
            needle=f"NEEDLE_CYCLE_{i:03d}",
            date="2026-01-01",
            path=path,
            related_ids=[f"research/{next_stem}"],
        )
        docs.append(doc)
        cycle_docs.append(doc)

    manifest.pathologies["cycle"] = cycle_docs
    manifest.pathology_details["cycle"] = [
        {"cycle_nodes": [d.doc_id for d in cycle_docs]}
    ]


def _apply_wrong_tag_count(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Emit a doc with only one tag (wrong count)."""
    stem = "2026-01-01-wrong-tag-count-doc"
    path = vault_dir / "plan" / f"{stem}.md"
    fm = '---\ntags:\n  - "#plan"\ndate: 2026-01-01\nrelated:\n  []\n---\n'
    body = "# wrong tag count\n\nThis document has only one tag.\n"
    path.write_text(fm + "\n" + body, encoding="utf-8")
    doc = GeneratedDoc(
        doc_id=f"plan/{stem}",
        doc_type="plan",
        feature="",
        needle="NEEDLE_WRONG_TAG_COUNT",
        date="2026-01-01",
        path=path,
    )
    docs.append(doc)
    manifest.pathologies["wrong_tag_count"] = [doc]
    manifest.pathology_details["wrong_tag_count"] = [{"stem": stem, "tag_count": 1}]


def _apply_stem_collision(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Emit two documents sharing the same filename stem in different type dirs."""
    shared_stem = "2026-01-01-collision-shared-stem"
    feature = "collision-feature"

    path_adr = vault_dir / "adr" / f"{shared_stem}.md"
    fm_adr = _make_frontmatter("adr", feature, "2026-01-01", [])
    path_adr.write_text(
        fm_adr + "\n# collision adr\n\nStem collision test.\n",
        encoding="utf-8",
    )
    doc_adr = GeneratedDoc(
        doc_id=f"adr/{shared_stem}",
        doc_type="adr",
        feature=feature,
        needle="NEEDLE_COLLISION_ADR",
        date="2026-01-01",
        path=path_adr,
    )

    path_plan = vault_dir / "plan" / f"{shared_stem}.md"
    fm_plan = _make_frontmatter("plan", feature, "2026-01-01", [])
    path_plan.write_text(
        fm_plan + "\n# collision plan\n\nStem collision test.\n",
        encoding="utf-8",
    )
    doc_plan = GeneratedDoc(
        doc_id=f"plan/{shared_stem}",
        doc_type="plan",
        feature=feature,
        needle="NEEDLE_COLLISION_PLAN",
        date="2026-01-01",
        path=path_plan,
    )

    docs.extend([doc_adr, doc_plan])
    manifest.pathologies["stem_collision"] = [doc_adr, doc_plan]
    manifest.pathology_details["stem_collision"] = [
        {
            "stem": shared_stem,
            "path_a": path_adr,
            "path_b": path_plan,
        }
    ]


def _apply_phantom_only_links(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Emit a plan whose related entries all point to nonexistent stems."""
    stem = "2026-01-01-phantom-only-links-plan"
    feature = "phantom-feature"
    phantom_targets = ["nonexistent-phantom-adr-001", "nonexistent-phantom-adr-002"]
    path = vault_dir / "plan" / f"{stem}.md"
    fm = _make_frontmatter("plan", feature, "2026-01-01", phantom_targets)
    body = "# phantom only links plan\n\nAll related entries are phantom.\n"
    path.write_text(fm + "\n" + body, encoding="utf-8")
    doc = GeneratedDoc(
        doc_id=f"plan/{stem}",
        doc_type="plan",
        feature=feature,
        needle="NEEDLE_PHANTOM_PLAN",
        date="2026-01-01",
        path=path,
        related_ids=[f"plan/{t}" for t in phantom_targets],
    )
    docs.append(doc)
    manifest.pathologies["phantom_only_links"] = [doc]
    manifest.pathology_details["phantom_only_links"] = [
        {"plan_doc": doc, "phantom_targets": phantom_targets}
    ]


def _apply_invalid_date_format(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Emit a doc whose date field is not ISO 8601."""
    stem = "2026-01-01-invalid-date-doc"
    path = vault_dir / "adr" / f"{stem}.md"
    fm = (
        '---\ntags:\n  - "#adr"\n  - "#invalid-date-feature"\n'
        'date: "not-a-date"\nrelated:\n  []\n---\n'
    )
    body = "# invalid date\n\nThis document has a non-ISO date.\n"
    path.write_text(fm + "\n" + body, encoding="utf-8")
    doc = GeneratedDoc(
        doc_id=f"adr/{stem}",
        doc_type="adr",
        feature="invalid-date-feature",
        needle="NEEDLE_INVALID_DATE",
        date="not-a-date",
        path=path,
    )
    docs.append(doc)
    manifest.pathologies["invalid_date_format"] = [doc]
    manifest.pathology_details["invalid_date_format"] = [
        {"stem": stem, "date_value": "not-a-date"}
    ]


def _apply_malformed_related_entry(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Emit a doc whose related list contains a non-wiki-link string."""
    stem = "2026-01-01-malformed-related-doc"
    path = vault_dir / "research" / f"{stem}.md"
    fm = (
        '---\ntags:\n  - "#research"\n  - "#malformed-related-feature"\n'
        'date: 2026-01-01\nrelated:\n  - "not-a-wiki-link"\n---\n'
    )
    body = (
        "# malformed related entry\n\nThis document has a non-wiki-link in related.\n"
    )
    path.write_text(fm + "\n" + body, encoding="utf-8")
    doc = GeneratedDoc(
        doc_id=f"research/{stem}",
        doc_type="research",
        feature="malformed-related-feature",
        needle="NEEDLE_MALFORMED_RELATED",
        date="2026-01-01",
        path=path,
    )
    docs.append(doc)
    manifest.pathologies["malformed_related_entry"] = [doc]
    manifest.pathology_details["malformed_related_entry"] = [
        {"stem": stem, "bad_entry": "not-a-wiki-link"}
    ]


def _apply_body_link(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Emit a doc whose body contains a wiki-link (not in frontmatter)."""
    stem = "2026-01-01-body-link-doc"
    feature = "body-link-feature"
    path = vault_dir / "plan" / f"{stem}.md"
    fm = _make_frontmatter("plan", feature, "2026-01-01", [])
    body = (
        "# body link doc\n\n"
        "This document has a [[body-wiki-link]] embedded in the body text.\n"
    )
    path.write_text(fm + "\n" + body, encoding="utf-8")
    doc = GeneratedDoc(
        doc_id=f"plan/{stem}",
        doc_type="plan",
        feature=feature,
        needle="NEEDLE_BODY_LINK",
        date="2026-01-01",
        path=path,
    )
    docs.append(doc)
    manifest.pathologies["body_link"] = [doc]
    manifest.pathology_details["body_link"] = [
        {"stem": stem, "body_link": "body-wiki-link"}
    ]


def _apply_bad_filename(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Emit a doc with a non-conforming filename (no date prefix)."""
    stem = "BadFilenameNoDate"
    path = vault_dir / "audit" / f"{stem}.md"
    fm = _make_frontmatter("audit", "bad-filename-feature", "2026-01-01", [])
    body = "# bad filename\n\nThis document has a non-conforming filename.\n"
    path.write_text(fm + "\n" + body, encoding="utf-8")
    doc = GeneratedDoc(
        doc_id=f"audit/{stem}",
        doc_type="audit",
        feature="bad-filename-feature",
        needle="NEEDLE_BAD_FILENAME",
        date="2026-01-01",
        path=path,
    )
    docs.append(doc)
    manifest.pathologies["bad_filename"] = [doc]
    manifest.pathology_details["bad_filename"] = [{"stem": stem}]


def _apply_unreferenced_research(
    vault_dir: Path,
    docs: list[GeneratedDoc],
    _rng: random.Random,
    manifest: CorpusManifest,
) -> None:
    """Emit a research doc that no plan or ADR links to."""
    stem = "2026-01-01-unreferenced-research-doc"
    feature = "unreferenced-feature"
    path = vault_dir / "research" / f"{stem}.md"
    fm = _make_frontmatter("research", feature, "2026-01-01", [])
    body = "# unreferenced research\n\nNo plan or ADR links to this document.\n"
    path.write_text(fm + "\n" + body, encoding="utf-8")
    doc = GeneratedDoc(
        doc_id=f"research/{stem}",
        doc_type="research",
        feature=feature,
        needle="NEEDLE_UNREFERENCED_RESEARCH",
        date="2026-01-01",
        path=path,
    )
    docs.append(doc)
    manifest.pathologies["unreferenced_research"] = [doc]
    manifest.pathology_details["unreferenced_research"] = [{"stem": stem}]


_PATHOLOGY_HANDLERS: dict[
    str,
    Any,
] = {  # type-checked at runtime via PATHOLOGY_NAMES export
    "dangling": _apply_dangling,
    "orphan": _apply_orphan,
    "missing_frontmatter": _apply_missing_frontmatter,
    "wrong_directory_tag": _apply_wrong_directory_tag,
    "stale_index": _apply_stale_index,
    "cycle": _apply_cycle,
    "wrong_tag_count": _apply_wrong_tag_count,
    "stem_collision": _apply_stem_collision,
    "phantom_only_links": _apply_phantom_only_links,
    "invalid_date_format": _apply_invalid_date_format,
    "malformed_related_entry": _apply_malformed_related_entry,
    "body_link": _apply_body_link,
    "bad_filename": _apply_bad_filename,
    "unreferenced_research": _apply_unreferenced_research,
}

#: Public, immutable set of valid pathology preset names accepted by
#: :func:`build_synthetic_vault`.  Tests and consumers should reference
#: this constant rather than the private ``_PATHOLOGY_HANDLERS`` mapping.
PATHOLOGY_NAMES: frozenset[str] = frozenset(_PATHOLOGY_HANDLERS)


def build_synthetic_vault(
    root: Path,
    *,
    n_docs: int = 24,
    graph_density: float = 0.3,
    seed: int = 42,
    pathologies: Iterable[str] | None = None,
    named_docs: dict[str, str] | None = None,
    feature_names: list[str] | None = None,
) -> CorpusManifest:
    """Generate a ``.vault/`` directory with predictable, searchable content.

    The ``graph_density`` defaults to ``0.3`` (non-zero) so tests asserting on
    graph connectivity (e.g. ``number_of_edges() > 0``) pass against the
    baseline corpus without configuration.

    Args:
        root: Project root directory. ``.vault/`` is created inside.
        n_docs: Total number of well-formed documents to generate.
            Distributed evenly across the 6 doc types.
        graph_density: Fraction of documents that link to another document
            via ``related:``. Must be >= 0.0 and <= 1.0. Default ``0.3``
            ensures the baseline corpus has edges for connectivity tests.
        seed: Random seed for reproducible generation.
        pathologies: Iterable of named pathology presets to inject after
            the well-formed corpus is written. Each preset adds affected
            docs recorded on ``manifest.pathologies[name]``.
        named_docs: Mapping from logical key to filename stem. Named docs
            are emitted in addition to the per-type baseline and participate
            in the wiki-link graph (injected before the edge-building pass).
        feature_names: Override the default ``FEATURES`` list. Useful when
            tests require specific feature names (e.g. ``"editor-demo"``).

    Returns:
        A ``CorpusManifest`` with all generated documents, their needle
        keywords, the graph edge list, and populated ``pathologies``,
        ``pathology_details``, and ``named_docs`` fields.
    """
    rng = random.Random(seed)
    vault_dir = root / ".vault"
    docs: list[GeneratedDoc] = []
    needles: dict[str, str] = {}
    graph_edges: list[tuple[str, str]] = []

    active_features = feature_names if feature_names is not None else FEATURES

    # Ensure all doc_type subdirs exist.
    for dt in DOC_TYPES:
        (vault_dir / dt).mkdir(parents=True, exist_ok=True)

    # Also create .vaultspec so workspace resolution works.
    (root / ".vaultspec").mkdir(parents=True, exist_ok=True)

    per_type = max(1, n_docs // len(DOC_TYPES))
    doc_index = 0

    for dt in DOC_TYPES:
        for _i in range(per_type):
            feature = active_features[doc_index % len(active_features)]
            needle = _needle_for(dt, doc_index)
            date = f"2026-01-{(doc_index % 28) + 1:02d}"
            stem = f"2026-01-{(doc_index % 28) + 1:02d}-{feature}-test-{doc_index:03d}"

            if dt == "exec":
                # Place exec docs inside a feature subdirectory to match the
                # expected exec/<feature>/<stem>.md shape.
                exec_subdir = vault_dir / "exec" / feature
                exec_subdir.mkdir(parents=True, exist_ok=True)
                doc_path = exec_subdir / f"{stem}.md"
                doc_id = f"exec/{feature}/{stem}"
            else:
                doc_path = vault_dir / dt / f"{stem}.md"
                doc_id = f"{dt}/{stem}"

            docs.append(
                GeneratedDoc(
                    doc_id=doc_id,
                    doc_type=dt,
                    feature=feature,
                    needle=needle,
                    date=date,
                    path=doc_path,
                    related_ids=[],
                ),
            )
            needles[needle] = doc_id
            doc_index += 1

    # Inject named docs BEFORE the edge-building pass so they participate in
    # the wiki-link graph as first-class nodes.
    named_doc_map: dict[str, GeneratedDoc] = {}
    if named_docs:
        for logical_key, stem in named_docs.items():
            dt = _infer_doc_type(stem)
            feature = active_features[doc_index % len(active_features)]
            date = "2026-01-15"
            doc_path = vault_dir / dt / f"{stem}.md"
            doc_id = f"{dt}/{stem}"

            named_doc = GeneratedDoc(
                doc_id=doc_id,
                doc_type=dt,
                feature=feature,
                needle=f"NEEDLE_NAMED_{logical_key.upper()}",
                date=date,
                path=doc_path,
                related_ids=[],
            )
            docs.append(named_doc)
            needles[named_doc.needle] = doc_id
            named_doc_map[logical_key] = named_doc
            doc_index += 1

    # Build graph links based on density.
    for doc in docs:
        if rng.random() < graph_density:
            candidates = [d for d in docs if d.doc_id != doc.doc_id]
            if candidates:
                target = rng.choice(candidates)
                doc.related_ids.append(target.doc_id)
                graph_edges.append((doc.doc_id, target.doc_id))

    # Write all documents.
    for doc in docs:
        # related: strip doc_type prefix (and any subdir) for wiki-link stem
        related_stems = [rid.rsplit("/", 1)[-1] for rid in doc.related_ids]
        fm = _make_frontmatter(doc.doc_type, doc.feature, doc.date, related_stems)
        try:
            idx = int(doc.doc_id.split("-")[-1])
        except ValueError:
            idx = 0
        body = _make_body(doc.doc_type, doc.feature, doc.needle, idx)
        doc.path.parent.mkdir(parents=True, exist_ok=True)
        doc.path.write_text(fm + "\n" + body, encoding="utf-8")

    manifest = CorpusManifest(
        root=root,
        docs=docs,
        needles=needles,
        graph_edges=graph_edges,
        named_docs=named_doc_map,
    )

    # Apply pathology presets after the well-formed corpus is written.
    if pathologies is not None:
        for name in pathologies:
            handler = _PATHOLOGY_HANDLERS.get(name)
            if handler is None:
                raise ValueError(
                    f"Unknown pathology {name!r}. "
                    f"Valid names: {list(_PATHOLOGY_HANDLERS)}"
                )
            handler(vault_dir, docs, rng, manifest)

    return manifest


def build_multi_project_fixture(
    base: Path,
    *,
    n_projects: int = 2,
    docs_per_project: int = 12,
    seed: int = 42,
) -> list[CorpusManifest]:
    """Create multiple project roots with distinct, non-overlapping corpora.

    Args:
        base: Parent directory; each project is a subdirectory.
        n_projects: Number of project roots to create.
        docs_per_project: Documents per project.
        seed: Base random seed (incremented per project).

    Returns:
        List of ``CorpusManifest`` instances, one per project.
    """
    manifests: list[CorpusManifest] = []
    for i in range(n_projects):
        project_root = base / f"project-{i}"
        project_root.mkdir(parents=True, exist_ok=True)
        manifest = build_synthetic_vault(
            project_root,
            n_docs=docs_per_project,
            seed=seed + i,
        )
        manifests.append(manifest)
    return manifests
