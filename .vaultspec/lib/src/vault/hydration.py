from __future__ import annotations

from typing import TYPE_CHECKING

from vault.models import DocType

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


def get_template_path(root_dir: pathlib.Path, doc_type: DocType) -> pathlib.Path | None:
    """Maps DocType to its corresponding template file."""
    from core.config import get_config

    cfg = get_config()

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

    path = root_dir / cfg.framework_dir / "templates" / name
    return path if path.exists() else None
