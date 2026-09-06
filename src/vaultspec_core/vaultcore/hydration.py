"""Hydrate templates and scaffold new `.vault/` documents.

This module is the write-side complement to parsing and scanning. It locates
templates, substitutes placeholders, and creates new vault records with the
expected structure and metadata shape.

Usage:
    Use `hydrate_template(...)` to render template content and
    `create_vault_doc(...)` to create a fully scaffolded vault document.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ..core.exceptions import ResourceExistsError, VaultSpecError
from .body_schema import CURRENT_BODY_SCHEMA
from .models import DocType
from .normalize import normalize_vault_date
from .query_rename import assert_within_docs

__all__ = [
    "AUTHOR_FILLED_PLACEHOLDERS",
    "MACHINE_FILLED_PLACEHOLDERS",
    "DocumentIdentity",
    "ExecBinding",
    "ParentPlan",
    "TemplateFields",
    "WritePolicy",
    "create_vault_doc",
    "get_template_path",
    "hydrate_template",
]

logger = logging.getLogger(__name__)

#: Placeholders :func:`hydrate_template` fills, plus the two the index
#: generator and the related-link injector own. A template may leave these
#: outside its hint comments; anything else outside a comment reaches the
#: author unfilled. ``tests/cli/test_corpus_contracts.py`` holds every shipped
#: template to this set, so a new placeholder is added here first.
MACHINE_FILLED_PLACEHOLDERS = frozenset(
    {
        "feature",
        "yyyy-mm-dd",
        "date",
        "title",
        "topic",  # alias of title in the research/reference templates
        "phase",  # alias of title, or the explicit Phase id on a summary
        "step",  # alias of title in the exec template
        "tier",
        "step_id",
        "plan_stem",
        "heading",
        "scope_block",
        "yyyy-mm-dd-*",  # related-link seed, stripped by _inject_related
        "yyyy-mm-dd-*-plan",  # fallback value the hydrator itself inserts
        "document_list",  # vaultcore/index.py, not hydrate_template
    }
)

#: Placeholders the author fills by hand; the template says so beside them.
AUTHOR_FILLED_PLACEHOLDERS = frozenset(
    {
        "proposed|accepted|rejected|superseded|deprecated",  # ADR status enum
    }
)

# Machine-filled placeholders that legitimately survive :func:`hydrate_template`:
# the related-link seed is stripped later by ``_inject_related``.
_RESIDUE_PLACEHOLDERS = frozenset({"yyyy-mm-dd-*"})

# Residue the post-hydration scan must not warn about. Every other registered
# placeholder left standing is a hydration miss and is reported.
_KNOWN_PLACEHOLDERS = frozenset(
    {f"{{{name}}}" for name in _RESIDUE_PLACEHOLDERS | AUTHOR_FILLED_PLACEHOLDERS}
    | {"[[{yyyy-mm-dd-*}]]"}
)

# Current on-disk filename for each template, keyed by document type. A type
# absent from this map has no template and resolves to ``None``.
_TEMPLATE_NAMES = {
    DocType.ADR: "adr.md",
    DocType.AUDIT: "audit.md",
    DocType.PLAN: "plan.md",
    DocType.RESEARCH: "research.md",
    DocType.REFERENCE: "reference.md",
    DocType.INDEX: "index.md",
}

#: The refusal every scaffold ingress raises for an ``exec`` document that is
#: not the plan's ledger. Execution has exactly one artifact and one writer.
EXEC_NOT_SCAFFOLDED = "execution is logged with `vaultspec-core vault exec log`"

# Document types that admit the optional topic infix
# (``{date}-{feature}-{topic}-{type}.md``). Plans retain one execution
# cluster and exec filenames are machine-derived, so they remain excluded.
_TOPIC_INFIX_TYPES = frozenset(
    {DocType.ADR, DocType.AUDIT, DocType.REFERENCE, DocType.RESEARCH}
)

# The exec document type has exactly one template: the ledger, one document
# per plan carrying every Step's mechanical rows, selected via the ``ledger``
# flag on ``ExecBinding``. There is no per-Step or per-Phase template.
_EXEC_LEDGER_TEMPLATE = "exec-ledger.md"

# Prior on-disk filenames for templates that have since been renamed in the
# source tree. A deployed mirror that predates the rename still ships the old
# filename; :func:`get_template_path` falls back to these so the scaffolder
# keeps working on a not-yet-upgraded workspace.
#
# TODO(remove after the release following the first published release that
# ships reference.md): drop the ref-audit.md legacy fallback. The
# `ref-audit.md` -> `reference.md` rename has not shipped in a release yet
# (current version 0.1.26), so the grace path must survive one upgrade cycle
# before removal. See REVIEW-005 in the firmware-wording-review audit.
_LEGACY_TEMPLATE_NAMES = {
    DocType.REFERENCE: "ref-audit.md",
}

if TYPE_CHECKING:
    import pathlib


@dataclass(frozen=True, slots=True)
class DocumentIdentity:
    """The values that name a vault document on disk.

    Together these decide the target directory, the filename, and the
    feature tag the scaffolded frontmatter carries.

    Attributes:
        doc_type: The type of vault document to create.
        feature: Feature name in kebab-case (leading ``#`` stripped).
        date: The document's date. Admitted by the scaffolder as a calendar
            date and re-rendered as ``yyyy-mm-dd`` before it names anything,
            so the lenient forms the vault's parser accepts may be passed
            here and a value that is not a date is refused.
        topic: Optional kebab-case narrative infix. Admitted only for the
            narrative trio (``audit``, ``reference``, ``research``) and
            ``adr``; the filename resolves to
            ``{date}-{feature}-{topic}-{type}.md``. Omitted, the filename
            keeps its ``{date}-{feature}-{type}.md`` form.
    """

    doc_type: DocType
    feature: str
    date: str
    topic: str | None = None


@dataclass(frozen=True, slots=True)
class TemplateFields:
    """Author-supplied values a template's placeholders resolve to.

    Attributes:
        title: Optional title that maps to the ``{title}`` and ``{topic}``
            placeholders.
        related: Pre-resolved ``[[wiki-link]]`` strings to inject into the
            ``related:`` frontmatter field.
        extra_tags: Tags to append during rendering. Document creation accepts
            only the required directory and feature tags and removes duplicates.
        tier: Optional plan tier value (``L1``..``L4``) substituted into the
            ``{tier}`` placeholder for plan templates.
    """

    title: str | None = None
    related: list[str] | None = None
    extra_tags: list[str] | None = None
    tier: str | None = None


@dataclass(frozen=True, slots=True)
class ParentPlan:
    """The plan document an execution record hangs off.

    Attributes:
        date: The parent plan's date, used for the execution folder and
            filename prefix. Falling back to the record's own date when
            omitted.
        stem: The parent plan's filename stem, used for the ``{plan_stem}``
            placeholder and the leading ``related:`` wiki-link.
    """

    date: str | None = None
    stem: str | None = None


@dataclass(frozen=True, slots=True)
class ExecBinding:
    """The plan an execution ledger records.

    Every field is inert for non-execution document types, whose templates
    carry none of the corresponding placeholders.

    Attributes:
        plan: Identity of the parent plan.
        ledger: When ``True``, the document is the plan's ledger, scaffolded
            from the ``exec-ledger.md`` template. An ``exec`` document with
            this flag unset is refused: execution has no other artifact.
    """

    plan: ParentPlan = ParentPlan()
    ledger: bool = False


@dataclass(frozen=True, slots=True)
class WritePolicy:
    """How the scaffolder treats the target path.

    Attributes:
        force: If ``True``, overwrite an existing document.
        dry_run: If ``True``, resolve the target path without writing.
    """

    force: bool = False
    dry_run: bool = False


def hydrate_template(
    template_content: str,
    feature: str,
    date: str,
    fields: TemplateFields | None = None,
    exec_binding: ExecBinding | None = None,
) -> str:
    """Replace placeholders in a template string with actual values.

    Supports both ``{key}`` and ``<key>`` placeholder styles.  Logs a
    warning for any placeholder that remains unresolved after substitution.

    When ``fields.related`` is provided, the template's placeholder
    ``related:`` entries are replaced with the resolved wiki-link list. When
    ``fields.extra_tags`` is provided, those tags are appended to the
    ``tags:`` block in frontmatter. When ``fields.tier`` is provided, the
    template's ``{tier}`` placeholder is substituted; otherwise the
    placeholder is left as-is for the caller to fill.

    Args:
        template_content: Raw template text containing placeholder tokens.
        feature: Feature name in kebab-case (e.g. ``editor-demo``).
        date: ISO 8601 date string (e.g. ``2026-02-06``).
        fields: Author-supplied placeholder values. Defaults to an empty
            :class:`TemplateFields`, leaving every optional placeholder
            for the caller to fill.
        exec_binding: The plan an execution ledger records. Defaults to an
            empty :class:`ExecBinding`, which leaves ``{plan_stem}`` on its
            generic fallback.

    Returns:
        The fully-hydrated document string.
    """
    if fields is None:
        fields = TemplateFields()
    if exec_binding is None:
        exec_binding = ExecBinding()

    title = fields.title
    tier = fields.tier

    hydrated = template_content

    # Normalize placeholders map
    placeholders = {
        "feature": feature,
        "yyyy-mm-dd": date,
        "date": date,
    }
    if title:
        placeholders["title"] = title
        placeholders["topic"] = title  # alias used in research template
        placeholders["phase"] = title  # alias used in the plan template
    if tier:
        placeholders["tier"] = tier

    # Perform replacements for both styles
    for key, value in placeholders.items():
        patterns = [f"{{{key}}}", f"<{key}>"]
        if key == "tier":
            # The plan template quotes the placeholder (`tier: '{tier}'`) so
            # YAML and mdformat treat it as a string; the quotes are stripped
            # on substitution to keep the scaffolded scalar unquoted. mdformat
            # parses a legacy unquoted `{tier}` YAML placeholder as an inline
            # map and normalizes it to `{tier: null}`.
            patterns.insert(0, "'{tier}'")
            patterns.append("{tier: null}")
        for pattern in patterns:
            if pattern in hydrated:
                logger.debug("Replacing '%s' with '%s'", pattern, value)
                hydrated = hydrated.replace(pattern, value)

    # Hydrate the ledger's parent-plan placeholder.
    plan_stem = exec_binding.plan.stem
    val_plan_stem = plan_stem if plan_stem is not None else "{yyyy-mm-dd-*-plan}"
    hydrated = hydrated.replace("{plan_stem}", val_plan_stem)

    # Stamp the CLI-maintained modified field (vault-orientation ADR D3):
    # at scaffold time it equals the creation date. Injected here rather
    # than relying on the template carrying the field, so scaffolds from
    # mirrors whose templates predate the schema row still get stamped.
    hydrated = _inject_modified(hydrated, date)
    hydrated = _inject_body_schema(hydrated)

    # Inject resolved related links into frontmatter
    if fields.related is not None:
        hydrated = _inject_related(hydrated, fields.related)

    # Inject extra tags into frontmatter
    if fields.extra_tags:
        hydrated = _inject_extra_tags(hydrated, fields.extra_tags)

    # Attest the scaffolded body last, once every frontmatter injection above
    # has landed: the fingerprint covers the body only, but computing it before
    # the frontmatter is final would attest text this function is still editing.
    hydrated = _inject_body_hash(hydrated)

    # Check for remaining placeholders that might have been missed.
    # Pattern matches {key} or <key> where key is alphanumeric with hyphens.
    # Strip HTML comment regions (<!-- ... -->) first: tokens inside those
    # are intentional template guidance for the human author, not
    # frontmatter placeholders. Without this, every freshly scaffolded
    # adr/plan/exec doc emits warnings about {adr}, {research},
    # {reference}, <display-path> etc. that live inside the template's
    # own guidance comments.
    scan_target = re.sub(r"<!--.*?-->", "", hydrated, flags=re.DOTALL)
    remaining = re.findall(r"[{<][a-z0-9\-_*]+[}>]", scan_target)
    if "{tier: null}" in scan_target:
        remaining.append("{tier: null}")
    if remaining:
        for placeholder in set(remaining):
            if placeholder in _KNOWN_PLACEHOLDERS:
                continue
            logger.warning(
                "Potential unhydrated placeholder found in template: %s",
                placeholder,
            )

    logger.debug("Successfully hydrated template (feature=%s)", feature)
    return hydrated


def _inject_modified(content: str, date: str) -> str:
    """Ensure the frontmatter carries a ``modified:`` stamp equal to *date*.

    Implements the scaffold-time half of the vault-orientation ADR's
    decision D3: every scaffolded document starts with
    ``modified: '<date>'`` (canonical quoted ``yyyy-mm-dd``, same value
    as ``date:``). When the template already carries a ``modified:``
    field (templates gain the schema row separately), the rendered
    value is left untouched; otherwise the stamp is inserted directly
    after the ``date:`` line inside the frontmatter block.

    Args:
        content: Full document text with YAML frontmatter.
        date: ISO 8601 date string the stamp is set to.

    Returns:
        Document text whose frontmatter carries the ``modified:`` field.
        Content without a recognisable frontmatter ``date:`` line is
        returned unchanged.
    """
    fence = re.match(r"^---\s*\n(.*?\n)---", content, re.DOTALL)
    if not fence:
        return content
    frontmatter_block = fence.group(1)

    if re.search(r"^modified:", frontmatter_block, re.MULTILINE):
        return content

    date_line = re.search(r"^date:[^\n]*\n", frontmatter_block, re.MULTILINE)
    if not date_line:
        return content

    insert_at = fence.start(1) + date_line.end()
    return content[:insert_at] + f"modified: '{date}'\n" + content[insert_at:]


def _inject_body_schema(content: str) -> str:
    """Ensure every newly hydrated document declares the current contract.

    A stale deployed template may carry an older schema identifier, but a new
    document cannot self-classify as historical. The scaffolder therefore
    always writes :data:`CURRENT_BODY_SCHEMA` rather than preserving a template
    token; legacy schemas are available only through hash attestation.
    """
    fence = re.match(r"^---\s*\n(.*?\n)---", content, re.DOTALL)
    if not fence:
        return content
    frontmatter_block = fence.group(1)
    schema_line = re.search(r"^body_schema:[^\n]*\n", frontmatter_block, re.MULTILINE)
    if schema_line:
        start = fence.start(1) + schema_line.start()
        end = fence.start(1) + schema_line.end()
        return (
            content[:start] + f"body_schema: '{CURRENT_BODY_SCHEMA}'\n" + content[end:]
        )

    modified_line = re.search(r"^modified:[^\n]*\n", frontmatter_block, re.MULTILINE)
    if not modified_line:
        return content
    insert_at = fence.start(1) + modified_line.end()
    return (
        content[:insert_at]
        + f"body_schema: '{CURRENT_BODY_SCHEMA}'\n"
        + content[insert_at:]
    )


def _inject_body_hash(content: str) -> str:
    """Attest the scaffolded body with its ``body_hash:`` fingerprint.

    The scaffold-time half of the modified-stamp-provenance decision: a new
    document leaves the scaffolder already attesting its own body, so the
    very first hand edit to its prose is detectable. Injected here rather
    than carried by the templates because the value is derived from the
    rendered body and cannot be a static template literal.

    Args:
        content: Fully hydrated document text with YAML frontmatter.

    Returns:
        Document text carrying the ``body_hash:`` field, or the input
        unchanged when the frontmatter offers no canonical anchor.
    """
    from .body_hash import set_body_hash

    return set_body_hash(content)


def _inject_related(content: str, related: list[str]) -> str:
    """Replace the ``related:`` block in YAML frontmatter with resolved links.

    Args:
        content: Full document text with YAML frontmatter.
        related: List of ``[[wiki-link]]`` strings.

    Returns:
        Document text with the ``related:`` field updated.
    """
    if not related:
        # Empty list - set related to empty
        new_block = "related: []"
    else:
        lines = ["related:"]
        for link in related:
            lines.append(f'  - "{link}"')
        new_block = "\n".join(lines)

    # Match the related: field and all its list items or inline empty list
    pattern = re.compile(
        r"^related:(?:[ \t]*\[\]|(?:\n[ \t]+- .*)*)",
        re.MULTILINE,
    )
    result = pattern.sub(new_block, content, count=1)
    return result


def _inject_extra_tags(content: str, extra_tags: list[str]) -> str:
    """Append additional tags to the ``tags:`` block in YAML frontmatter.

    Args:
        content: Full document text with YAML frontmatter.
        extra_tags: List of ``#tag`` strings to append.

    Returns:
        Document text with extra tags appended to the ``tags:`` field.
    """
    # Find the last tag entry line in the tags block
    # Tags block looks like:
    #   tags:
    #     - "#adr"
    #     - "#feature"
    # We want to insert after the last - "..." line in the tags block
    tag_lines: list[str] = []
    for tag in extra_tags:
        normalized = tag if tag.startswith("#") else f"#{tag}"
        tag_lines.append(f'  - "{normalized}"')

    insertion = "\n".join(tag_lines)

    # Find the tags block and append after the last entry
    pattern = re.compile(
        r"(tags:\s*\n(?:\s+-\s+.*\n)*\s+-\s+.*)",
        re.MULTILINE,
    )
    match = pattern.search(content)
    if match:
        return content[: match.end()] + "\n" + insertion + content[match.end() :]

    return content


def _admit_date(raw: str | None, *, label: str) -> str:
    """Return *raw* as a canonical ``yyyy-mm-dd`` token, or refuse it.

    The scaffolder composes a document's directory and filename from its
    date, so an unparsed date is a path segment the caller chose. Routing it
    through :func:`~vaultspec_core.vaultcore.normalize.normalize_vault_date`
    means the value that reaches the composition is re-rendered from a
    parsed :class:`datetime.date` and can carry nothing but digits and
    hyphens.

    Args:
        raw: The candidate date value.
        label: The noun used in the failure message, distinguishing the
            document's own date from its parent plan's.

    Returns:
        The canonical ``yyyy-mm-dd`` string.

    Raises:
        VaultSpecError: When the value is absent or does not parse as a
            calendar date.
    """
    if not raw:
        raise VaultSpecError(f"A {label} is required to name the document.")
    result = normalize_vault_date(raw, label=label)
    if not result.ok or result.value is None:
        raise VaultSpecError(str(result.error))
    return result.value


def create_vault_doc(
    root_dir: pathlib.Path,
    identity: DocumentIdentity,
    fields: TemplateFields | None = None,
    *,
    exec_binding: ExecBinding | None = None,
    write: WritePolicy | None = None,
    content_root: pathlib.Path | None = None,
) -> pathlib.Path:
    """Scaffold a new vault document from the appropriate template.

    Args:
        root_dir: Project root (output_root from workspace layout).
        identity: Type, feature, date, and optional narrative infix of the
            document to create. A ``topic`` on a type outside the admitting
            set raises :class:`ValueError` (adr and plan cardinality rules
            forbid disambiguation-by-infix; exec filenames are
            machine-derived).
        fields: Author-supplied placeholder values. Defaults to an empty
            :class:`TemplateFields`.
        exec_binding: The plan an execution ledger records. An ``exec``
            document is scaffolded only with ``ledger=True``.
        write: Overwrite and dry-run policy. Defaults to a
            :class:`WritePolicy` that refuses to overwrite and does write.
        content_root: Explicit content root for template lookup.

    Returns:
        Path to the newly created (or would-be-created) document.

    Raises:
        FileNotFoundError: If no template exists for the identity's type.
        ValueError: If an ``exec`` document is requested without the ledger
            binding; execution is logged with ``vaultspec-core vault exec log``.
        ResourceExistsError: If the target file already exists and the
            write policy does not force an overwrite.
        VaultSpecError: If supplied tags are not the required directory and
            feature tags; if the identity's date (or the parent plan's) is
            not a calendar date; or if the composed destination resolves
            outside the vault's document root.
    """
    from ..config import get_config

    if fields is None:
        fields = TemplateFields()
    if exec_binding is None:
        exec_binding = ExecBinding()
    if write is None:
        write = WritePolicy()

    doc_type = identity.doc_type
    feature = identity.feature
    topic = identity.topic
    plan_stem = exec_binding.plan.stem

    # Admission for the two date-shaped values that become path segments.
    # Both are parsed into a real calendar date and re-rendered from it, so
    # what reaches the filename below is ten characters of digits and
    # hyphens by construction rather than by inspection of the caller's
    # string. This is the chokepoint: it holds for every surface that
    # scaffolds a document, so no caller has to remember to validate first.
    date_str = _admit_date(identity.date, label="document date")
    plan_date = (
        _admit_date(exec_binding.plan.date, label="parent plan date")
        if exec_binding.plan.date
        else None
    )

    if fields.extra_tags:
        required_tags = {doc_type.tag, f"#{feature}"}
        unsupported = [
            tag
            for tag in fields.extra_tags
            if (tag if tag.startswith("#") else f"#{tag}") not in required_tags
        ]
        if unsupported:
            raise VaultSpecError(
                f"Unsupported tags: {', '.join(unsupported)}. "
                f"Only {doc_type.tag} and #{feature} are allowed."
            )
        fields = replace(fields, extra_tags=None)

    if topic is not None and doc_type not in _TOPIC_INFIX_TYPES:
        raise ValueError(
            f"topic infix is not supported for '{doc_type.value}' documents; "
            "admitted types: adr, audit, reference, research"
        )
    if doc_type is DocType.EXEC and not exec_binding.ledger:
        raise ValueError(EXEC_NOT_SCAFFOLDED)

    template_path = get_template_path(
        root_dir,
        doc_type,
        content_root=content_root,
        ledger=exec_binding.ledger,
    )
    if template_path is None:
        raise FileNotFoundError(
            f"No template found for type '{doc_type.value}'. The deployed "
            "template mirror is missing or stale; run "
            "`vaultspec-core install --upgrade` to refresh it."
        )

    content = template_path.read_text(encoding="utf-8")

    # Default to empty related list so created documents pass validation
    # instead of keeping template placeholder entries like [[{yyyy-mm-dd-*}]]
    effective_related = list(fields.related) if fields.related is not None else []
    if plan_stem:
        plan_link = f"[[{plan_stem}]]"
        if plan_link not in effective_related:
            effective_related.insert(0, plan_link)

    # A topic-infixed document scaffolded without an explicit title would
    # otherwise leave the template's `{topic}`/`{title}` heading placeholder
    # unhydrated and fail the placeholder check; the humanized topic is a
    # valid concise-prose heading value, and an explicit title still wins.
    effective_title = fields.title
    if effective_title is None and topic is not None:
        effective_title = topic.replace("-", " ")

    hydrated = hydrate_template(
        content,
        feature,
        date_str,
        replace(fields, title=effective_title, related=effective_related),
        exec_binding,
    )

    if doc_type is DocType.EXEC and exec_binding.ledger:
        # One ledger per plan, so the filename carries no Step or Phase
        # segment - the Step identity lives in the rows, not the path.
        filename = f"{plan_date or date_str}-{feature}-ledger.md"
        target_dir = (
            root_dir
            / get_config().docs_dir
            / doc_type.value
            / f"{plan_date or date_str}-{feature}"
        )
    elif topic is not None:
        filename = f"{date_str}-{feature}-{topic}-{doc_type.value}.md"
        target_dir = root_dir / get_config().docs_dir / doc_type.value
    else:
        filename = f"{date_str}-{feature}-{doc_type.value}.md"
        target_dir = root_dir / get_config().docs_dir / doc_type.value

    target_path = target_dir / filename

    # Containment backstop. The date admission above closes the field this
    # advisory was raised for, but the guard is bound to the composed path
    # rather than to any one field, so the next identity value that grows a
    # path segment inherits it without a second audit. Both sides resolve
    # before comparison, so a `..` segment, an absolute value, and a
    # symlinked type directory are all refused alike.
    docs_root = root_dir / get_config().docs_dir
    assert_within_docs(docs_root, target_dir)
    assert_within_docs(docs_root, target_path)

    if not write.force:
        if target_path.exists():
            raise ResourceExistsError(
                f"File already exists at {target_path}",
                hint="Use --force to overwrite",
            )

        # Guard against stem collisions  - a file with the same stem in a
        # different type directory would cause silent overwrites in the
        # graph (nodes are keyed by stem).
        stem = target_path.stem
        docs_dir = root_dir / get_config().docs_dir
        if docs_dir.exists():
            for existing in docs_dir.rglob("*.md"):
                if existing.stem == stem and existing != target_path:
                    raise ResourceExistsError(
                        f"A file with stem '{stem}' already exists at "
                        f"{existing.relative_to(root_dir)}. "
                        f"Choose a different name to avoid graph key collisions.",
                        hint="Use --force to overwrite",
                    )

    # Emit-time validator: refuse to write content the framework's own
    # validators would reject on the next read. Closes the
    # scaffolder-integrity invariant prescribed by the
    # cli-scaffolder-integrity ADR.
    _assert_scaffolded_content_valid(hydrated, doc_type)

    if write.dry_run:
        return target_path

    from ..core.helpers import atomic_write

    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(target_path, hydrated)
    logger.info("Created %s", target_path)
    return target_path


class ScaffoldValidationError(ValueError):
    """Raised when a scaffolded document would fail its own validator.

    The scaffolder must never write a document the framework's read-path
    validators would reject. When this exception fires, the failure is
    in the template + hydration pipeline, not in the operator's input.
    """


def _assert_scaffolded_content_valid(content: str, doc_type: DocType) -> None:
    """Validate hydrated scaffolder output before the write hits disk.

    Scope is deliberately narrow: this is the emit-time guard against
    the B2/B5-shape antipattern where a scaffolder writes content the
    next read-path command crashes on with an uncaught exception. It
    is not a general lint pass -- frontmatter advisories from custom
    templates remain post-creation warnings via
    :func:`vaultspec_core.cli.vault_cmd._validate_created_doc` and are
    not blocking here.

    For plan documents the frontmatter is parsed with the same parser
    the read path uses; a failure (e.g. an invalid ``tier`` value)
    raises :class:`ScaffoldValidationError` and the scaffolder must
    not write. Other document types have no crash-on-parse frontmatter
    field today, so they pass through.
    """
    if doc_type is DocType.PLAN:
        try:
            from ..plan.frontmatter import parse_plan_frontmatter
        except ImportError:
            return
        try:
            parse_plan_frontmatter(content)
        except Exception as exc:
            msg = (
                "Scaffolded plan failed the framework's own frontmatter "
                f"validator: {exc}. The template + hydration pipeline "
                "produced content the next vault plan command would "
                "reject. This is a scaffolder bug; do not edit the file "
                "by hand."
            )
            raise ScaffoldValidationError(msg) from exc


def get_template_path(
    root_dir: pathlib.Path,
    doc_type: DocType,
    *,
    content_root: pathlib.Path | None = None,
    ledger: bool = False,
) -> pathlib.Path | None:
    """Return the filesystem path of the template file for a given DocType.

    Args:
        root_dir: Project root used to derive the framework directory when
            ``content_root`` is not provided.
        doc_type: The vault document type whose template is requested.
        content_root: Explicit content root (e.g. ``.vaultspec/``). Templates
            live in the content tree. When ``None``, falls back to
            ``root_dir / framework_dir``.
        ledger: When ``True`` and *doc_type* is :attr:`DocType.EXEC`, resolve
            the ledger template (``exec-ledger.md``), the only exec template.

    Returns:
        Path to the template file, or ``None`` if the type has no mapping or
        the file does not exist on disk.
    """
    from ..config import get_config

    if ledger and doc_type is DocType.EXEC:
        name: str | None = _EXEC_LEDGER_TEMPLATE
    else:
        name = _TEMPLATE_NAMES.get(doc_type)
    if not name:
        return None

    if content_root is not None:
        base = content_root
    else:
        cfg = get_config()
        base = root_dir / cfg.framework_dir

    templates_dir = base / "templates"
    path = templates_dir / name
    if path.exists():
        return path

    # Legacy-filename fallback for renamed templates. A workspace whose
    # deployed mirror predates a template rename (for example a stale
    # `.vaultspec/templates/` that still ships `ref-audit.md` after the source
    # renamed it to `reference.md`) would otherwise resolve to a missing
    # file. Fall back to the prior filename so the verb keeps working on a
    # not-yet-upgraded workspace until the operator re-runs
    # `vaultspec-core install --upgrade`. See REVIEW-005 in the
    # firmware-wording-review audit.
    #
    # TODO(remove after the release following the first published release that
    # ships reference.md): drop this ref-audit.md legacy fallback branch.
    legacy_name = _LEGACY_TEMPLATE_NAMES.get(doc_type)
    if legacy_name is not None:
        legacy_path = templates_dir / legacy_name
        if legacy_path.exists():
            logger.warning(
                "Template '%s' for type '%s' is missing; falling back to the "
                "legacy filename '%s'. Run `vaultspec-core install --upgrade` "
                "to refresh the deployed mirror.",
                name,
                doc_type.value,
                legacy_name,
            )
            return legacy_path

    return None
