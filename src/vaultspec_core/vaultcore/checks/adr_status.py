"""Validate ADR status against the canonical taxonomy.

Checks that every Architecture Decision Record declares a status drawn from the
canonical :class:`~vaultspec_core.core.enums.AdrStatus` set, encoded in the body
H1 in the canonical backtick-quoted form, and that the body status agrees with
the supersession frontmatter. The canonical encoding is::

    # `feature` adr: `Title` | (**status:** `accepted`)

Surfaces, all as warnings so the suite never hard-fails an existing corpus:

- a status token outside the canonical set, or no parseable status at all;
- status declared in a legacy ``## Status`` section instead of the H1;
- a bare (unquoted) H1 token, which ``--fix`` normalizes to the quoted form;
- ``superseded_by`` set in frontmatter while the body status is not
  ``superseded`` (an unpropagated supersession).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from ...core.enums import AdrStatus
from ...core.helpers import atomic_write
from ..models import refresh_modified_stamp, vault_today
from ._base import CheckDiagnostic, CheckResult, Severity

if TYPE_CHECKING:
    from pathlib import Path

    from ._base import VaultSnapshot

__all__ = ["check_adr_status"]

logger = logging.getLogger(__name__)

# H1 status token: captures the optional backtick quoting and the raw token.
# Mirrors the pattern used by ``adr_supersede`` so the two stay in lockstep.
_H1_STATUS_RE = re.compile(
    r"^#\s+.*\|\s+\(\*\*status:\*\*\s+(?P<open>`?)(?P<token>[^`)]+?)(?P<close>`?)\)\s*$"
)
_LEGACY_STATUS_RE = re.compile(r"^##\s+Status\s*$", re.MULTILINE)

_CANONICAL_TOKENS = ", ".join(s.value for s in AdrStatus)


def _is_adr(path: Path) -> bool:
    """Return ``True`` when *path* is an ADR document."""
    return path.parent.name == "adr" and path.suffix == ".md"


def _find_h1_status(body: str) -> tuple[int, str, bool] | None:
    """Locate the H1 status declaration in *body*.

    Args:
        body: The document body (markdown after the frontmatter).

    Returns:
        ``(line_index, token, quoted)`` for the first matching H1, or ``None``
        when no H1-inline status is present. ``quoted`` is ``True`` when the
        token is wrapped in backticks.
    """
    for index, line in enumerate(body.split("\n")):
        if not line.startswith("# "):
            continue
        # Anchor to the document's first H1: status lives on the title line, so
        # a title without a status marker means "no parseable status" rather
        # than deferring to some later heading that happens to carry one.
        match = _H1_STATUS_RE.match(line)
        if match:
            quoted = bool(match.group("open")) and bool(match.group("close"))
            return index, match.group("token").strip(), quoted
        return None
    return None


def _normalize_h1_quote(doc_path: Path, root_dir: Path, token: str) -> bool:
    """Rewrite the H1 status token to the canonical backtick-quoted form.

    The read, the heading rewrite, the stamp refresh, and the write are one
    critical section on *doc_path*'s per-document advisory lock - the same
    sentinel ``execute_edit`` takes - so the replacement is always derived
    from the bytes it overwrites rather than from a revision a concurrent
    editor has since superseded.

    Args:
        doc_path: Absolute path to the ADR document.
        root_dir: Project root owning the document's ``.vault/``.
        token: The canonical status value to write.

    Returns:
        ``True`` when the file was modified.
    """
    from ..edit_engine import document_write_lock

    with document_write_lock(doc_path, root_dir):
        return _normalize_h1_quote_locked(doc_path, token)


def _normalize_h1_quote_locked(doc_path: Path, token: str) -> bool:
    """Perform the H1 quoting rewrite under *doc_path*'s already-held lock.

    Args:
        doc_path: Absolute path to the ADR document.
        token: The canonical status value to write.

    Returns:
        ``True`` when the file was modified.
    """
    try:
        raw = doc_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    newline = "\r\n" if "\r\n" in raw else "\n"
    content = raw.replace("\r\n", "\n")

    lines = content.split("\n")
    changed = False
    for index, line in enumerate(lines):
        if not line.startswith("# "):
            continue
        match = _H1_STATUS_RE.match(line)
        if not match:
            break
        prefix = line[: match.start("open")]
        suffix = line[match.end("close") :]
        lines[index] = f"{prefix}`{token}`{suffix}"
        changed = True
        break

    if not changed:
        return False

    rendered = "\n".join(lines)
    # The quoting rewrite is a content mutation, so refresh the recency stamp in
    # the same pass (mirroring adr_supersede); the helper preserves the line
    # ending convention, so apply it before reapplying CRLF below.
    rendered = refresh_modified_stamp(rendered, vault_today())
    new_content = rendered if newline == "\n" else rendered.replace("\n", newline)
    atomic_write(doc_path, new_content)
    logger.info("Normalized H1 status quoting in %s", doc_path.name)
    return True


def check_adr_status(
    root_dir: Path,
    *,
    snapshot: VaultSnapshot,
    feature: str | None = None,
    fix: bool = False,
) -> CheckResult:
    """Validate ADR status declarations against the canonical taxonomy.

    Args:
        root_dir: Project root directory.
        snapshot: Mapping of document paths to parsed ``(metadata, body)``.
        feature: Restrict checks to ADRs carrying this feature tag (without
            ``#``).
        fix: When ``True``, normalize a bare canonical H1 token to the quoted
            form. Other findings are advisory and never auto-fixed.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with check
        name ``"adr-status"``.
    """
    result = CheckResult(check_name="adr-status", supports_fix=True)
    feat = feature.lstrip("#") if feature else None

    for path, (meta, body) in sorted(snapshot.items(), key=lambda kv: str(kv[0])):
        if not _is_adr(path):
            continue
        if feat is not None and feat not in {t.lstrip("#") for t in meta.tags}:
            continue

        rel_path = path.relative_to(root_dir)
        h1 = _find_h1_status(body)

        if h1 is None:
            if _LEGACY_STATUS_RE.search(body):
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=rel_path,
                        message=(
                            "ADR status is declared in a legacy '## Status' "
                            "section, not the canonical H1 status token"
                        ),
                        severity=Severity.WARNING,
                        fix_description=(
                            "Move the status into the H1 as "
                            "(**status:** `<value>`) per the ADR template"
                        ),
                    )
                )
            else:
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=rel_path,
                        message="ADR has no parseable status in its H1",
                        severity=Severity.WARNING,
                        fix_description=(
                            "Add (**status:** `<value>`) to the H1; one of "
                            f"{_CANONICAL_TOKENS}"
                        ),
                    )
                )
            continue

        _, token, quoted = h1
        status = AdrStatus.from_token(token)

        if status is None:
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=(
                        f"ADR status '{token}' is outside the canonical set "
                        f"({_CANONICAL_TOKENS})"
                    ),
                    severity=Severity.WARNING,
                    fix_description="Set the H1 status to a canonical value",
                )
            )
            continue

        if not quoted:
            if fix and _normalize_h1_quote(path, root_dir, status.value):
                result.fixed_count += 1
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=rel_path,
                        message=f"Fixed: quoted H1 status token `{status.value}`",
                        severity=Severity.INFO,
                    )
                )
            else:
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=rel_path,
                        message=(
                            f"ADR status '{token}' is not backtick-quoted in the H1"
                        ),
                        severity=Severity.WARNING,
                        fixable=True,
                        fix_description="Wrap the H1 status token in backticks",
                    )
                )

        if meta.superseded_by and status is not AdrStatus.SUPERSEDED:
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=(
                        "ADR has 'superseded_by' in frontmatter but its body "
                        f"status is '{status.value}', not 'superseded'"
                    ),
                    severity=Severity.WARNING,
                    fix_description=(
                        "Re-run vault adr supersede, or set the H1 status to "
                        "`superseded` to match the frontmatter"
                    ),
                )
            )

    return result
