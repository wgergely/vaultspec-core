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
from typing import TYPE_CHECKING

from .models import DocType

__all__ = ["get_template_path", "hydrate_template"]

logger = logging.getLogger(__name__)

_KNOWN_PLACEHOLDERS = (
    "{yyyy-mm-dd-*}",
    "[[{yyyy-mm-dd-*}]]",
    "{accepted|rejected|deprecated}",
)

if TYPE_CHECKING:
    import pathlib


def hydrate_template(
    template_content: str,
    feature: str,
    date: str,
    title: str | None = None,
    *,
    related: list[str] | None = None,
    extra_tags: list[str] | None = None,
) -> str:
    """Replace placeholders in a template string with actual values.

    Supports both ``{key}`` and ``<key>`` placeholder styles.  Logs a
    warning for any placeholder that remains unresolved after substitution.

    When *related* is provided, the template's placeholder ``related:``
    entries are replaced with the resolved wiki-link list. When
    *extra_tags* is provided, those tags are appended to the ``tags:``
    block in frontmatter.

    Args:
        template_content: Raw template text containing placeholder tokens.
        feature: Feature name in kebab-case (e.g. ``editor-demo``).
        date: ISO 8601 date string (e.g. ``2026-02-06``).
        title: Optional title that maps to the ``{title}`` and ``{topic}``
            placeholders.
        related: Pre-resolved ``[[wiki-link]]`` strings to inject into
            the ``related:`` frontmatter field.
        extra_tags: Additional ``#tag`` strings to append to the ``tags:``
            frontmatter field (beyond the directory and feature tags).

    Returns:
        The fully-hydrated document string.
    """
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
        placeholders["phase"] = title  # alias used in plan/exec templates
        placeholders["step"] = title  # alias used in exec template

    # Perform replacements for both styles
    for key, value in placeholders.items():
        for pattern in [f"{{{key}}}", f"<{key}>"]:
            if pattern in hydrated:
                logger.debug("Replacing '%s' with '%s'", pattern, value)
                hydrated = hydrated.replace(pattern, value)

    # Inject resolved related links into frontmatter
    if related is not None:
        hydrated = _inject_related(hydrated, related)

    # Inject extra tags into frontmatter
    if extra_tags:
        hydrated = _inject_extra_tags(hydrated, extra_tags)

    # Check for remaining placeholders that might have been missed
    # Pattern matches {key} or <key> where key is alphanumeric with hyphens
    remaining = re.findall(r"[{<][a-z0-9\-_*]+[}>]", hydrated)
    if remaining:
        for placeholder in set(remaining):
            if placeholder in _KNOWN_PLACEHOLDERS:
                continue
            logger.warning(
                "Potential unhydrated placeholder found in template: %s", placeholder
            )

    logger.debug("Successfully hydrated template (feature=%s)", feature)
    return hydrated


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

    # Match the related: field and all its list items
    pattern = re.compile(
        r"^related:(?:\n[ \t]+- .*)*",
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
    tag_lines = []
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


def create_vault_doc(
    root_dir: pathlib.Path,
    doc_type: DocType,
    feature: str,
    date_str: str,
    title: str | None = None,
    *,
    related: list[str] | None = None,
    extra_tags: list[str] | None = None,
    content_root: pathlib.Path | None = None,
) -> pathlib.Path:
    """Scaffold a new vault document from the appropriate template.

    Args:
        root_dir: Project root (output_root from workspace layout).
        doc_type: The type of vault document to create.
        feature: Feature name in kebab-case (leading ``#`` stripped).
        date_str: ISO 8601 date string (e.g. ``2026-02-06``).
        title: Optional document title.
        related: Pre-resolved ``[[wiki-link]]`` strings for the
            ``related:`` frontmatter field.
        extra_tags: Additional ``#tag`` strings to append to ``tags:``.
        content_root: Explicit content root for template lookup.

    Returns:
        Path to the newly created document.

    Raises:
        FileNotFoundError: If no template exists for the given ``doc_type``.
        FileExistsError: If the target file already exists.
    """
    from ..config import get_config

    template_path = get_template_path(root_dir, doc_type, content_root=content_root)
    if template_path is None:
        raise FileNotFoundError(f"No template found for type '{doc_type.value}'")

    content = template_path.read_text(encoding="utf-8")

    # Default to empty related list so created documents pass validation
    # instead of keeping template placeholder entries like [[{yyyy-mm-dd-*}]]
    effective_related = related if related is not None else []

    hydrated = hydrate_template(
        content,
        feature,
        date_str,
        title,
        related=effective_related,
        extra_tags=extra_tags,
    )

    filename = f"{date_str}-{feature}-{doc_type.value}.md"
    target_dir = root_dir / get_config().docs_dir / doc_type.value
    target_path = target_dir / filename

    if target_path.exists():
        raise FileExistsError(f"File already exists at {target_path}")

    # Guard against stem collisions  - a file with the same stem in a
    # different type directory would cause silent overwrites in the
    # graph (nodes are keyed by stem).
    stem = target_path.stem
    docs_dir = root_dir / get_config().docs_dir
    if docs_dir.exists():
        for existing in docs_dir.rglob("*.md"):
            if existing.stem == stem and existing != target_path:
                raise FileExistsError(
                    f"A file with stem '{stem}' already exists at "
                    f"{existing.relative_to(root_dir)}. "
                    f"Choose a different name to avoid graph key collisions."
                )

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path.write_text(hydrated, encoding="utf-8")
    logger.info("Created %s", target_path)
    return target_path


def get_template_path(
    root_dir: pathlib.Path,
    doc_type: DocType,
    *,
    content_root: pathlib.Path | None = None,
) -> pathlib.Path | None:
    """Return the filesystem path of the template file for a given DocType.

    Args:
        root_dir: Project root used to derive the framework directory when
            ``content_root`` is not provided.
        doc_type: The vault document type whose template is requested.
        content_root: Explicit content root (e.g. ``.vaultspec/``). Templates
            live in the content tree. When ``None``, falls back to
            ``root_dir / framework_dir``.

    Returns:
        Path to the template file, or ``None`` if the type has no mapping or
        the file does not exist on disk.
    """
    from ..config import get_config

    mapping = {
        DocType.ADR: "adr.md",
        DocType.AUDIT: "audit.md",
        DocType.PLAN: "plan.md",
        DocType.RESEARCH: "research.md",
        DocType.REFERENCE: "ref-audit.md",
        DocType.EXEC: "exec-step.md",
    }

    name = mapping.get(doc_type)
    if not name:
        return None

    if content_root is not None:
        base = content_root
    else:
        cfg = get_config()
        base = root_dir / cfg.framework_dir

    path = base / "rules" / "templates" / name
    return path if path.exists() else None
