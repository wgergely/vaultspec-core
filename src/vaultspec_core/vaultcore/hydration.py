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
from typing import TYPE_CHECKING

from .models import DocType

__all__ = ["get_template_path", "hydrate_template"]

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import pathlib


def hydrate_template(
    template_content: str, feature: str, date: str, title: str | None = None
) -> str:
    """Replace placeholders in a template string with actual values.

    Supports both ``{key}`` and ``<key>`` placeholder styles.  Logs a
    warning for any placeholder that remains unresolved after substitution.

    Args:
        template_content: Raw template text containing placeholder tokens.
        feature: Feature name in kebab-case (e.g. ``editor-demo``).
        date: ISO 8601 date string (e.g. ``2026-02-06``).
        title: Optional title that maps to the ``{title}`` and ``{topic}``
            placeholders.

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

    # Check for remaining placeholders that might have been missed
    import re

    # Pattern matches {key} or <key> where key is alphanumeric with hyphens
    remaining = re.findall(r"[{<][a-z0-9\-|_|*]+[}>]", hydrated)
    if remaining:
        for placeholder in set(remaining):
            # Skip common non-placeholder patterns if necessary,
            # but generally everything in this format should be hydrated.
            _known = (
                "{yyyy-mm-dd-*}",
                "[[{yyyy-mm-dd-*}]]",
                "{accepted|rejected|deprecated}",
            )
            if placeholder in _known:
                continue
            logger.warning(
                "Potential unhydrated placeholder found in template: %s", placeholder
            )

    logger.debug("Successfully hydrated template (feature=%s)", feature)
    return hydrated


def create_vault_doc(
    root_dir: pathlib.Path,
    doc_type: DocType,
    feature: str,
    date_str: str,
    title: str | None = None,
    *,
    content_root: pathlib.Path | None = None,
) -> pathlib.Path:
    """Scaffold a new vault document from the appropriate template.

    Args:
        root_dir: Project root (output_root from workspace layout).
        doc_type: The type of vault document to create.
        feature: Feature name in kebab-case (leading ``#`` stripped).
        date_str: ISO 8601 date string (e.g. ``2026-02-06``).
        title: Optional document title.
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
    hydrated = hydrate_template(content, feature, date_str, title)

    filename = f"{date_str}-{feature}-{doc_type.value}.md"
    target_dir = root_dir / get_config().docs_dir / doc_type.value
    target_path = target_dir / filename

    if target_path.exists():
        raise FileExistsError(f"File already exists at {target_path}")

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
