"""Surface vault documents that are not valid UTF-8.

The framework treats ``.vault/`` as a UTF-8 corpus. Every discovery path -
``scan_vault``/``list_features`` in the scanner, ``scan_all`` in the query
layer, the graph builder, and the snapshot-backed checks - reads documents
with ``read_text(encoding="utf-8")`` and silently skips a file that fails to
decode (``UnicodeDecodeError``). A UTF-16 or Latin-1 ``.md`` is therefore
invisible: it never appears in a feature listing, never participates in a
graph build, and is silently omitted from a feature rename or index.

This checker makes that silent exclusion loud. It does NOT auto-decode or
rewrite anything: guessing an arbitrary encoding and rewriting it to UTF-8
would silently mutate document bytes. Instead it walks the docs tree directly
(a non-UTF-8 document is absent from the parsed snapshot, so this checker
cannot rely on it and does its own ``rglob``) and reports each non-UTF-8 file
as an ``ERROR`` to be converted by hand. A plain UTF-8 file and a UTF-8-BOM
file both decode cleanly and pass.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..exclusions import is_excluded_vault_path
from ._base import CheckDiagnostic, CheckResult, Severity

if TYPE_CHECKING:
    from pathlib import Path

    from ...graph.api import VaultGraph

logger = logging.getLogger(__name__)

__all__ = ["check_encoding"]

_DECODE_MESSAGE = (
    "Document is not valid UTF-8 "
    "(byte {start}: {reason}); it is silently "
    "excluded from feature scans, indexes, and renames. "
    "Convert it to UTF-8 (a UTF-8-BOM file is also accepted)."
)


def check_encoding(root_dir: Path, *, graph: VaultGraph | None = None) -> CheckResult:
    """Report every ``.vault/`` document that is not valid UTF-8.

    When *graph* is supplied (the combined ``run_all_checks`` pass), the
    findings come from the read and decode failures the ingress read already
    observed (:attr:`~vaultspec_core.graph.api.VaultGraph.encoding_issues`),
    folding this check into the run's single read of the corpus. Standalone,
    it walks ``<root>/<docs_dir>/**/*.md`` directly (mirroring
    ``scan_vault``'s exclusions: every non-corpus subtree and
    symlinks are skipped) rather than consulting the parsed snapshot, because
    a non-UTF-8 document never enters the snapshot in the first place. Either
    way, a clean decode (including a UTF-8-BOM file, which is valid UTF-8)
    passes, a :class:`UnicodeDecodeError` is reported as an ``ERROR`` naming
    the file, and a read failure (:class:`OSError`) is a ``WARNING``.

    Encoding is validated vault-wide and takes no ``feature`` filter: a
    non-UTF-8 document has no parseable frontmatter and therefore no feature
    tag to match against (this mirrors :func:`check_rename_integrity`, which is
    likewise scope-free).

    Args:
        root_dir: Project root directory.
        graph: A built :class:`~vaultspec_core.graph.api.VaultGraph` whose
            ingress read (``ensure_raw_texts``) has run.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with check
        name ``"encoding"``.
    """
    result = CheckResult(check_name="encoding", supports_fix=False)

    if graph is not None:
        # No per-file stat parity probes here: the graph path must stay
        # disk-free. The only divergence from the standalone walk is that a
        # symlinked document observed by the scan is reported rather than
        # skipped.
        for issue in sorted(graph.encoding_issues, key=lambda i: i.path):
            path = issue.path
            rel_path = path.relative_to(root_dir) if path.is_absolute() else path
            if issue.kind == "read":
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=rel_path,
                        message=f"Could not read document bytes: {issue.detail}",
                        severity=Severity.WARNING,
                    )
                )
            else:
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=rel_path,
                        message=_DECODE_MESSAGE.format(
                            start=issue.start, reason=issue.detail
                        ),
                        severity=Severity.ERROR,
                    )
                )
        return result

    from ...config import get_config

    docs_dir = root_dir / get_config().docs_dir
    if not docs_dir.exists():
        return result

    for path in sorted(docs_dir.rglob("*.md")):
        if is_excluded_vault_path(path):
            continue
        if path.is_symlink() or not path.is_file():
            continue

        rel_path = path.relative_to(root_dir) if path.is_absolute() else path

        try:
            raw = path.read_bytes()
        except OSError as exc:
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=f"Could not read document bytes: {exc}",
                    severity=Severity.WARNING,
                )
            )
            continue

        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=_DECODE_MESSAGE.format(start=exc.start, reason=exc.reason),
                    severity=Severity.ERROR,
                )
            )

    return result
