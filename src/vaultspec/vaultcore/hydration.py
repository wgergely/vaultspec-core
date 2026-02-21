from __future__ import annotations

from typing import TYPE_CHECKING

from .models import DocType

__all__ = ["get_template_path", "hydrate_template"]

if TYPE_CHECKING:
    import pathlib


def hydrate_template(
    template_content: str, feature: str, date: str, title: str | None = None
) -> str:
    """Replaces placeholders in a template with actual values."""
    hydrated = template_content
    hydrated = hydrated.replace("<feature>", feature)
    hydrated = hydrated.replace("<yyyy-mm-dd>", date)
    if title:
        hydrated = hydrated.replace("<title>", title)

    # Simple replacement for common placeholders
    # In a real system, we might use a more robust template engine
    return hydrated


def get_template_path(
    root_dir: pathlib.Path,
    doc_type: DocType,
    *,
    content_root: pathlib.Path | None = None,
) -> pathlib.Path | None:
    """Maps DocType to its corresponding template file.

    Parameters
    ----------
    content_root:
        Explicit content root (e.g. ``.vaultspec/``).  Templates live in
        the content tree.  When ``None``, falls back to
        ``root_dir / framework_dir``.
    """
    from vaultspec.core import get_config

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
