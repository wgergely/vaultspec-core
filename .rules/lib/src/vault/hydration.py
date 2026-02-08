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
    mapping = {
        DocType.ADR: "ADR.md",
        DocType.PLAN: "PLAN.md",
        DocType.RESEARCH: "RESEARCH.md",
        DocType.REFERENCE: "REF_AUDIT.md",
        DocType.EXEC: "EXEC_STEP.md",  # Defaulting to step
    }

    name = mapping.get(doc_type)
    if not name:
        return None

    path = root_dir / ".rules" / "templates" / name
    return path if path.exists() else None
