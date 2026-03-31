"""Check for dangling wiki-links that resolve to no existing document."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ...core.helpers import atomic_write
from ._base import CheckDiagnostic, CheckResult, Severity

if TYPE_CHECKING:
    from pathlib import Path

    from ...graph import VaultGraph


__all__ = ["check_dangling"]


def check_dangling(
    root_dir: Path,
    *,
    graph: VaultGraph,
    feature: str | None = None,
    fix: bool = False,
) -> CheckResult:
    """Find wiki-links in ``related:`` frontmatter that resolve to no document.

    Iterates :meth:`~vaultspec_core.graph.VaultGraph.get_dangling_links` and
    emits an ERROR-severity diagnostic for each ``(source, target)`` pair.
    When *fix* is ``True``, removes the dangling ``[[target]]`` entry from
    the source document's ``related:`` YAML field only (body wiki-links are
    left untouched to avoid unintended prose changes).

    Args:
        root_dir: Project root directory.
        graph: Pre-built vault graph to query.
        feature: Restrict results to sources with this feature tag
            (without ``#``).
        fix: When ``True``, remove dangling entries from ``related:``
            frontmatter.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with
        check name ``"dangling"``.
    """
    from ._base import extract_feature_tags

    result = CheckResult(check_name="dangling", supports_fix=True)
    dangling_links = graph.get_dangling_links()

    if not dangling_links:
        return result

    # Group targets by source for efficient fix I/O
    source_targets: dict[str, list[str]] = {}
    for source_name, target_name in dangling_links:
        source_targets.setdefault(source_name, []).append(target_name)

    feat = feature.lstrip("#") if feature else None

    for source_name, targets in sorted(source_targets.items()):
        node = graph.nodes.get(source_name)
        if node is None or node.path is None:
            continue

        # Feature filter
        if feat:
            node_features = extract_feature_tags(list(node.tags))
            if feat not in node_features:
                continue

        rel_path = node.path.relative_to(root_dir)

        for target_name in sorted(targets):
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=f"Dangling wiki-link: [[{target_name}]] does not exist",
                    severity=Severity.ERROR,
                    fixable=True,
                    fix_description=(f"Remove [[{target_name}]] from related:"),
                )
            )

        if fix:
            fixed = _remove_related_entries(node.path, targets)
            result.fixed_count += fixed

    return result


def _remove_related_entries(path: Path, targets: list[str]) -> int:
    """Remove ``[[target]]`` lines from the ``related:`` YAML field.

    Only modifies lines within the ``related:`` list block in the YAML
    frontmatter. Returns the number of entries removed.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0

    lines = content.split("\n")
    target_set = {t.lower() for t in targets}

    # Pattern matching a related list entry like:  - "[[some-target]]"
    related_entry_re = re.compile(r'^\s*-\s*["\']?\[\[(.+?)\]\]["\']?\s*$')

    in_frontmatter = False
    in_related = False
    new_lines: list[str] = []
    removed = 0

    for line in lines:
        # Track YAML frontmatter boundaries
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
            else:
                in_frontmatter = False
                in_related = False
            new_lines.append(line)
            continue

        if in_frontmatter:
            # Detect start of related: field
            if line.startswith("related:"):
                in_related = True
                new_lines.append(line)
                continue

            # Detect exit from related: block (new top-level key)
            if in_related and not line.startswith(" ") and not line.startswith("\t"):
                in_related = False

            if in_related:
                m = related_entry_re.match(line)
                if m and m.group(1).lower() in target_set:
                    removed += 1
                    continue

        new_lines.append(line)

    if removed:
        new_content = "\n".join(new_lines)
        bak = path.with_suffix(path.suffix + ".bak")
        bak.write_bytes(path.read_bytes())
        try:
            atomic_write(path, new_content)
        except Exception:
            if bak.exists():
                bak.replace(path)
            raise
        bak.unlink(missing_ok=True)

    return removed
