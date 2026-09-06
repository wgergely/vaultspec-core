"""Foundation types for vault health checks.

Defines the result model used by all checkers, snapshot types for
shared data passing, and a shared rendering function for Rich console
output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from ..models import DocumentMetadata

if TYPE_CHECKING:
    from rich.console import Console

VaultDocData = tuple[DocumentMetadata, str]
"""Parsed document payload: ``(metadata, body)``."""

VaultSnapshot = dict[Path, VaultDocData]
"""Mapping of document paths to their parsed ``(metadata, body)`` tuples."""

__all__ = [
    "CheckDiagnostic",
    "CheckResult",
    "Severity",
    "VaultDocData",
    "VaultSnapshot",
    "extract_feature_tags",
    "is_generated_index",
    "iter_document_texts",
    "render_check_result",
]


def iter_document_texts(root_dir: Path):
    """Yield ``(path, text, has_crlf)`` for every readable vault document.

    The standalone-read fallback for content-consuming checks invoked
    without the ingress raw-text map (single-check CLI verbs, mutating
    passes).  ``text`` keeps the source newlines; ``has_crlf`` reports the
    CRLF convention.  Unreadable or non-UTF-8 files are skipped, mirroring
    every other discovery path (``check_encoding`` surfaces them).

    Reads the corpus as it stands.  The ``run_migrations`` flag this used
    to forward to ``scan_vault`` is gone with the scanner's migration
    trigger: a check reports on the workspace it is given and never
    converges it (issue #443).

    Args:
        root_dir: Project root directory.

    Yields:
        ``(path, text, has_crlf)`` tuples in scan order.
    """
    from ..scanner import scan_vault

    for doc_path in scan_vault(root_dir):
        try:
            raw_content = doc_path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        yield doc_path, raw_content, "\r\n" in raw_content


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


def is_generated_index(path: Path) -> bool:
    """Return ``True`` if *path* is a generated feature index file.

    Index files follow the ``<feature>.index.md`` naming convention and
    live under ``<docs_dir>/<index_dir>/`` (canonical) or, in
    unmigrated vaults, at the docs root.

    Post-#91 indexes carry the standard two-tag shape (``#index``
    directory tag plus the feature tag) and run through frontmatter
    validation like every other document, so ``frontmatter`` no longer
    consults this predicate. The exemption is still used by checkers
    whose semantics genuinely differ for indexes:

    - ``body-links`` skips them because their body legitimately lists
      vault documents as a generated inventory (wiki-links in body
      text are intentional, not violations).
    - ``orphans`` skips them because indexes have only outgoing links
      by design and would otherwise always register as orphans.
    - ``features`` and ``structure`` use the predicate to distinguish
      generated indexes from authored documents during their own
      bookkeeping rather than to bypass validation.

    The check is intentionally filename-only and folder-agnostic: a
    file dropped into the wrong directory by mistake is surfaced as a
    misplaced-index ERROR by ``vaultspec-core vault check structure`` rather than
    being silently exempted.

    Args:
        path: Absolute or relative path to test.

    Returns:
        ``True`` when the filename ends with ``.index.md``.
    """
    return path.name.endswith(".index.md")


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

# ASCII-only status markers per the cli-presentation-uniformity ADR: the data
# path emits no box-drawing or non-ASCII glyphs, so output survives a cp1252
# stdout byte-for-byte and reads uniformly with the outcome vocabulary.
_SEVERITY_ICON = {
    Severity.ERROR: "x",
    Severity.WARNING: "!",
    Severity.INFO: "-",
}


#: Maximum diagnostics carried per check, on BOTH surfaces.
#:
#: This was once a human-render cap that pointed the machine surface at an
#: uncapped ``--json`` payload. That premise was inverted: the machine consumer
#: is a context window, not a script, so the cap was being given to the reader
#: who can scroll and withheld from the one who cannot. Measured on a
#: 1,222-document vault, ``--json`` grew from 6,962 bytes clean to 2,211,057
#: fully damaged while the human form converged at 69,119 - largest exactly
#: when the caller could least afford it, since payload size tracks how broken
#: the vault is.
#:
#: Both surfaces now cut here and both report the totals, so neither can
#: mislead about what was withheld.
DIAGNOSTIC_RENDER_CAP = 50


def render_check_result(
    console: Console,
    result: CheckResult,
    *,
    verbose: bool = False,
    summary_only: bool = False,
) -> None:
    """Render a CheckResult to a Rich console.

    At most :data:`DIAGNOSTIC_RENDER_CAP` findings are printed per check; a
    marked truncation line reports how many more exist. The ``--json`` payload
    applies the same cap and carries the same totals, so the two surfaces agree
    on what was withheld.

    Args:
        console: Rich Console instance.
        result: The check result to render.
        verbose: When False, suppress INFO-level diagnostics.
        summary_only: When True, show only the one-line summary per check.
    """
    # When not verbose, INFO-only results are effectively clean.
    visible_issues = result.error_count + result.warning_count
    if result.is_clean or (not verbose and not visible_issues):
        console.print(f"  [green]ok[/green] {result.check_name}: [green]clean[/green]")
        return

    errors = result.error_count
    warnings = result.warning_count
    infos = result.info_count

    parts: list[str] = []
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

    icon = "[red]x[/red]" if errors else "[yellow]![/yellow]"
    console.print(f"  {icon} {result.check_name}: {summary}")

    if summary_only:
        return

    # Diagnostic text is content (it embeds file paths and [[wiki-link]]
    # names); escape it so Rich does not treat [[...]] as console markup.
    from rich.markup import escape

    rendered = 0
    suppressed = 0
    for diag in result.diagnostics:
        if diag.severity == Severity.INFO and not verbose:
            continue
        if rendered >= DIAGNOSTIC_RENDER_CAP:
            suppressed += 1
            continue
        rendered += 1
        style = _SEVERITY_STYLE[diag.severity]
        icon = _SEVERITY_ICON[diag.severity]
        message = escape(diag.message)
        path_str = escape(str(diag.path)) if diag.path else ""
        if path_str:
            console.print(f"    [{style}]{icon}[/{style}] {path_str}")
            console.print(f"      {message}")
        else:
            console.print(f"    [{style}]{icon}[/{style}] {message}")
        if diag.fix_description:
            console.print(f"      [dim]fix: {escape(diag.fix_description)}[/dim]")
    if suppressed:
        console.print(
            f"    [dim]... {suppressed} more finding"
            f"{'s' if suppressed != 1 else ''} not shown "
            "(counts above are complete)[/dim]"
        )
