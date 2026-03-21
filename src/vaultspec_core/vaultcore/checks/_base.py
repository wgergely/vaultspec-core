"""Foundation types for vault health checks.

Defines the result model used by all checkers and a shared rendering
function for Rich console output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from rich.console import Console

__all__ = [
    "CheckDiagnostic",
    "CheckResult",
    "Severity",
    "extract_feature_tags",
    "render_check_result",
]


class Severity(StrEnum):
    """Diagnostic severity level for vault health check findings."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class CheckDiagnostic:
    """A single finding from a vault health check.

    Attributes:
        path: Relative path to the affected document, or ``None`` for
            vault-wide findings.
        message: Human-readable description of the issue.
        severity: Urgency level; one of :class:`Severity`.
        fixable: ``True`` when ``--fix`` can resolve this diagnostic.
        fix_description: Short description of the corrective action, or
            ``None`` when not applicable.
    """

    path: Path | None
    message: str
    severity: Severity
    fixable: bool = False
    fix_description: str | None = None


@dataclass
class CheckResult:
    """Aggregated result from a single check pass.

    Attributes:
        check_name: Identifier string displayed in CLI output
            (e.g. ``"frontmatter"``).
        diagnostics: All findings produced by this check.
        fixed_count: Number of issues auto-corrected when run with ``--fix``.
        supports_fix: ``True`` when this checker accepts a ``fix=True`` argument.
    """

    check_name: str
    diagnostics: list[CheckDiagnostic] = field(default_factory=list)
    fixed_count: int = 0
    supports_fix: bool = False

    @property
    def error_count(self) -> int:
        """Number of ERROR-severity diagnostics."""
        return sum(1 for d in self.diagnostics if d.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        """Number of WARNING-severity diagnostics."""
        return sum(1 for d in self.diagnostics if d.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        """Number of INFO-severity diagnostics."""
        return sum(1 for d in self.diagnostics if d.severity == Severity.INFO)

    @property
    def is_clean(self) -> bool:
        """``True`` when no diagnostics were produced."""
        return len(self.diagnostics) == 0


def extract_feature_tags(tags: list[str]) -> list[str]:
    """Return the feature tags from a list of vault tags.

    Filters out directory tags (``#adr``, ``#exec``, etc.) and strips
    leading ``#`` from the remaining feature tags.

    Args:
        tags: Raw tag strings from document metadata.

    Returns:
        List of feature tag values without ``#`` prefix.
    """
    from ..models import DocType

    type_values = {d.value for d in DocType}
    return [t.lstrip("#") for t in tags if t.lstrip("#") not in type_values]


_SEVERITY_STYLE = {
    Severity.ERROR: "red",
    Severity.WARNING: "yellow",
    Severity.INFO: "dim",
}

_SEVERITY_ICON = {
    Severity.ERROR: "✗",
    Severity.WARNING: "!",
    Severity.INFO: "·",
}


def render_check_result(
    console: Console,
    result: CheckResult,
    *,
    verbose: bool = False,
    summary_only: bool = False,
) -> None:
    """Render a CheckResult to a Rich console.

    Args:
        console: Rich Console instance.
        result: The check result to render.
        verbose: When False, suppress INFO-level diagnostics.
        summary_only: When True, show only the one-line summary per check.
    """
    if result.is_clean:
        console.print(f"  [green]✓[/green] {result.check_name}: [green]clean[/green]")
        return

    errors = result.error_count
    warnings = result.warning_count
    infos = result.info_count

    parts = []
    if errors:
        parts.append(f"[red]{errors} error{'s' if errors != 1 else ''}[/red]")
    if warnings:
        parts.append(
            f"[yellow]{warnings} warning{'s' if warnings != 1 else ''}[/yellow]"
        )
    if infos and verbose:
        parts.append(f"[dim]{infos} info[/dim]")

    summary = ", ".join(parts)
    if result.fixed_count:
        summary += f" ([green]{result.fixed_count} fixed[/green])"

    icon = "[red]✗[/red]" if errors else "[yellow]![/yellow]"
    console.print(f"  {icon} {result.check_name}: {summary}")

    if summary_only:
        return

    for diag in result.diagnostics:
        if diag.severity == Severity.INFO and not verbose:
            continue
        style = _SEVERITY_STYLE[diag.severity]
        icon = _SEVERITY_ICON[diag.severity]
        path_str = str(diag.path) if diag.path else ""
        if path_str:
            console.print(f"    [{style}]{icon}[/{style}] {path_str}")
            console.print(f"      {diag.message}")
        else:
            console.print(f"    [{style}]{icon}[/{style}] {diag.message}")
        if diag.fix_description:
            console.print(f"      [dim]fix: {diag.fix_description}[/dim]")
